# n8n Workflow Skill

## Steps

### **Set up project folder**
If `assets/workflows/<workflow-name>/` already exists, use it. Otherwise create it:
   ```bash
   mkdir -p assets/workflows/<workflow-name>/
   ```

When part of a multi-asset solution, add the following entry to `solution.yaml`:
```yaml
  - ref: ./assets/workflows/<workflow-name>/asset.yaml
```

### **MANDATORY: Look up nodes from the catalog (MUST do this for EVERY node)**

Before writing ANY node in the workflow JSON, you MUST look up its exact `type` and `typeVersion` from the catalog.

Required verification checklist:
- Call `search-nodes-catalog` MCP tool once with all planned node keywords.
- Use the returned `name` as `type` and `version` as `typeVersion`.
- Never use a node that was not returned by the catalog.
- If a planned node was not searched for, stop and search for it before continuing.
- If the catalog does not return a node, choose an alternative approach or tell the user the requested solution is not available.
- Before generating the workflow JSON, confirm every planned node appears in the catalog results.
- Custom/SAP nodes (e.g. `CUSTOM.approvalTask`) include full `properties` in the output to help you configure them correctly.

> **Node & routing selection — decide here, before writing any node.** The sections below are the authoritative decision gates. Critical Rules enforce these decisions as pre-write checks rather than restating them.

### **MANDATORY: Setup the multi-asset solution**

**Asset creation policy**: 
- When the workflow includes a `CUSTOM.sapAgent` node, determine whether the target is a new or existing agent.
   - If the user confirms a new agent, include a new agent asset in the solution.
   - NEVER fabricate/hallucinate agent ordId or agent name values. If no agent is specified, leave the SAP Agent node unconfigured: set `"agentName": ""` and `"agents": "[]"` on the SAP Agent node.
   - If the user confirms an existing agent, leave the selection for the user in the n8n editor and add a `n8n-nodes-base.stickyNote` node directly above the SAP Agent node.
   - **Fast Track mode (user did not specify):** do NOT create an in-solution agent asset, if user didn't specify it explicitly. Only set `"agentName": ""` and `"agents": "[]"` on the SAP Agent node, and add a sticky note.
   - When a sticky note is required, use this content: "⚠️ Agent not configured — select the target agent in this node before deploying the workflow."
- When the workflow or agent reads SAP or LOB data and no existing external agent covers that data access, a new MCP server asset MUST be part of the solution. Never silently skip asset creation — when uncertain, ask.

1. Identify any `CUSTOM.sapAgent` or `CUSTOM.sapMcpClient` nodes in the workflow.
2. Run the `setup-solution` skill (if not already done), passing the node types from step 1 — follow the **Example 1: Multi-Asset Solution (Agent + n8n Workflow + MCP Server)** in that skill.
3. If the workflow contains `CUSTOM.sapAgent` nodes:
   - **If the solution has agents:** read each agent's `asset.yaml` to collect `provides.apis[].name` and `provides.apis[].ordId`. Derive the agent ORD ID by replacing `apiResource` with `agent` (e.g. `customer.build:apiResource:...:v1` → `customer.build:agent:...:v1`). Populate the `agents` parameter on every SAP Agent node with the full list using these names and derived ORD IDs. Follow the `agents` and `agentName` parameter shapes defined in `n8n-sap-agent.md`.
   - **If no agents exist in the solution: Add a sticky note above each SAP Agent node, that is left unconfigured.

#### Trigger node requirement

**Every workflow MUST have at least one Webhook trigger node.** Never generate a workflow whose only trigger is a Manual Trigger node. A Manual Trigger may coexist alongside a Webhook trigger as a secondary entry point, but a Webhook trigger is always required. If the prompt does not describe a trigger, either ask the user to define the Webhook behavior or generate a clearly named placeholder Webhook trigger and note that it should be refined.

#### Runtime capabilities & the "parallel" question — read first, decide once

**No sub-workflows.** This n8n instance does not support sub-workflow / Execute-Workflow calls. Everything runs inside one workflow.

When a prompt says "parallel", "in parallel", "work on each item", "concurrently", or "fan out", it means **n8n per-item iteration or branch fan-out within this one workflow** — never a separately executing sub-flow. Do not stall trying to decide whether the user wants "true" concurrency; this runtime does not support it. Instead use one of these:

- **Default shape for a list arriving in a webhook body:** `Webhook → Split Out(body.<array>) → per-item nodes → Aggregate`. Per-item nodes run once per item automatically — that IS the "parallel" processing here. See Rule 12.
- **Loop Over Items, Merge, and IF/Switch branches are all available and behave normally.** Use them per **Rule 8 — Branch convergence**. "Parallel" does not forbid them and does not require them.
- **Prefer default per-item iteration.** Only reach for the Loop Over Items node for genuine batching, rate limiting, or stateful iteration (see `n8n-loops`). Do not add it just to "wait for all items" — default iteration already does that.

**Canonical skeleton for "process a list from a webhook body"** (a shape to reason from, not a template to copy — fill the `<…>` roles from the actual prompt; drop the second pass if the task needs only one):

```
Webhook
  → Split Out(body.<array>)
  → <per-item transform>            (e.g. compute a derived field; runs once per item)
  → Aggregate                       (collect items into one array; add a summary/total with executeOnce)
  → [only if a second per-item pass is needed:]
      Split Out → IF/Switch(<condition>) → <per-branch transform> → Aggregate
  → <finalize>                      (executeOnce; build the response payload)
  → Respond to Webhook
```

Exclusive IF/Switch branches in the second pass connect **directly** to the following Aggregate (Rule 8, case 1) — no Merge.


#### SAP node selection — deterministic vs. reasoning

**Use an SAP MCP Client node for:**
- Any deterministic API call to SAP systems (fetch, create, update, post).
- Operations with a known endpoint and parameters.
- Before generating, verify the required MCP translation card exists. If missing, flag it for generation.

**Use an SAP Agent node for:**
- Analysis based on thresholds, patterns, or business rules.
- Content generation requiring context (emails, summaries, recommendations).
- Decision-making with open-ended reasoning.
- Multi-step problem solving where dynamic tool selection is needed.

**Separation requirements:**
- Keep deterministic API calls (MCP Client nodes) and reasoning (SAP Agent nodes) in distinct workflow nodes. Do not embed data fetching logic inside agent definitions.
- Pattern: `MCP Client (fetch) → SAP Agent (analyze) → MCP Client (action)`.
- Any step that creates, updates, posts, notifies, or otherwise causes a durable side effect in SAP MUST be a `CUSTOM.sapMcpClient` node. A `n8n-nodes-base.set` node only stores data in n8n memory — it does not contact SAP, so it is never an SAP action.
- For read-only analysis workflows, a terminal formatting or response-shaping node is acceptable when no SAP write-back is requested.

#### External API integration order

Choose the integration pattern in this order:

1. **Use a dedicated n8n node** when one exists for the target service.
   - Example: Use the Outlook node to send email.

2. **Use the `n8n-sap-mcp-client` skill** for SAP systems and SAP services.
   - Example: S/4HANA, SAP BTP services exposed through MCP.

3. **Use an MCP server wrapper plus the `n8n-sap-mcp-client` skill** for custom LOB systems or internal APIs.
   - Example: Legacy systems, internal databases, custom services.

#### SAP Node Detailed Rules

SAP Nodes are the default choice whenever they cover the requested capability. Use generic n8n nodes only when no SAP Node exists for that use case.

##### Subskill Routing

Analyze the user prompt and invoke the relevant SAP subskills. The table below maps signals to subskills. When in doubt, prefer the SAP subskill first and let the catalog lookup confirm availability.

| Signal type | Examples | Action |
|-------------|----------|--------|
| Strong SAP-specific signals | `SAP Task Center`, `SAP AI Core`, `SAP Agent`, `SAP MCP Client`, `S/4HANA` | Invoke the matching subskill (`n8n-sap-task-center`, `n8n-sap-ai-core`, `n8n-sap-agent`, `n8n-sap-mcp-client`) |
| Contextual SAP workflow signals | `purchase requisition in S/4HANA`, `SAP sales order`, `SAP invoice extraction`, `approval in SAP Task Center`, `SAP agent orchestration`, `extract with SAP AI Core` | Invoke the matching subskill |
| Ambiguous terms that match a SAP capability | `AI`, `LLM`, `chat`, `analyze`, `agent`, `approval`, `invoice`, `purchase requisition`, `sales order`, `task` (without explicit non-SAP context) | Invoke the matching SAP subskill by default; the catalog lookup will confirm whether the node is available |

**Mapping table:**
- **SAP Task Center** → `n8n-sap-task-center` skill (mandatory Switch node pattern after Task Center)
- **SAP AI Core** → `n8n-sap-ai-core` skill (NEVER use OpenAI/Gemini, only SAP AI Core nodes)
- **SAP Agent** → `n8n-sap-agent` skill (SAP Agent node configuration and credentials)
- **SAP MCP Client / S/4HANA** → `n8n-sap-mcp-client` skill (NEVER use HTTP Request for SAP, use MCP Client)

**Example:** User prompt "Create workflow with SAP Agent for approval escalation"
→ Detected strong signals: "SAP Agent", contextual signal: "approval escalation"
→ MUST invoke: `n8n-sap-agent`, `n8n-sap-task-center`
→ Read and follow ALL rules from both skill files

#### Routing node selection — deterministic vs. Agent

Decide the routing node type here; Critical Rule 11 enforces this decision as a pre-write gate. Before generating any conditional or routing node, determine whether the decision is fully defined in the prompt:

- **Fixed rule from the prompt** (expressible from information already present in the prompt or conversation) → IF node or Switch node.
- **Free-text, unstructured, or judgment-based input** that no fixed rule can capture → Agent node.
- **Neither applies** — the rule is not defined and the input is structured or of a known, bounded type → choose a reasonable default, **explicitly state the assumed value in your response**, and continue generating so the user can review or correct it before activation. Stop and ask only when no reasonable default exists and the routing structure would be materially wrong without it.
- **User explicitly requests AI-based routing** → use an Agent node for the inference step and a Switch/IF node to route on its structured output. This combination is intentional — the Agent infers, the IF/Switch routes on the result.

### **MANDATORY: Create the file in the filesystem**
Write workflow files to `assets/workflows/<workflow-name>/` only. The file **MUST** use the `.n8n.json` extension (for example, `morning-email-workflow.n8n.json`). NEVER use MCP to create or update workflow files.

Every workflow JSON **MUST** include a `"description"` field at the top level that accurately summarises what the workflow does. When editing an existing workflow, update the `"description"` to reflect any changes made.

### **MANDATORY: Credential policy — never embed instance-specific credentials**
Generated workflow JSON must **never** contain instance-specific credential IDs or names. Credentials are instance-specific and are resolved automatically during solution deployment. No input from the user is required.

For every node that requires authentication, omit the `credentials` field entirely. Do not embed credential IDs, names, or placeholders.

If validation reports a missing credential error, that is expected and acceptable.

### **MANDATORY: Generate workflow ordId and API ORD IDs**
After the workflow JSON file is written, run the following script to generate the `workflow` block and `provides.apis[]` entries for `asset.yaml`:

```bash
node scripts/generate-workflow-asset.js assets/workflows/<workflow-name>/<workflow-name>.n8n.json <workflow-name> <solution-name>
```

Example:
```bash
node scripts/generate-workflow-asset.js assets/workflows/leave-request/leave-request.n8n.json leave-request-workflow my-solution
```

Example output:
```yaml
workflow:
  definitionFile: leave-request.n8n.json
  name: leave-request-workflow
  ordId: sap.btpn8n:apiResource:ManagedN8nMcpServer:v1

provides:
  apis:
    - name: leave_request_submitted
      path: /my-solution-3f8a1/leave-request-workflow/leave-request-submitted
      kind: rest
      description: <add description>
      ordId: sap.n8nwfrt:apiResource:my-solution-3f8a1_leave-request-workflow.leaveRequestSubmitted:v1
    - name: leave_request_submitted_mcp_server
      kind: mcp-server
      description: MCP server for leave request submitted operations
      ordId: sap.n8nwfrt:apiResource:my-solution-3f8a1_leave-request-workflow.leaveRequestSubmittedMcpServer:v1
```

Paste the output verbatim into `asset.yaml`. The only field to fill in is the `description` value for each `kind: rest` entry — write a one-sentence description of what each webhook does based on the workflow context. The script also rewrites each webhook node's `parameters.path` to the full path `<solution-name>/<workflow-name>/<operation>` (matching `provides.apis[].path` without the leading slash) so the runtime appends it to the tenant URL as-is — no webhook URL is generated at deploy time. Do not hand-edit either path.

The script also writes a `workflow-schema.openapi.json` sidecar next to the workflow file — a best-effort **OpenAPI 3.1** skeleton (one `post` per `kind: rest` webhook, keyed by the webhook path, with a `requestBody` and a `200` response). Written only when absent; `asset.yaml` carries no schema data.

### **MANDATORY: Refine `workflow-schema.openapi.json` now**

The skeleton has coarse `string` types, no `required`, and `<...>` placeholders — you **MUST** refine it before continuing:

1. For each operation, replace the `summary`/response `description` placeholders and fix the `requestBody`/response field types (`integer`/`boolean`/`array` with `items`/nested `object`), adding `enum`/`format`/`required` as needed.
2. Keep it valid: `openapi: "3.1.0"`, every `paths` key identical to its `provides.apis[].path`, `$ref`s `#/`-local. Only the request body is derived — add any `?query`/`:path` params as OpenAPI `parameters` (`in: query`/`in: path`) yourself.
3. **Align every IF/Switch condition operator with the refined body types.** Treat this sidecar's `requestBody` schema as the authoritative type for every `$json.body.<property>` reference. For each condition in an `n8n-nodes-base.if` or `n8n-nodes-base.switch` node whose `leftValue` reads a body property, the condition `operator.type` **MUST** match the property's schema `type`:
   - schema `string` → `operator.type: "string"` (`contains`, `equals`, `startsWith`, …)
   - schema `integer`/`number` → `operator.type: "number"` (`gt`, `gte`, `lt`, `equals`, …)
   - schema `boolean` → `operator.type: "boolean"` (`true`/`false`)
   - schema `array` → `operator.type: "array"`; schema `object` → `operator.type: "object"`

   A mismatch — e.g. a `number` operator (`gte`) comparing a property typed `string` in the schema, or a `string` operator (`contains`) on an `integer` field — is a defect. Fix it by either correcting `operator.type` to match the schema, or correcting the schema `type` if the schema is wrong (the schema and the condition must agree). Keep `conditions.options.typeValidation: "strict"` so a residual mismatch fails loudly at runtime rather than coercing silently.
4. `Write` it back and verify no `<...>` placeholder or wrong `string` type remains.

Hard gate: a sidecar still containing a `<...>` placeholder or all-`string` fields is incomplete. A sidecar whose body property types disagree with any IF/Switch condition operator that reads them is also incomplete.

If the workflow has **no** webhook nodes, the script outputs only the `workflow:` block — the `provides.apis[]` block is omitted from `asset.yaml` and no `workflow-schema.openapi.json` is written (skip this refine step).

### **MANDATORY when applicable: Generate MCP server for in-solution agent consumption**

**Evaluate all three conditions below right now — before moving to the next section.** If all three hold, this step is **required**; skipping it leaves the solution incomplete and non-functional.

1. The solution contains at least one agent asset — check `solution.yaml` for a `ref:` entry pointing to an `asset.yaml` with `type: agent`.
2. The workflow is triggered by a webhook — it has an `n8n-nodes-base.webhook` node as its entry point (trigger). A webhook node used elsewhere in the workflow, not as the trigger, does not count. The script above will have produced a `provides.apis[]` block two entries: a `kind: rest` entry and a corresponding `kind: mcp-server` entry when this is the case.
3. The specification (intent.md, PRD, tasks.md, or the agent's own specification) indicates the agent should call, trigger, or invoke this workflow in any way. The MCP wrapping is an infrastructure detail added by IBD — the spec does not need to mention MCP explicitly.

If all three conditions hold, **complete Steps A–F before continuing**. If any condition is not met, skip this step entirely.

#### Step A — Generate the OpenAPI spec

Run the script and redirect its output to the folder that the `mcp-translation-file` skill expects:

```bash
mkdir -p specification/<workflow-name>-mcp-server/api-specs
node scripts/generate-webhook-openapi.js \
  assets/workflows/<workflow-name>/<workflow-name>.n8n.json \
  <workflow-name> \
  > specification/<workflow-name>-mcp-server/api-specs/<workflow-name>-webhook-api.json
```

If the script outputs `{}` (no webhook nodes), abort Steps A–F — there is nothing to expose as an MCP server.

#### Step B — Prepare the `mcp-translation-file` skill prerequisites

The `mcp-translation-file` skill requires a `specification/<asset-name>/specification.md` whose content references an API integration. Create the file if it does not already exist:

File: `specification/<workflow-name>-mcp-server/specification.md`

```markdown
# <workflow-name>-mcp-server MCP Translation

## Tasks

- Generate MCP translation for webhook API integration with ORD ID `<rest-api-ordId>`.
```

Replace `<rest-api-ordId>` with the value from `provides.apis[].ordId` where `kind: rest` in `assets/workflows/<workflow-name>/asset.yaml` — the value that `generate-workflow-asset.js` produced in the previous step.

#### Step C — Run the `mcp-translation-file` skill

Invoke the `mcp-translation-file` skill with asset name `<workflow-name>-mcp-server`. The skill will:

- Locate the API spec at `specification/<workflow-name>-mcp-server/api-specs/<workflow-name>-webhook-api.json`
- Resolve the ORD ID from `specification/<workflow-name>-mcp-server/specification.md`
- Write output files to `specification/<workflow-name>-mcp-server/mcps/<workflow-name>-webhook-api/`

After the skill completes successfully, copy the generated files into the MCP server asset folder so they ship with the deployable asset:

```bash
mkdir -p assets/<workflow-name>-mcp-server/mcp-translation
cp specification/<workflow-name>-mcp-server/mcps/<workflow-name>-webhook-api/translation.json \
   assets/<workflow-name>-mcp-server/mcp-translation/translation.json
cp specification/<workflow-name>-mcp-server/mcps/<workflow-name>-webhook-api/api-spec.json \
   assets/<workflow-name>-mcp-server/mcp-translation/api-spec.json
```

#### Step D — Create the mcp-server `asset.yaml`

Write `assets/<workflow-name>-mcp-server/asset.yaml`. The MCP card ORD ID (`<mcp-card-ordId>`) must be derived from the REST ORD ID using the ADR-021 §8.1 convention:

1. From the workflow's `asset.yaml`, find the `provides.apis` entry where `kind: rest`. Use **only this entry** — do **not** use the `kind: mcp-server` entry that the workflow script also generates (it uses a different `McpServer` camelCase suffix and serves a different purpose).
2. Take that REST entry's `ordId` and append `_mcp` to the `apiName` segment (the part between the last `.` and `:v1`).

Example derivation:
- REST ORD ID (from workflow asset.yaml, `kind: rest`): `sap.n8nwfrt:apiResource:my-solution_leave-request-workflow.leaveRequestSubmitted:v1`
- MCP card ORD ID: `sap.n8nwfrt:apiResource:my-solution_leave-request-workflow.leaveRequestSubmitted_mcp:v1`
- **Wrong** (do not copy): `sap.n8nwfrt:apiResource:my-solution_leave-request-workflow.leaveRequestSubmittedMcpServer:v1` ← this is the workflow's own `kind: mcp-server` entry; ignore it here

```yaml
apiVersion: asset.sap/v1
kind: Asset
type: mcp-server

metadata:
  name: <workflow-name>-mcp-server
  version: "1.0.0"
  translation: mcp-translation/translation.json
  apiSpec: mcp-translation/api-spec.json

requires:
  - name: <webhook-snake-name>        # snake_case of the webhook node name
    kind: api
    ordId: <rest-api-ordId>           # provides.apis[].ordId where kind: rest

provides:
  apis:
    - name: <webhook-kebab-name>-mcp-server
      kind: mcp-server
      description: MCP server for <workflow-name> webhook operations
      ordId: <mcp-card-ordId>         # REST ORD ID with _mcp appended to apiName segment (see derivation above)
```

If the workflow has **multiple** webhook nodes, add one `requires` entry and one `provides.apis` entry per webhook node, deriving each `<mcp-card-ordId>` from its corresponding `kind: rest` entry.

#### Step E — Update `solution.yaml`

Add the new mcp-server asset reference to `solution.yaml`:

```yaml
  - ref: ./assets/<workflow-name>-mcp-server/asset.yaml
```

#### Step F — Update every agent's `asset.yaml`

Find all agent assets in the solution:
1. Read `solution.yaml`.
2. For each `ref:` entry, read the target `asset.yaml`.
3. Collect every asset whose `type` field equals `agent`.

For each agent found, add a `requires` entry to its `asset.yaml` **only if** the specification (intent.md, PRD, tasks.md, or the agent's own specification) indicates that this agent should call, trigger, or invoke this workflow. Merge with any existing `requires` entries — do not overwrite them.

```yaml
requires:
  - name: <workflow-name>-mcp-server
    kind: mcp-server
    ordId: <mcp-card-ordId>           # same value as in Step D (REST ORD ID with _mcp appended to apiName)
```

Then update `app/agent.py` in the same agent directory to instruct the agent to use the MCP tool rather than calling the webhook URL directly. Append a sentence to the system prompt such as:

> To invoke the `<workflow-name>` workflow, use the `<tool-name>` MCP tool. Do not call workflow webhook URLs directly.

Derive `<tool-name>` from the MCP card ORD ID: take the `apiName` segment (e.g. `leaveRequestSubmitted_mcp`), then strip the `_mcp` suffix → `leaveRequestSubmitted`. The agent directory is the folder that contains the `asset.yaml` identified in step 2 above.

If no agent assets are found in `solution.yaml`, skip this step.

### **MANDATORY: Fetch pinData schemas and embed sample pinData**
Before validation, populate the workflow's top-level `pinData` object with sample data for every node whose schema can be served by the SAP pinData library. This must happen inside the same in-memory JSON that will be validated and written — never as a follow-up edit.

Required steps:
1. Build the input list from the catalog results already obtained in the "Look up nodes from the catalog" step:
   - Include **every** node type used in the workflow — both SAP (`CUSTOM.*`) and generic (`n8n-nodes-base.*`). Do not pre-filter; the tool moves non-SAP entries into `notFound` on its own.
   - Deduplicate by `type`, and use the exact `typeVersion` that `search-nodes-catalog` returned for each.
2. Call the `pin-data-schemas` MCP tool once with the full list:
   ```json
   { "nodes": [ { "type": "CUSTOM.sapMcpClient", "typeVersion": 1 }, { "type": "n8n-nodes-base.webhook", "typeVersion": 2 } ] }
   ```
3. For every entry in the returned `schemas` object, find each node in the workflow whose `type` matches. For each match, synthesize **one** sample item that conforms to the returned JSON Schema (respect `required`, `type`, `enum`, `format`; use plausible placeholder values) and add it under `pinData[<node.name>]` as a single-element array. If the same `type` appears on multiple nodes, generate a separate sample object for each node — never share a reference across nodes.
4. Entries in `notFound` are expected:
   - `reason: "non-sap"` → generic n8n nodes; skip silently.
   - `reason: "no-schema"` → SAP node not yet in the library; skip silently.
   - `reason: "duplicate-type"` → already handled from a prior `schemas` entry; skip silently.
   - `reason: "version-mismatch"` → keep the `typeVersion` from the catalog (it drives the node's real behavior); do **not** downgrade to `closestVersion`. Skip the pinData entry for this node.
5. Merge the resulting object into the workflow's top-level `pinData` field, replacing any `pinData: {}` placeholder. Only include entries for nodes actually present in the workflow.
6. If the workflow has zero nodes, skip the tool call.

**On edits to an existing workflow:** Still call `pin-data-schemas` — the fetch is unconditional so the model always has fresh schemas for every node type currently in the workflow. Then reconcile with the existing `pinData` before writing:
- Read the current top-level `pinData` from the in-memory workflow.
- Keep every existing `pinData[<name>]` entry whose node is still present and whose `type` and `typeVersion` are unchanged. Do not re-synthesize over user-provided or previously pinned sample data.
- If a node was renamed (its `name` changed but `type` and `typeVersion` are the same), move the existing `pinData` entry from the old key to the new `name` rather than dropping and re-synthesizing.
- Delete `pinData[<name>]` entries whose node was removed from the workflow.
- Only synthesize new sample data (using the schemas from the `pin-data-schemas` call above) for nodes that (a) are new to the workflow, (b) had their `type` or `typeVersion` changed, or (c) previously had no `pinData` entry.

Example — a workflow with an SAP MCP Client node named `Get Blocked Invoices (S/4HANA)`:
```json
"pinData": {
  "Get Blocked Invoices (S/4HANA)": [
    {
      "mcpServer": { "globalTenantId": null, "name": "S/4HANA Cloud", "ordId": "sap.s4:apiResource:supplier-invoice:v1" },
      "requestId": "req-test-001",
      "result": { "content": [{ "text": "Retrieved 2 blocked invoices", "type": "text" }], "isError": false, "structuredContent": { "invoices": [] } }
    }
  ]
}
```

### **MANDATORY: Validate the workflow**
**Pre-validation gate:** Before running the validator, confirm that the MCP server step was handled. If the three conditions in the ["MANDATORY when applicable"](#mandatory-when-applicable-generate-mcp-server-for-in-solution-agent-consumption) section above all hold — verify that `assets/<workflow-name>-mcp-server/` exists with a valid `asset.yaml`. If it does not exist, **stop and complete Steps A–F now** before continuing.

Before writing the workflow file, validate the fully constructed workflow JSON with the `validate-n8n-workflow` MCP tool, following the rule above. Pass two arguments: `workflow` — the full workflow JSON serialized as a string — and `assetYaml` — the contents of the workflow's `asset.yaml` (at `assets/workflows/<workflow-name>/asset.yaml` under the solution root) read as a YAML string. If validation returns errors, fix the workflow before writing it. Some errors are expected and cannot be fixed by the agent — for example, credentials with `"id": "MISSING"`. In those cases, inform the user and leave the credential configuration to be done manually in the n8n UI.

---

## Critical Rules

Construct the entire final JSON in memory first, then apply each pre-write check defined below, in order:

- **Topology and execution**
   - every node must be reachable from a trigger,
   - every branch convergence follows the single **Branch convergence** decision in Rule 8 (Merge for independent branches that both run; direct connect for exclusive IF/Switch branches),
   - every execution path must fulfill the caller contract,
   - webhook trigger and Respond to Webhook are mode-consistent — if a `respondToWebhook` node is reachable, the webhook trigger sets `responseMode: "responseNode"`; if `responseMode: "responseNode"`, every reachable path reaches a respond node (see the `responseMode` decision table in `n8n-trigger-nodes-webhook.md`),
   - every routing step is grounded — no invented thresholds or fabricated rules,

- **Code node conventions**
   - every user-provided configuration constant is named in ALL_CAPS and placed at the top of its Code node,
   - every Code node with a user-provided configuration constant has a sticky note directly above it,

- **Validation and metadata**
   - `pinData` has been fetched via `pin-data-schemas` for every node type used and reconciled with the current node set (kept, renamed, re-synthesized for new or changed nodes), then merged onto the workflow's top-level `pinData` field,
   - validate with `validate-n8n-workflow`.

   Then write once. This applies equally to new files and edits to existing ones.

### Rule 1 — No environment variables
**NEVER use n8n environment variables** (e.g. `$env.MY_VAR`, `={{ $env.SOME_VALUE }}`) in any generated workflow JSON → use placeholder URLs like `https://your-sap-system.com/api`.

### Rule 2 — SAP Custom Nodes take priority
**Always use SAP Custom Nodes when one exists for the required capability. Never substitute it with a generic core node.** See the [Subskill Routing mapping table](#subskill-routing) for the full capability-to-node mapping. If no SAP Node exists for the requested capability, document that outcome and only then fall back to an appropriate generic node.

### Rule 3 — Separate deterministic calls from agent reasoning
**Separate deterministic API calls from agent reasoning.** MCP Client for deterministic SAP calls, SAP Agent for reasoning; Set nodes are never SAP actions. See the [SAP node selection](#sap-node-selection--deterministic-vs-reasoning) rules above for the full decision.

### Rule 4 — File location and extension
**ALWAYS** use `.n8n.json` extension and write to `assets/workflows/<workflow-name>/`

### Rule 5 — Response content
**DO NOT explain credentials, deployment, or setup steps in your response.** The n8n platform automatically detects missing credentials when the workflow is imported and prompts users via its UI. Mentioning this in your response is redundant and creates noise. Keep your response focused on what was created — not what the user needs to do next.

   After stating where the workflow was created, you may optionally include a business-facing summary that describes:
    - The workflow's purpose and trigger
    - The business roles involved
    - Key decisions and outcomes
    - Any non-obvious design choice, explained as a business reason (e.g. "human review can take time, so the submitter receives the outcome whenever the decision arrives") — not the technical mechanism

   Keep this summary focused on the business process only. Do not include:
    - Credentials
    - Node names
    - Deployment steps
    - Webhook URLs
    - n8n UI instructions
    - Operational prerequisites
    - Communication protocols or interaction patterns between systems

   You may name external systems once (e.g. "S/4HANA", "SAP Task Center") without describing how the systems interact.

   When the workflow includes a human-in-the-loop step, describe it in business terms only. Example: "The workflow pauses for approval. The manager receives a task to review and, once they respond, the process continues automatically."

### Rule 6 — Catalog verification before any node
**STOP. Before planning or writing any node, verify it exists in the catalog.** Only use nodes returned by `search-nodes-catalog`. Never generate a node from base n8n training knowledge — if the search tools did not return it, do not use it. This applies to both new workflows and edits to existing ones.
    - **New workflows:** If a planned node is not returned by the search tools, do not use it. Find a workaround using nodes you can use and rewrite the plan.
    - **Editing existing workflows:** Check all nodes in the existing file — not just the ones being added or changed. If a node that was not returned by the search tools is already present, do not silently preserve it. Instead, remove it and Inform the user: "This workflow contained the [display name] node, which was not supported in the current version. It was removed." Then proceed with the requested edits using only catalog-confirmed nodes.

### Rule 7 — Every node reachable from a trigger
**Every node must be reachable from a trigger.** Every executable path in the workflow must be reachable from at least one trigger node.

   Treat a node as a trigger when it is a known trigger-type node. As a naming heuristic, its `type`, lowercased, usually:
   - ends with `trigger`, or
   - ends with `.webhook`

   Do **not** treat response or action nodes such as `n8n-nodes-base.respondToWebhook` as triggers, even if they are related to webhook flows.

   Examples:
   - `n8n-nodes-base.webhook` → trigger
   - `n8n-nodes-base.respondToWebhook` → not a trigger

   Before writing the final workflow JSON, traverse the `connections` graph from each trigger and confirm that every non-trigger node is visited. If any node is unreachable, re-derive its intended role in the execution graph from the user's original prompt and reconnect it before writing.

### Rule 8 — Branch convergence: one decision for Merge vs. direct connect
**This is the single, authoritative rule for what to put where two or more edges reach the same downstream node.** It supersedes any Merge/NoOp/convergence advice in the n8n reference bundles (`n8n-expressions`, `n8n-loops`) and the SAP subskills — those are instances of this rule, not separate rules. Applies to caller-based workflows (those triggered by `n8n-nodes-base.webhook`).

Route by **what created the branches**:

1. **Exclusive branches — only one fires per item** (the two outputs of an IF node, or the outputs of a Switch). These never both run for the same item, so there is nothing to synchronize.
   → **Connect each branch directly to the shared downstream node (Aggregate, the next step, or a loop's feedback edge). NO Merge. NO NoOp.**
   → Adding a Merge here **deadlocks**: `waitForAll` waits forever for the branch that did not fire.
   → This includes **exclusive IF/Switch branches feeding a Loop Over Items feedback edge** — connect them directly.

2. **Independent branches that both fan out and both run**, then reconverge on a shared node whose *single* execution matters — e.g. one `respondToWebhook`, or several `CUSTOM.sapMcpClient` calls that must all complete before responding.
   → **A Merge node (`mode: waitForAll`) is required** before the shared node.
   → Without it, each branch triggers the shared node independently: for `respondToWebhook` the first response wins and the rest error; for other nodes you get duplicate execution or missing data.
   → The Merge need not be the direct predecessor of the shared node; intermediate nodes are allowed.

**Exception:** independent branches that terminate separately are not a convergence and need no Merge.

**NoOp / Set at a convergence is NOT a control-flow requirement.** A NoOp (or Set) at a merge point exists only for *reference stability* — giving downstream a stable `$('Name')` to read when a later-inserted intermediate would otherwise break `$json`. That is an expression concern (see `n8n-expressions/n8n-expressions.md`), not a substitute for, or addition to, the Merge decision above. Do not add a NoOp to "make branches converge."

**Note on downstream expressions:** After a Merge node, `$json` refers to the merged output, not to a specific upstream branch. To read data from a particular upstream node, use `$('Node Name').item.json.field`, but only when that node is guaranteed to have produced data on the current execution path. If a field is created after the Merge on the unified path, use `$json`.

### Rule 9 — Every execution path fulfills the caller contract
**Every execution path must fulfill the caller contract.** This rule applies only to caller-based workflows (see rule 8). These trigger types imply a contract: the caller expects a result regardless of which execution path is taken. Every path reachable from the trigger must contain at least one node that fulfills this contract.

   The preferred fulfillment is an explicit response to the caller via `n8n-nodes-base.respondToWebhook`. Other durable side effects (sending a notification, writing to a datastore, calling an external service) may be acceptable when an explicit response is not possible or appropriate, but they should not be used as a substitute where a direct response is expected.

   Requirements:
   - A Switch node in rules mode must define a fallback output so unmatched items continue on a valid path — without it, unmatched items follow a path with no nodes at all, silently dropping the caller contract.

### Rule 10 — Structure user-provided configuration as a named constant block
**Structure user-provided configuration as a named constant block.** When a Code node contains data that the user supplied directly in the prompt — such as routing tables, decision matrices, threshold sets, policy mappings, or reviewer assignments — structure it as a named constant block:

   Required:
   - Define a single ALL_CAPS constant for the configuration data (e.g. `ROUTING_TABLE`, `APPROVAL_THRESHOLDS`).
   - Place the constant at the top of the node, before any logic.
   - One entry per line so individual values are easy to locate and change.
   - Keep all data values inside the constant block. Do not scatter magic numbers or strings through the logic.
   - Add a sticky note directly above the Code node.

   Example (JavaScript mode):
   ```javascript
   const ROUTING_TABLE = {
     "CC1000": "approver.a@example.com",
     "CC2000": "approver.b@example.com",
   };
   ```

   For each Code node that contains a user-provided configuration block, add a `n8n-nodes-base.stickyNote` node directly above it. Position it so it does not overlap any other node: place it at the same x as the Code node, choose a width wide enough to display the text without clipping, choose a height tall enough to show the full content, and set y so there is a small gap between the bottom of the note and the top of the Code node.

   Use this sticky note content:

   > This configuration is hardcoded — the values in this node reflect what you provided. If this data is maintained in a connected system, replace this node with a live lookup when that integration is available. For now, update the values in this node directly when they change.

### Rule 11 — Ground every routing step before generating
**Ground every routing step before generating.** The routing node type (IF/Switch vs. Agent) is decided in the [Routing node selection](#routing-node-selection--deterministic-vs-agent) section above — this is the pre-write enforcement gate for that decision. Before writing any conditional or routing node, confirm it follows that decision and that every rule is grounded in the prompt. Never fabricate routing logic — invented thresholds, keyword scoring, or any rule not grounded in the prompt creates workflows with unapproved behavior and increases the risk of incorrect runtime decisions.

**Type-align every IF/Switch condition with the refined schema.** When a condition's `leftValue` reads a `$json.body.<property>`, its `operator.type` MUST match that property's type in the refined `workflow-schema.openapi.json` sidecar — see step 3 of [Refine `workflow-schema.openapi.json`](#mandatory-refine-workflow-schemaopenapijson-now). A `number` operator on a `string` field (or vice versa) is a defect; make the schema and the condition agree and keep `typeValidation: "strict"`.

**Apply the same rule to all other field sources — Code node outputs, Set node outputs, HTTP responses, and any expression.** `operator.type` MUST match the actual JavaScript type of the value. A boolean (`errors.length === 0`, `true`, `false`) MUST use `operator.type: "boolean"` — never `operator.type: "string"` with `rightValue: "true"`.

### Rule 12 — Webhook body access
**Webhook node wraps the POST body — always access data via `$json.body.*`, never `$json.*` directly.** The `n8n-nodes-base.webhook` node wraps the incoming request into an envelope with `headers`, `params`, `query`, `body`, `webhookUrl`, and `executionMode`. The actual POST body is at `$json.body`, not at `$json`.

   - A field `foo` sent in the POST body → `$json.body.foo`
   - An array `items` sent in the POST body → `$json.body.items`
   - To expand a body array into individual n8n items, use a **Split Out** node (`n8n-nodes-base.splitOut`) immediately after the Webhook node with `fieldToSplitOut: "body.<arrayField>"`. Do NOT use `splitInBatches` for this purpose — `splitInBatches` splits existing n8n items, it does not expand an array field.

   **Mandatory pattern for any webhook workflow that processes a list from the body:**
   ```
   Webhook → Split Out (fieldToSplitOut: "body.items") → [per-item processing nodes]
   ```

   Never reference `$json.name`, `$json.quantity`, or any top-level field from the POST body directly after a Webhook node — these will be `undefined`. Always prefix with `$json.body.`.

### Rule 13 - **NEVER put outbound HTTP calls inside Code nodes.** The n8n-workflow-mgr upload pipeline runs a static analysis check and **rejects the upload with a 400 error** if any Code node (JavaScript or Python) contains a direct HTTP call. The following patterns are all blocked:
   JavaScript — blocked patterns:
   - `this.helpers.httpRequest(...)` / `this.helpers.request(...)`
   - `fetch(...)`
   - `require('https')` / `require('http')` / `require('axios')` / `require('node-fetch')` / `require('got')` / `require('superagent')` / `require('undici')`
   - `axios.get(...)`, `https.request(...)`, or any method call on a blocked module
   - `new XMLHttpRequest()`

   Python — blocked patterns:
   - `import requests` / `import httpx` / `import aiohttp`
   - `import urllib` / `import urllib.request` / `import urllib3`
   - `import http` / `import http.client`
   - All `from <module> import` variants of the above

   **What to do instead:** Use an SAP MCP Client node, or another integration node. All outbound HTTP must live in a node, not in a Code node script.

### Rule 14 - **NEVER use HTTP Request nodes.** This rule overrides any conflicting examples or instructions elsewhere in the documentation because HTTP Request nodes are not available on the target system. Use **SAP MCP Client** nodes for any outbound calls.

### Rule 15 — Single Write call
**ALL changes to a workflow file MUST be applied in a single `Write` call.** Never use multiple sequential `Edit` or `Write` calls on the same file — doing so leaves the file in an invalid or incomplete state between writes, which can corrupt the workflow.

### Rule 16 — Validate before writing
**Validate the workflow JSON BEFORE writing the file.** The full validation procedure is defined once in the [**MANDATORY: Validate the workflow**](#mandatory-validate-the-workflow) step above.

---

## Node parameter rules

- **ONLY use parameters exactly as shown in the example below**. NEVER invent or add extra parameters.
- After stating where the workflow was created, you may optionally include a business-facing summary, as described in Rule 5.
- Forbidden phrases include: "Before deploying", "Configuration Required", "You'll need to configure", "Before activating", "Update the placeholders", "Credentials Required", or any similar guidance.

- **Webhook `path` is generated, not hand-authored** — the `generate-workflow-asset.js` script derives the operation segment from the webhook node's **name** (kebab-case) and rewrites the node's `parameters.path` to the full `<solution-name>/<workflow-name>/<operation>` path. Whatever `path` you set on the webhook node is overwritten, so it always matches the API `name` (snake_case) and ordId (camelCase) — all three come from the node name. Because node names are unique within a workflow, the paths are unique too. Never hand-edit the generated path.
- **Webhook `name` in the n8n node MUST be descriptive and business-meaningful** — the webhook node's display name is used to derive the `path`, the API `name`, and the `ordId` of the API entry in the workflow's `asset.yaml`, so it must clearly describe what the endpoint does. Use the workflow's business purpose (e.g. "Prime Number Calculator", "Array Sorter", "Leave Request Submitted", "Blocked Invoice Received"), NEVER generic technical terms like "Webhook", "API", or "Endpoint".
- **SAP Task Center recipients**: At least one recipient target must be configured (`recipients` or `recipientGroups`). For exact parameter shapes, defaults, and naming rules, follow the dedicated `n8n-sap-task-center` skill.

**For SAP Nodes:** All detailed rules (parameters, credentials, patterns) are in the dedicated SAP skills. Always invoke the appropriate skill (`n8n-sap-task-center`, `n8n-sap-ai-core`, `n8n-sap-agent`, `n8n-sap-mcp-client`) as indicated by the routing table above.

**When a new agent is added to the solution:** Read every existing `.n8n.json` workflow file in the solution and update the `agents` parameter on every `CUSTOM.sapAgent` node to include the new agent. Every SAP Agent node must always reflect the full list of solution agents. Follow the `agents` and `agentName` parameter shapes defined in `n8n-sap-agent.md`.
