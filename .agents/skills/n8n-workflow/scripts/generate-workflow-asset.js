#!/usr/bin/env node

/**
 * Outputs the top-level workflow: block and provides.apis[] YAML for asset.yaml.
 *
 * Usage:
 *   node generate-workflow-asset.js <workflow-file> <workflow-name> <solution-name>
 *
 * Each webhook node produces two provides.apis[] entries:
 *   - kind: rest  — the HTTP endpoint
 *   - kind: mcp-server — the MCP translation entry
 *
 * The webhook path is composed at design time as <solution-name>/<workflow-name>/<operation>,
 * where <operation> is derived from the webhook node's name (same source as the
 * API name and ORD IDs, so the path always fits the ordId). It is written back
 * into the node's parameters.path (no leading slash) and emitted as the kind:
 * rest path (with leading slash), so no webhook URL is generated at deploy time.
 * Re-running is idempotent.
 *
 * Alongside the printed YAML, this script writes a `workflow-schema.openapi.json`
 * sidecar next to the workflow file: a full OpenAPI 3.1 document whose `paths`
 * mirror `provides.apis[].path` (one `post` per webhook — `requestBody` from the
 * body reads, `200` from the Respond nodes). It is a best-effort skeleton (coarse
 * types, `<...>` placeholders) the LLM MUST refine, written only when absent.
 * `asset.yaml` carries no schema data.
 *
 * The LLM must paste the printed YAML verbatim into asset.yaml, fill in the
 * description placeholder on each kind: rest entry, and refine
 * workflow-schema.openapi.json.
 */

import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { basename, dirname, join } from "node:path";

const [, , file, workflowName, solutionName] = process.argv;

if (!file || !workflowName || !solutionName) {
  console.error(
    "Usage: node generate-workflow-asset.js <workflow-file> <workflow-name> <solution-name>",
  );
  process.exit(1);
}

let rawWorkflowText;
let wf;
try {
  rawWorkflowText = readFileSync(file, "utf-8");
  wf = JSON.parse(rawWorkflowText);
} catch (error) {
  console.error(`Failed to parse workflow JSON from ${file}: ${error.message}`);
  process.exit(1);
}

if (!Array.isArray(wf.nodes)) {
  console.error(`Invalid workflow format in ${file}: expected a 'nodes' array.`);
  process.exit(1);
}

const webhookNodes = wf.nodes.filter((node) => node.type === "n8n-nodes-base.webhook");
const respondNodes = wf.nodes.filter((node) => node.type === "n8n-nodes-base.respondToWebhook");

// Quote a YAML scalar only when it contains characters that would break bare style
function yamlString(value) {
  const s = String(value);
  return /[:#[\]{},&*?|<>=!%@`"']|^\s|\s$/.test(s) ? JSON.stringify(s) : s;
}

function normalizeWords(str) {
  return String(str)
    .trim()
    .split(/[^a-zA-Z0-9]+/)
    .filter(Boolean);
}

/** Convert a string to snake_case */
function toSnake(str) {
  return normalizeWords(str)
    .map((word) => word.toLowerCase())
    .join("_");
}

/** Convert a string to camelCase (lowercase first letter) */
function toCamel(str) {
  const words = normalizeWords(str);
  if (words.length === 0) return "";
  return (
    words[0].toLowerCase() +
    words
      .slice(1)
      .map((word) => word[0].toUpperCase() + word.slice(1).toLowerCase())
      .join("")
  );
}

/** Escape a string for safe use inside a RegExp. */
function escapeRegExp(str) {
  return String(str).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Best-effort request-body schema from `<ref>.json.body.<field>` reads, where
 * `<ref>` is the webhook by name, or `$json`/`$input` when it is the only
 * webhook. Trailing delimiter types the field: `.`→object, `[`→array, else
 * string.
 *
 * REVISIT: body only. query/path params aren't derived — add them as OpenAPI
 * `parameters` (`in: query` / `in: path`) by hand when needed.
 */
function deriveInputSchema(node, text, isSingleWebhook) {
  const properties = {};
  const required = [];

  const setProp = (name, type) => {
    if (!name) return;
    // Do not downgrade a richer inferred type back to string.
    if (!properties[name] || (properties[name].type === "string" && type !== "string")) {
      properties[name] = { type };
    }
  };

  // Body field references.
  // Field token capture: `.field` (dot) or `["field"]` / `['field']` (bracket),
  // followed by a delimiter used to infer the type.
  const fieldTail = "(?:\\.([A-Za-z_$][A-Za-z0-9_$]*)|\\[\\s*['\"]([^'\"]+)['\"]\\s*\\])([.\\[]?)";

  const collect = (prefixPattern) => {
    const re = new RegExp(`${prefixPattern}\\.body${fieldTail}`, "g");
    for (const m of text.matchAll(re)) {
      const name = m[1] ?? m[2];
      const delim = m[3];
      const type = delim === "." ? "object" : delim === "[" ? "array" : "string";
      setProp(name, type);
    }
  };

  // Prefixes end right before `.body`:
  //   named form:  $('Node Name')(.item|.first()|.last()|.all()[n])?.json
  //   $input form: $input(.first()|.last()|.item())?.json
  //   $json form:  $json            (no `.json` segment)
  const nameRef = `\\$\\(\\s*['"]${escapeRegExp(node.name)}['"]\\s*\\)(?:\\.(?:item|first\\(\\)|last\\(\\)|all\\(\\)(?:\\[\\d+\\])?))?\\.json`;

  // Unambiguous: explicit node-name references.
  collect(nameRef);
  // Implicit references only when there is a single webhook to attribute to.
  if (isSingleWebhook) {
    collect("\\$json");
    collect("\\$input(?:\\.(?:first|last|item)\\(\\))?\\.json");
  }

  return { properties, required };
}

/** Infer a coarse JSON Schema type from a JS value-expression source string. */
function inferValueType(raw) {
  const v = String(raw).trim().replace(/^=/, "").trim();
  if (/^(true|false)$/.test(v)) return "boolean";
  if (/^-?\d+(\.\d+)?$/.test(v)) return "number";
  if (/^['"`]/.test(v)) return "string";
  if (/^\[/.test(v)) return "array";
  if (/^\{/.test(v)) return "object";
  if (/\bnew\s+Date\b/.test(v)) return "string";
  return "string"; // expressions like $json.x, function calls, etc.
}

/**
 * Extract the first balanced `{ ... }` object literal from a source string,
 * ignoring braces inside quotes. Returns the inner text (without the outer
 * braces) or null if none found.
 */
function extractObjectLiteral(src) {
  const start = src.indexOf("{");
  if (start === -1) return null;
  let depth = 0;
  let quote = null;
  for (let i = start; i < src.length; i++) {
    const ch = src[i];
    const prev = src[i - 1];
    if (quote) {
      if (ch === quote && prev !== "\\") quote = null;
      continue;
    }
    if (ch === "'" || ch === '"' || ch === "`") {
      quote = ch;
    } else if (ch === "{") {
      depth++;
    } else if (ch === "}") {
      depth--;
      if (depth === 0) return src.slice(start + 1, i);
    }
  }
  return null;
}

/** Split an object-literal body on top-level commas (respecting nesting/strings). */
function splitTopLevel(body) {
  const parts = [];
  let depth = 0;
  let quote = null;
  let current = "";
  for (let i = 0; i < body.length; i++) {
    const ch = body[i];
    const prev = body[i - 1];
    if (quote) {
      if (ch === quote && prev !== "\\") quote = null;
      current += ch;
      continue;
    }
    if (ch === "'" || ch === '"' || ch === "`") {
      quote = ch;
      current += ch;
    } else if (ch === "{" || ch === "[" || ch === "(") {
      depth++;
      current += ch;
    } else if (ch === "}" || ch === "]" || ch === ")") {
      depth--;
      current += ch;
    } else if (ch === "," && depth === 0) {
      parts.push(current);
      current = "";
    } else {
      current += ch;
    }
  }
  if (current.trim()) parts.push(current);
  return parts;
}

/** Parse `key: value` pairs from an object-literal body into {name, type}. */
function parseObjectEntries(body) {
  const entries = [];
  for (const part of splitTopLevel(body)) {
    const trimmed = part.trim();
    if (!trimmed) continue;
    // Find the first top-level colon (key/value separator).
    let depth = 0;
    let quote = null;
    let colon = -1;
    for (let i = 0; i < trimmed.length; i++) {
      const ch = trimmed[i];
      const prev = trimmed[i - 1];
      if (quote) {
        if (ch === quote && prev !== "\\") quote = null;
        continue;
      }
      if (ch === "'" || ch === '"' || ch === "`") quote = ch;
      else if (ch === "{" || ch === "[" || ch === "(") depth++;
      else if (ch === "}" || ch === "]" || ch === ")") depth--;
      else if (ch === ":" && depth === 0) {
        colon = i;
        break;
      }
    }
    let keyRaw;
    let valueRaw;
    if (colon === -1) {
      // Shorthand property, e.g. { status } → value unknown.
      keyRaw = trimmed;
      valueRaw = "";
    } else {
      keyRaw = trimmed.slice(0, colon).trim();
      valueRaw = trimmed.slice(colon + 1).trim();
    }
    const name = keyRaw.replace(/^['"`]|['"`]$/g, "");
    if (!/^[A-Za-z_$][A-Za-z0-9_$]*$/.test(name)) continue; // skip spread/computed keys
    entries.push({ name, type: valueRaw ? inferValueType(valueRaw) : "string" });
  }
  return entries;
}

/**
 * Strip the n8n expression wrapper from a parameter value:
 *   `={{ <expr> }}` → `<expr>`   |   `=<literal>` → `<literal>`
 */
function unwrapExpression(value) {
  let v = String(value).trim();
  if (v.startsWith("=")) v = v.slice(1).trim();
  if (v.startsWith("{{") && v.endsWith("}}")) v = v.slice(2, -2).trim();
  return v;
}

/**
 * Remove `//` line comments and block comments from a JS-ish source string,
 * leaving string literals untouched. n8n Respond bodies frequently contain
 * inline comments that would otherwise break object-literal parsing.
 */
function stripComments(src) {
  let out = "";
  let quote = null;
  for (let i = 0; i < src.length; i++) {
    const ch = src[i];
    const next = src[i + 1];
    const prev = src[i - 1];
    if (quote) {
      out += ch;
      if (ch === quote && prev !== "\\") quote = null;
      continue;
    }
    if (ch === "'" || ch === '"' || ch === "`") {
      quote = ch;
      out += ch;
      continue;
    }
    if (ch === "/" && next === "/") {
      while (i < src.length && src[i] !== "\n") i++;
      out += "\n";
      continue;
    }
    if (ch === "/" && next === "*") {
      i += 2;
      while (i + 1 < src.length && !(src[i] === "*" && src[i + 1] === "/")) i++;
      i += 1; // land on the closing '/', the for-loop's i++ moves past it
      continue;
    }
    out += ch;
  }
  return out;
}

/**
 * Best-effort derivation of a webhook's output JSON Schema from the object
 * literals returned by Respond to Webhook nodes.
 *
 * A Respond node is attributed to this webhook when there is only one webhook,
 * or when its responseBody explicitly references this webhook by name
 * (`$('Node Name')...`). Keys are unioned across all attributed Respond nodes.
 */
function deriveOutputSchema(node, respondNodes, isSingleWebhook) {
  const properties = {};
  const nameRef = new RegExp(`\\$\\(\\s*['"]${escapeRegExp(node.name)}['"]\\s*\\)`);

  for (const rn of respondNodes) {
    const rb = String(rn.parameters?.responseBody ?? "");
    if (!rb) continue;
    if (!isSingleWebhook && !nameRef.test(rb)) continue; // cannot attribute

    const body = extractObjectLiteral(stripComments(unwrapExpression(rb)));
    if (!body) continue;
    for (const { name, type } of parseObjectEntries(body)) {
      if (!properties[name] || (properties[name].type === "string" && type !== "string")) {
        properties[name] = { type };
      }
    }
  }

  return { properties, required: [] };
}

const definitionFile = basename(file);

// ── workflow: block (no webhooks → emit workflow block only) ─────────────────
if (webhookNodes.length === 0) {
  let out = `workflow:\n`;
  out += `  definitionFile: ${yamlString(definitionFile)}\n`;
  out += `  name: ${yamlString(workflowName)}\n`;
  out += `  ordId: sap.btpn8n:apiResource:ManagedN8nMcpServer:v1\n`;
  process.stdout.write(`${out.trimEnd()}\n`);
  process.exit(0);
}

// ── derive schemas + provides.apis[] ─────────────────────────────────────────
const seenNames = new Set();
const seenOrdIds = new Set();

const apis = [];
// OpenAPI 3.1 `paths` object: webhook path → { <method>: operation }. Assembled
// into the workflow-schema.openapi.json sidecar below.
const openApiPaths = {};
const isSingleWebhook = webhookNodes.length === 1;
let workflowModified = false;

// Convert a derived { properties, required } into a JSON Schema object
// (OpenAPI 3.1 schemas are JSON Schema).
function toJsonSchema({ properties, required }) {
  const schema = { type: "object", properties: {} };
  for (const [name, def] of Object.entries(properties)) {
    schema.properties[name] = { type: def.type };
  }
  if (required && required.length > 0) schema.required = [...required];
  return schema;
}

// Build the OpenAPI operation for one webhook node. `summary`/response
// `description` are placeholders the LLM must refine. A requestBody is emitted
// only when body fields were derived.
function buildOperation(node) {
  const input = toJsonSchema(deriveInputSchema(node, rawWorkflowText, isSingleWebhook));
  const output = toJsonSchema(deriveOutputSchema(node, respondNodes, isSingleWebhook));
  const op = {
    summary: `<one sentence describing what the ${node.name} endpoint does>`,
  };
  if (Object.keys(input.properties).length > 0) {
    op.requestBody = {
      required: true,
      content: { "application/json": { schema: input } },
    };
  }
  op.responses = {
    200: {
      description: `<one sentence describing the ${node.name} response>`,
      content: { "application/json": { schema: output } },
    },
  };
  return op;
}

webhookNodes.forEach((n) => {
  const snake = toSnake(n.name);
  const camel = toCamel(n.name);

  if (!snake || !camel) {
    console.error(`Unable to derive API identifiers from node name: '${n.name}'`);
    process.exit(1);
  }

  const mcpCamel = `${camel}McpServer`;
  const mcpSnake = `${snake}_mcp_server`;

  // Full design-time webhook path: <solution-name>/<asset-name>/<operation>.
  // The operation segment is derived from the node name (kebab-case == the API
  // name with "-"), the same source as the API name and ORD IDs, so the path
  // always fits the ordId. <asset-name> is the workflow name (== asset
  // metadata.name by convention). The runtime appends this to the tenant URL
  // as-is, so no webhook URL is generated at deploy time.
  const operation = snake.replace(/_/g, "-");
  const nodePath = `${solutionName}/${workflowName}/${operation}`;
  const path = `/${nodePath}`;
  n.parameters = n.parameters ?? {};
  if (n.parameters.path !== nodePath) {
    n.parameters.path = nodePath;
    workflowModified = true;
  }

  const restOrdId = `sap.n8nwfrt:apiResource:${solutionName}_${workflowName}.${camel}:v1`;
  const mcpOrdId = `sap.n8nwfrt:apiResource:${solutionName}_${workflowName}.${mcpCamel}:v1`;

  for (const id of [restOrdId, mcpOrdId]) {
    if (seenOrdIds.has(id)) {
      console.error(`Duplicate ORD ID generated: '${id}' (from node name '${n.name}')`);
      process.exit(1);
    }
    seenOrdIds.add(id);
  }

  if (seenNames.has(snake) || seenNames.has(mcpSnake)) {
    console.error(`Duplicate API name generated for node name: '${n.name}'`);
    process.exit(1);
  }
  seenNames.add(snake);
  seenNames.add(mcpSnake);

  // OpenAPI operation for this webhook, keyed by its path (identical to the
  // rest api `path` below, so the document paths mirror provides.apis[].path).
  // Method mirrors the webhook node's httpMethod (default POST).
  const method = String(n.parameters?.httpMethod ?? "POST").toLowerCase();
  openApiPaths[path] = { [method]: buildOperation(n) };

  apis.push({
    name: snake,
    path,
    kind: "rest",
    ordId: restOrdId,
    displayName: n.name,
  });
  apis.push({
    name: mcpSnake,
    kind: "mcp-server",
    displayName: n.name,
    ordId: mcpOrdId,
  });
});

// ── workflow: block ──────────────────────────────────────────────────────────
let yaml = `workflow:\n`;
yaml += `  definitionFile: ${yamlString(definitionFile)}\n`;
yaml += `  name: ${yamlString(workflowName)}\n`;
yaml += `  ordId: sap.btpn8n:apiResource:ManagedN8nMcpServer:v1\n`;

// ── provides.apis[] block ────────────────────────────────────────────────────
yaml += `\nprovides:\n  apis:\n`;
apis.forEach((a) => {
  yaml += `    - name: ${yamlString(a.name)}\n`;
  if (a.kind === "rest") {
    yaml += `      path: ${yamlString(a.path)}\n`;
  }
  yaml += `      kind: ${a.kind}\n`;
  if (a.kind === "rest") {
    yaml += `      description: <add description>\n`;
  } else {
    yaml += `      description: MCP server for ${a.displayName.toLowerCase()} operations\n`;
  }
  yaml += `      ordId: ${yamlString(a.ordId)}\n`;
});

if (workflowModified) {
  writeFileSync(file, `${JSON.stringify(wf, null, 2)}\n`);
}

// ── workflow-schema.openapi.json sidecar ─────────────────────────────────────
// A full OpenAPI 3.1 document describing the webhook endpoints. Written next to
// the workflow file, write-if-absent so an already-refined sidecar is never
// overwritten.
const openApiDocument = {
  openapi: "3.1.0",
  info: {
    title: typeof wf.name === "string" && wf.name ? wf.name : workflowName,
    version: "1.0.0",
  },
  paths: openApiPaths,
};
const schemaPath = join(dirname(file), "workflow-schema.openapi.json");
if (existsSync(schemaPath)) {
  console.error(
    `workflow-schema.openapi.json already exists at ${schemaPath}; leaving it untouched (refine it by hand).`,
  );
} else {
  writeFileSync(schemaPath, `${JSON.stringify(openApiDocument, null, 2)}\n`);
  console.error(
    `Wrote skeleton ${schemaPath} — refine the request/response schemas, field types, enums, required, and descriptions.`,
  );
}

process.stdout.write(`${yaml.trimEnd()}\n`);
