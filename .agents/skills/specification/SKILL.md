---
name: specification
description: Generate actionable TODO-list specifications from a PRD, intent.md, or direct user prompt. Produces specification/ folder with per-asset checklists. Route here when the user explicitly asks for a specification or says "do specification directly" (even if they skip intent-analysis). To implement, just say "execute specification/specification.md".
metadata:
  version: 1.0.0
  author: sap-joule-studio
  
---

# Specification Skill

Generate actionable, TODO-list specifications from a Product Requirements Document (PRD), an intent document, or a direct user prompt. Output is a `specification/` folder containing one main spec and one per-asset spec — each a persisted checklist an AI coding agent can execute directly.

## Input Resolution

The skill uses the best available input, checked in this order:

1. **`product-requirements-document.md`** — full PRD with solution category, milestones, requirements. Preferred.
2. **`intent.md`** — lighter intent document from the `intent-analysis` skill. Used if no PRD exists.
3. **User prompt** — direct description of what to build. Used if neither file exists.

When working from intent or user prompt (no PRD), the skill must infer solution category, feature scope, and requirements from the available context. Ask clarifying questions if the input is too ambiguous to determine asset types or key features.

**To implement code:** just say `execute specification/specification.md`.

## Output Structure

```
specification/
  specification.md                            # Master spec — orchestrates all asset specs
  guidelines.md                               # Execution rules (copied from <type> skill, editable)
  guidelines-<type>.md                        # Type-specific constraints (copied once per used type, editable)
  <asset-name>/
    specification.md                          # Per-asset TODO list
    api-specs/                                # (optional) Downloaded API spec files (OData / REST)
    mcp-specs/                                # (optional) Existing MCP server tool schemas
```

Code is generated into `assets/<asset-name>/` when specifications are executed.

## Fast Track Mode

If user request contains "fast track":
- Skip all interactive questions, bypass confirmations
- Generate minimal specification TODO items
- Immediately proceed to execution after generation — do NOT ask the user; autonomously execute `specification/specification.md` by reading it and running all tasks
- Never skip: tests (for agents)

**Fast track = faster workflow, NOT incomplete implementation.**

## A - Writing Specifications

### Step 1: Determine Asset Type
Read the resolved input (PRD → intent → user prompt).
- If a PRD exists, find the `Solution Category` field, and get the relevant `Asset Type`.
- If working from intent or user prompt, infer the category from the description.

Split on commas if multiple. If missing/ambiguous, ask user.

Select a **feature name** prefix (e.g. `purchase-order-approval`).

**Asset name** = `<feature>-<asset-type>` (e.g. `purchase-order-approval-agent`). 

Exceptions:
- **n8n workflows**: use `assets/workflows/<workflow-name>` where `<workflow-name>` is kebab-case (e.g. `assets/workflows/invoice-approval-workflow`).
- **Data products**: the asset name is derived at metadata approval time (Step 1 of the `data-product` skill) as the kebab-case folder name (e.g. `sales-order-analytics-data-product`). Use a placeholder until then.

This naming allows multiple assets of the same type to coexist.

### Step 2: API Discovery (Conditional)

> **CONSTRAINT: APIs must NEVER be consumed directly. No direct HTTP clients (`requests`, `httpx`, OData clients, `fetch`, `axios`, etc.) for any SAP or external API. All API interactions MUST go through MCP tools.**

> **Note:** If the asset includes data products AND the `data-product` skill exists (check `skills/data-product/SKILL.md`), that skill's MCP tools (`dpca-mcp-server__ums_search_data_products` ,`fetch-and-prepare`, `generate-interop`, etc.) cover data product interactions. Still run the sub-steps below for any additional MCP servers or APIs identified in the Fit Gap Analysis. **If Fit Gap rows have a Data Product ORD ID and `—` for both API ORD ID and MCP Server ORD ID, skip Steps 2a and 2b entirely — DPQuery is the only runtime dependency.**

This step covers two sub-cases. Run ones that apply.

#### 2a — MCP server tool discovery

**When to run:** `intent.md` Fit Gap Analysis table has one or more rows with a value in the **MCP Server ORD ID** column.

For each MCP server ORD ID carried over from intent analysis:

1. Call `get_mcp_tools` with the MCP server ORD ID (and the optional `version` if recorded in `intent.md`) to list all available tools (returns name, title, description — no schemas).
2. For each **relevant** tool (relevant to the business challenge / asset being specified), call `get_mcp_tool_details` with the MCP server ORD ID (and the optional `version` if recorded in `intent.md`) and tool name to retrieve the full input/output JSON schema.
3. Save each tool's full schema as a separate file: `specification/<asset-name>/mcp-specs/mcp-spec-<server-name>-<tool-name>.json`. Create directory if needed.
4. The MCP server ORD IDs, versions (if available), tool names, and paths to schema files **must** be included in the per-asset spec TODO items.

#### 2b — OData / REST API discovery

**When to run:** `intent.md` Fit Gap Analysis table has rows with an **API ORD ID** but no corresponding **MCP Server ORD ID** (i.e., a plain REST/OData API with no MCP server).

**Skip** if the agent has zero SAP API touchpoints (pure AI-to-AI, no SAP backend), OR if every required API interaction is already covered by an available MCP server.

For each relevant asset:

1. Call `sap_knowledge_graph_api_discovery` with a concise use-case description as `query`; save the output to `api-discovery-results.md`.
2. For each API in the results:
   - Only `OData` and `REST` are supported types for MCP server generation. Any other `type` value is unsupported.
   - A single ORD ID may appear in multiple discovery entries with different types. Always prefer a supported-type entry; do not inform the user about unsupported variants if a supported one exists for the same ORD ID.
   - Use the **top-level `type` field** to determine the API protocol — not `files[].type`, which only describes the file format. Example: `{ "type": "GraphQL", "files": [{ "type": "OpenAPI JSON" }] }` is unsupported, regardless of the file format listed.
   - If an ORD ID has at least one entry with `type: OData` or `type: REST`, download only that entry and ignore any other variants. If **all** entries for an ORD ID are unsupported types, do not download — treat that ORD ID as having no supported API. Do NOT save stub files for unsupported APIs. Do NOT document limitations or workarounds in the spec — unsupported means unsupported, not "handle differently later".
   - For supported APIs, create `specification/<asset-name>/api-specs/` if it does not already exist
   - Then download each schema with the `jl` CLI and save the raw response as-is using the original file extension.
   ```bash
   jl mcp call ibd-mcp-server sap_knowledge_graph_api_schema_download ordId=<apiOrdId> type=<apiType> fileType=<fileType> > specification/<asset-name>/api-specs/<filename>
   ```
   - sap_knowledge_graph_api_schema_download MUST be used through the jl cli. Calling it directly is NOT allowed.
   - Prefer `EDMX` over `OpenAPI JSON` when both are available.
   - Do not inspect API specification files directly, even partially with commands such as `cat`, `head`, `tail`, or `grep`, because each file is stored as a single line and will exceed the available context window.

3. If discovery returns no relevant results, ask the user to retry with a different query.
4. After filtering unsupported APIs:
   - If at least one supported API remains for each required integration, continue with specification generation.
   - If any required integration has no supported API → **STOP. Do NOT proceed to Step 3. Do NOT write any files.** Tell the user exactly which ORD ID(s) had no OData or REST variant, and suggest checking the SAP Business Accelerator Hub for an alternative API that is OData or REST.

The discovered API names, ORD IDs, and paths to downloaded spec files **must** be included in the PRD-specific tasks in the generated specification. Do **NOT** include raw endpoints, entity sets, key fields, or response schemas — those are consumed exclusively by the `mcp-translation-file` skill, not by agent implementation tasks.

**Also record the MCP tool scope** for each API integration in the per-asset `specification/<asset-name>/specification.md`, so the `mcp-translation-file` skill can prune the generated tool set to what the asset actually needs (the generator emits every endpoint of the API by default). Write one labeled block **per integrated API**, derived from the asset's tasks:

```text
MCP API: <API name or ORD ID>
MCP tool scope: <read-only | read-write>
Resources in scope: <comma-separated resources the tasks touch, or `all`>
```

- `MCP API` identifies which integration the block applies to, so that when an asset integrates multiple APIs each scope is unambiguously tied to the correct one. Use the ORD ID recorded during API discovery.
- `MCP tool scope`: use `read-only` when every task for this asset only lists, reads, queries, or retrieves data. Use `read-write` if any task creates, updates, deletes, or triggers a side-effecting action. (This is protocol-agnostic: the downstream skill maps it to OData CRUD operations or OpenAPI HTTP methods.)
- `Resources in scope`: the API resources the tasks name. The exact term depends on the API type, use whichever the tasks naturally reference, and let the downstream `mcp-translation-file` skill match it structurally:
    - **OData**: entity sets (e.g. `CostCenter, CostCenterText`).
    - **OpenAPI / REST**: resource paths or tags (e.g. `/businesspartners, /addresses`).

    If the tasks genuinely need the full API surface, write `Resources in scope: all` and `MCP tool scope: read-write` to signal no pruning.
- This is a scope *hint*, not raw spec detail: it names capability intent and resources only, never concrete endpoints, parameters, or schemas.

#### 2c — n8n workflow webhook API discovery

**When to run:** Another asset in the current solution (e.g. an agent) needs to invoke an already-deployed n8n workflow via its webhook endpoint. The webhook ORD ID comes from the `intent.md` Fit Gap Analysis **Webhook API ORD ID** column.

**Skip** if no other asset in the solution invokes an n8n workflow, or if the n8n workflow is being built as part of this solution (not pre-existing).

For each webhook to be invoked:

1. Call `get_webhook_api_spec` with the webhook API resource ORD ID from the Fit Gap Analysis. The ORD ID has the form `sap.n8nwfrt:apiResource:<tenant>_<workflow-name>_<path>:v1`.
2. Save the returned spec content to `specification/<asset-name>/api-specs/<workflow-name>.json`. Create the directory if needed.
3. After saving, invoke the `mcp-translation-file` skill so it can generate a translation card from the saved spec file.

The webhook ORD ID and path to the downloaded spec file **must** be included in the per-asset spec TODO items.

### Step 3: Generate Specification Files

**Only enter this step if Step 2b completed without a STOP.** If a required integration had no supported API, the workflow ended at Step 2b — do not proceed here.

**Before writing any files**, copy the guidelines from the skill into the `specification/` folder so they live next to the specs and can be customized per project:

- Copy `<skill:specification>/assets/guidelines.md` → `specification/guidelines.md` (skip if already exists)
- For each distinct asset type used, copy `<skill:<asset-type>>/assets/guidelines-<asset-type>.md` → `specification/guidelines-<asset-type>.md` (once per asset-typetype; skip if already exists)

These are **pure file copies** (`cp`) — do not modify, resolve references, or rewrite content. Copy the file bytes as-is.

For each asset:

1. Read the template: `<skill:<asset-type>>/assets/specification-<asset-type>-template.md`
2. Read the PRD thoroughly to derive feature-specific tasks
3. Replace placeholders:
   - `{​{asset-name}}` → actual asset name (e.g. `purchase-order-approval-agent`)
   - `{​{feature}}` → feature name (e.g. `purchase-order-approval`)
   - Any remaining `<skill:specification>` references: replace with the relative path from the file being written to the skill directory. **Must be a relative `../`-based path — never an absolute path (e.g. never `/Users/...` or `/home/...`).**
4. Replace `{{project-specific-tasks}}` with concrete TODO items derived from the input (PRD, intent, or user prompt). Use `##` markdown headers to group related TODOs:
   - Each functional requirement → one or more `- [ ]` items
   - Each business rule → specific TODO
   - When working from intent/prompt (no PRD): derive tasks from the described goals; be explicit about assumptions made
   - **If `## Data Dependencies` has only Data Product ORD IDs (no direct API ORD IDs): do NOT generate MCP server creation or `mcp-translation-file` tasks — DPQuery is the only runtime dependency.**
5. Write to `specification/<asset-name>/specification.md`

**CRITICAL: Complete the spec generation loop for ALL assets before doing anything else.**
Finish every per-asset spec file first, then generate the main spec at `specification/specification.md`:

```markdown
# Specification

> **Guidelines**: Read [guidelines.md](./assets/guidelines.md) before executing ANY tasks below.

Check off items as completed.

## Solution Setup

- [ ] Create asset directories: `mkdir -p assets/<asset-name-1>/ assets/<asset-name-2>/`
- [ ] Invoke `setup-solution` skill to create `solution.yaml` and `asset.yaml` files for every asset
- [ ] Validate all `asset.yaml` and `solution.yaml` files exist and are well-formed

## Asset Implementation

- [ ] Execute specification/<asset-name-1>/specification.md (all items)
- [ ] Execute specification/<asset-name-2>/specification.md (all items)
- [ ] Cross-implementation compatibility check (only if multiple assets — verify interfaces, data shapes, auth, env vars align across assets; fix any mismatches before proceeding)
```

Adjust the list based on actual assets. Single-asset solutions omit the compatibility check.

### Step 4: Review (not in fast-track mode)

Only run this step after ALL per-asset specs and the main `specification/specification.md` is fully written.

Present the full set of generated specifications to the user. Summarize:
- Number of assets and their types
- Key features per asset
- API integrations discovered (if any)

User can edit specification files before execution.

**In fast-track mode:** skip review — do NOT output a summary, do NOT ask the user; autonomously proceed to execution by reading `specification/specification.md` and running all tasks.

## B - Executing Specifications

When user says **"execute specification/specification.md"** (or similar):

Read `specification/specification.md` and execute tasks.

## Templates

Templates live in `<skill:<asset-type>/assets/specification-<asset-type>-template.md`.

## Guidelines

Guidelines are **copied from the skill into the `specification/` folder** during spec generation, so they live next to the specs and can be customized per project.

| Source (skill asset)         | Copied to                              | Referenced as (main spec) | Referenced as (per-asset spec) 
| `guidelines.md`              | `specification/guidelines.md`          | `./guidelines.md`         | `../guidelines.md`          |     

This applies to asset specific guidelines as well. Source (skill asset) is copied from `<skill:asset-type>/asset/guidelines-<asset-type>.md` to `specification/guidelines-<asset-type>.md` and referenced per-asset spec as `../guidelines-<asset-type>.md` 

Only the guidelines files for asset types actually used in the solution are copied. If a guideline file does not exist, skip it silently and continue.

## What This Skill Does NOT Do

- Implement code (specifications are executed separately)
- Git operations, deployment, authentication
- Create PRDs (use `product-requirements-document` skill)
