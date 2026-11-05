#!/usr/bin/env node

/**
 * Outputs a valid OpenAPI 3.0 spec (JSON, to stdout) for every webhook node
 * found in an n8n workflow file.
 *
 * Usage:
 *   node generate-webhook-openapi.js <workflow-file> <workflow-name>
 *
 * Each webhook node becomes one path entry in the spec.  When multiple webhook
 * nodes are present their paths are merged into a single spec document.
 *
 * Outputs an empty object `{}` and exits 0 when the workflow has no webhook
 * nodes (signals to the caller that the MCP-server step can be skipped).
 */

import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";

const [, , file, workflowName] = process.argv;

if (!file || !workflowName) {
  console.error("Usage: node generate-webhook-openapi.js <workflow-file> <workflow-name>");
  process.exit(1);
}

let wf;
try {
  wf = JSON.parse(readFileSync(file, "utf-8"));
} catch (error) {
  console.error(`Failed to parse workflow JSON from ${file}: ${error.message}`);
  process.exit(1);
}

if (!Array.isArray(wf.nodes)) {
  console.error(`Invalid workflow format in ${file}: expected a 'nodes' array.`);
  process.exit(1);
}

const webhookNodes = wf.nodes.filter((node) => node.type === "n8n-nodes-base.webhook");

// No webhook nodes — output empty object so the caller can skip the MCP step.
if (webhookNodes.length === 0) {
  process.stdout.write("{}\n");
  process.exit(0);
}

/**
 * Load the workflow-schema.openapi.json sidecar co-located with the workflow file.
 * Returns the parsed `paths` object, or null if absent or malformed.
 */
function loadSidecarPaths(workflowFile) {
  const schemaPath = join(dirname(workflowFile), "workflow-schema.openapi.json");
  if (!existsSync(schemaPath)) return null;
  try {
    const doc = JSON.parse(readFileSync(schemaPath, "utf-8"));
    if (doc && typeof doc.paths === "object" && !Array.isArray(doc.paths)) {
      return doc.paths;
    }
  } catch {
    // Malformed sidecar — caller falls back to generic schema.
  }
  return null;
}

/**
 * Return the requestBody from the sidecar for a given webhook path and method,
 * or null when the sidecar has no matching entry.
 *
 * @param {Object|null} sidecarPaths - Parsed `paths` object from the sidecar, or null
 * @param {string} webhookPath - Webhook path to match (leading slash optional)
 * @param {string} method - HTTP method (e.g. "post")
 */
function suppliedRequestBody(sidecarPaths, webhookPath, method) {
  if (!sidecarPaths) return null;
  const norm = (p) => String(p || "").replace(/^\/+|\/+$/g, "");
  const key = Object.keys(sidecarPaths).find((k) => norm(k) === norm(webhookPath));
  if (!key) return null;
  const op = sidecarPaths[key]?.[method.toLowerCase()] ?? sidecarPaths[key]?.post;
  return op?.requestBody ?? null;
}

const sidecarPaths = loadSidecarPaths(file);

// ── generateWebhookOpenApiSpec ────────────────────────────────────────────────

/**
 * Generate OpenAPI 3.0 specification for a webhook endpoint
 *
 * Per ORD spec, REST APIs should have an OpenAPI spec in resourceDefinitions.
 * This generates a minimal OpenAPI 3.0.0 spec for the webhook.
 *
 * n8n webhooks specify their HTTP method in the node's parameters.httpMethod field.
 * If provided, we generate spec for that specific method. Otherwise, we include
 * all common methods since n8n webhook triggers can be configured for any method.
 *
 * @param {Object} tenant - Workflow tenant object
 * @param {Object} webhook - Webhook object
 * @param {string} [webhook.httpMethod] - HTTP method from n8n webhook node (e.g., "POST", "GET")
 * @param {string[]} [webhook.methods] - Array of HTTP methods (alternative to httpMethod)
 * @returns {Object} OpenAPI 3.0.0 specification
 */
function generateWebhookOpenApiSpec(tenant, webhook) {
  const webhookPathClean = `/${webhook.path.replace(/^\//, "")}`;

  // Determine supported HTTP methods:
  // 1. If webhook.httpMethod is set (from n8n node), use only that method
  // 2. If webhook.methods array is set, use those
  // 3. Otherwise, include all common methods
  let supportedMethods;
  if (webhook.httpMethod) {
    // Single method from n8n webhook node configuration
    supportedMethods = [webhook.httpMethod.trim().toLowerCase()];
  } else if (webhook.methods && Array.isArray(webhook.methods)) {
    supportedMethods = webhook.methods.map((m) => m.toLowerCase());
  } else {
    // Default to common methods if not specified
    supportedMethods = ["get", "post", "put", "delete", "patch"];
  }

  // Build operations for each HTTP method
  const pathOperations = {};

  // Common response schema
  const successResponse = {
    description: "Webhook executed successfully",
    content: {
      "application/json": {
        schema: {
          type: "object",
          additionalProperties: true,
          description: "Response from workflow execution",
        },
      },
    },
  };

  const errorResponses = {
    401: { description: "Unauthorized - Invalid or missing JWT token" },
    403: { description: "Forbidden - Token audience mismatch or invalid issuer" },
    500: { description: "Internal Server Error - Workflow execution failed" },
  };

  // Common request body schema (for methods that accept body)
  const requestBody = {
    description: "Webhook payload - passed to workflow as input",
    required: false,
    content: {
      "application/json": {
        schema: {
          type: "object",
          additionalProperties: true,
          description: "JSON payload for the workflow",
        },
      },
      "application/x-www-form-urlencoded": {
        schema: {
          type: "object",
          additionalProperties: true,
        },
      },
      "multipart/form-data": {
        schema: {
          type: "object",
          additionalProperties: true,
        },
      },
    },
  };

  // Methods that accept request body
  const methodsWithBody = ["post", "put", "patch"];

  for (const method of supportedMethods) {
    const methodLower = method.toLowerCase();
    const methodUpper = method.toUpperCase();

    pathOperations[methodLower] = {
      summary: `${methodUpper} ${webhook.name || webhook.path}`,
      description: `${methodUpper} endpoint for webhook: ${webhook.path}\n\nWorkflow: ${tenant.workflowName || tenant.tenantName}`,
      // operationId follows format: {method}{TitleCase}Using{METHOD}
      // e.g., /number-check-agent/workflow/webhook → getNumberCheckAgentWorkflowWebhookUsingGET
      operationId: (() => {
        const webhookPathForOp = webhook.path.replace(/^\//, "");
        const titleCaseName = webhookPathForOp
          .split(/[-_\s/]+/)
          .filter(Boolean)
          .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
          .join("");
        return `${methodLower}${titleCaseName}Using${methodUpper}`;
      })(),
      tags: [tenant.workflowName || tenant.tenantName],
      responses: {
        200: successResponse,
        ...errorResponses,
      },
      security: [{ bearerAuth: [] }],
    };

    // Add request body for methods that support it
    if (methodsWithBody.includes(methodLower)) {
      const supplied = suppliedRequestBody(sidecarPaths, webhookPathClean, methodLower);
      pathOperations[methodLower].requestBody = supplied ?? requestBody;
    }

    // Add query parameters for GET
    if (methodLower === "get") {
      pathOperations[methodLower].parameters = [
        {
          name: "query",
          in: "query",
          description: "Query parameters are passed to the workflow",
          required: false,
          schema: {
            type: "object",
            additionalProperties: true,
          },
          style: "form",
          explode: true,
        },
      ];
    }
  }

  return {
    openapi: "3.0.3",
    info: {
      title: webhook.name || `${tenant.workflowName} - ${webhook.path}`,
      description: [
        `Webhook endpoint for workflow tenant: ${tenant.tenantName}`,
        ``,
        `**Workflow:** ${tenant.workflowName || "N/A"}`,
        ``,
        `This webhook accepts multiple HTTP methods. The request body/query parameters`,
        `are passed as input to the n8n workflow execution.`,
      ].join("\n"),
      version: tenant.versionId || "1.0.0",
      contact: {
        name: "Managed n8n Support",
      },
    },
    servers: [
      {
        url: tenant.tenantUrl,
        description: "Workflow tenant webhook base URL",
      },
    ],
    tags: [
      {
        name: tenant.workflowName || tenant.tenantName,
        description: `Webhooks for workflow: ${tenant.workflowName || tenant.tenantName}`,
      },
    ],
    paths: {
      [webhookPathClean]: pathOperations,
    },
    components: {
      securitySchemes: {
        bearerAuth: {
          type: "http",
          scheme: "bearer",
          bearerFormat: "JWT",
          description:
            "JWT token with correct issuer and audience for this workflow tenant. Token is validated by Istio RequestAuthentication.",
        },
      },
    },
  };
}

// ── build combined spec from all webhook nodes ────────────────────────────────

const tenant = {
  tenantName: workflowName,
  workflowName,
  // Placeholder URL — the real base URL is resolved at deployment time.
  tenantUrl: "https://your-n8n-workflow-tenant.example.com",
  versionId: "1.0.0",
};

// Accumulate paths across all webhook nodes, then build a single spec envelope.
// Using a Map lets us deep-merge per-path method objects instead of overwriting
// them (which Object.assign would do when two nodes share the same URL path).
const accumulatedPaths = new Map();
const seenOperationIds = new Set();
let firstSpec = null;

for (const node of webhookNodes) {
  const rawPath = String(node.parameters?.path ?? "").trim();
  if (!rawPath) {
    console.error(
      `Webhook node '${node.name}' is missing parameters.path; cannot generate path entry.`,
    );
    process.exit(1);
  }

  const webhook = {
    path: rawPath,
    name: node.name,
    // n8n stores the selected HTTP method in parameters.httpMethod (optional).
    httpMethod: node.parameters?.httpMethod ?? undefined,
  };

  const spec = generateWebhookOpenApiSpec(tenant, webhook);

  // Capture the envelope from the first spec only.
  if (firstSpec === null) firstSpec = spec;

  for (const [pathKey, methodsObj] of Object.entries(spec.paths)) {
    const existing = accumulatedPaths.get(pathKey) ?? {};

    for (const [method, operation] of Object.entries(methodsObj)) {
      let opId = operation.operationId;
      if (seenOperationIds.has(opId)) {
        let suffix = 2;
        while (seenOperationIds.has(`${opId}${suffix}`)) suffix++;
        opId = `${opId}${suffix}`;
        operation.operationId = opId;
      }
      seenOperationIds.add(opId);

      existing[method] = operation;
    }

    accumulatedPaths.set(pathKey, existing);
  }
}

// Build the final spec from the first envelope plus the merged paths.
const combinedSpec = {
  ...firstSpec,
  paths: Object.fromEntries(accumulatedPaths),
};

process.stdout.write(`${JSON.stringify(combinedSpec, null, 2)}\n`);
