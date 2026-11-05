**This skill operates on the current working directory.** The caller is responsible for running it from the correct target directory (e.g. `assets/agent-extension/`).

## Schema References

All generated files MUST conform to the following JSON Schema definitions:

- **Extension Descriptor** (`extension.yaml`): [assets/extension.json](assets/extension.json)
- **Asset Descriptor**: From `setup-solution` skill
- **Agent Discovery Response** (response schema reference): [assets/agent-discovery-response.json](assets/agent-discovery-response.json)
  - Fetching all extensible agents returns the full response (`{ agents: [...], pageInfo: {...} }`)
  - Fetching a single extensible agent returns a single agent object (one item from the `agents` array, no `pageInfo`)

### Tool Result → YAML Field Mapping

Use this mapping to translate agent discovery response fields into the generated YAML files.

#### Agent → `extension.yaml`

| Tool Result Field | `extension.yaml` Field |
|---|---|
| `ordId` | `agent.ordId` |
| `systemInstance.globalTenantId` | `agent.identifier` |
| `extensions[].params.capabilityId` | `capabilityImplementations[].capabilityId` |
| `extensions[].params.instructionSupported` | Determines if `capabilityImplementations[].instruction` can be set |
| `extensions[].params.tools.additions.enabled` | Determines if `capabilityImplementations[].tools[]` can be populated |
| `extensions[].params.supportedHooks` | Determines which hooks can be defined in `capabilityImplementations[].hooks[]` |

#### Agent → `asset.yaml`

| Tool Result Field | `asset.yaml` Field |
|---|---|
| `ordId` | `requires[].ordId` (where `type: agent`) |
| `version` | `requires[].version` (where `type: agent`) |

## Step 0: Ensure Intent, PRD, and Spec exist (MANDATORY)

**Before generating any extension YAML, the solution MUST contain all three IBD documents: `intent.md`, `product-requirements-document.md`, and a `specification/` folder.** These are normally already present because this skill runs at the end of the orchestration chain (`intent-analysis` → `product-requirements-document` → `specification` → `create-agent-extension`).

**Check the current working directory and act accordingly:**

- **If `product-requirements-document.md` AND `specification/` already exist**, the upstream chain already ran — proceed directly to Step 1.
- **Otherwise (any of the three documents is missing — e.g. this skill was reached directly from an "Extend agent" request), you MUST run the full IBD chain first, in order, and only then continue:**
  1. Run the `intent-analysis` skill → writes `intent.md`.
  2. Then run the `product-requirements-document` skill → writes `product-requirements-document.md`.
  3. Then run the `specification` skill → writes the `specification/` folder.

  Do NOT generate any extension YAML, and do NOT jump ahead to Step 1, until **all three** documents exist. Generating `intent.md` alone is NOT sufficient — the PRD and specification MUST also be produced. This guarantees an agent extension solution is as complete and consistent as any other solution type, with or without fast track.

## Step 0b: Check Feature Flags

Check which optional capabilities are enabled before collecting requirements or generating any files:

```bash
jl feature-flags get enable_agent_extension_mcp_server
jl feature-flags get enable_agent_extension_n8n_hooks
```

Store the results — they govern whether the MCP tools and hooks sub-skills execute:

| Flag | Controls |
|---|---|
| `enable_agent_extension_mcp_server` | MCP tool integration (Step 3b / [mcp-tools sub-skill](./mcp-tools.md)) |
| `enable_agent_extension_n8n_hooks` | n8n hook configuration (Step 4 / [hooks sub-skill](./hooks.md)) |

**Fail-closed — a capability is enabled ONLY on an explicit `true`:**
- Command returns `true` → capability enabled.
- Command returns `false` → capability disabled.
- Command **errors, returns non-zero, prints anything other than a clear `true`, or the value cannot be retrieved for any reason** → treat the capability as **disabled**. Do NOT assume it is enabled, and do NOT proceed with that capability. Inform the user, e.g.: "Could not retrieve `<flag>` — treating the capability as disabled and skipping it. Re-run once the flag can be read if you need it."

Do NOT ask the user about tools or hooks in Step 1b unless their flag was retrieved and is `true`. Do NOT include `tools` or `hooks` sections in `extension.yaml` unless their flag was retrieved and is `true`.

## Step 1: Fetch Agent Information

**IMPORTANT: Always fetch agent information first** to get the correct `ordId` and `version` for the agent to be extended.

#### When User Provides a Specific ordId

If the user provides a specific ordId and version (e.g., `sap.ai:agent:my-agent:v1` & version `1.0.0`), fetch that specific agent via the agent discovery API:

#### Default Query (No ordId Provided)

Fetch all extensible agents via the agent discovery API.

Note that the result can have a next page with a cursor that can be used to fetch more agents if needed. If multiple agents are returned, ask the user to select which agent they want to extend. Present the options clearly with their `ordId`, `version`, and a short description.

#### Handle Multiple Versions

If the query returns **multiple versions** of the same agent (e.g., `sap.ai:agent:my-agent:v1` and `sap.ai:agent:my-agent:v2`), you **MUST ask the user which version to use** before proceeding. Present the versions clearly:

- List each version with its `ordId`, `version`, `description`
- Highlight differences between versions if apparent (e.g., different extension capabilities)
- **Do NOT default to the latest version silently** — always let the user decide

#### Handle Agent Not Found

**CRITICAL — MANDATORY ABORT:** If no agent is found in the extensible agents registry (empty results, the specified `ordId` does not exist, or no matching agent returns):

1. **Do NOT create any extension files** — no `extension.yaml`, no agent-extension folder, no skeleton files
2. **Do NOT use placeholder values** — never write `<REPLACE: ...>`, `<from tool: ...>`, or similar placeholder text
3. **Do NOT invent or guess agent information** — never fabricate `ordId`, `version`, `identifier`, or extension capabilities
4. **Do NOT ask the user to provide the ordId manually** — if the agent is not in the registry, it cannot be extended
5. **SKIP the entire agent extension creation** and inform the user:
   > "The requested agent was not found in the extensible agents registry. Skipping agent extension creation. Only agents that are registered as extensible can be extended via this skill."
6. **Continue with other tasks** in the conversation if applicable (e.g., creating workflows, other assets that don't depend on the agent extension)

**This is a hard stop** — without valid agent data from the discovery API, no extension artifacts can be created. The skill requires real agent metadata; it cannot proceed with placeholders or user-provided values.

## Step 1b: Collect and Confirm Extension Requirements (MANDATORY)

**CRITICAL: This step MUST NOT be skipped under any circumstances.** Before generating any YAML files, collect all required information and obtain explicit user confirmation.

### Required Information Checklist

Gather the following information from the user, intent.md, product-requirements-document.md, and the agent discovery response:

**Extension Basics:**
- [ ] Extension name (kebab-case, descriptive)
- [ ] Extension purpose/description (what capabilities does this add?)
- [ ] Target base agent (confirmed from Step 1)
  - Agent name: `<agent-name>`
  - Agent ordId: `<ordId>`
  - Agent version: `<version>`

**Extension Capabilities (based on agent's supported extensions AND feature flags from Step 0b):**
- [ ] Will this extension add **instructions**? (if `instructionSupported: true`)
  - If yes, what additional instructions/guidance?
- [ ] Will this extension add **tools**? (if `tools.additions.enabled: true` **AND** `enable_agent_extension_mcp_server = true`)
  - If yes, which APIs/systems will be integrated?
  - Expected tool names/functions?
- [ ] Will this extension add **hooks**? (if `supportedHooks` is non-empty **AND** `enable_agent_extension_n8n_hooks = true`)
  - If yes, which hooks? (pre-execution, post-execution, etc.)
  - What should each hook do?

**Dependencies:**
- [ ] Are there MCP servers to be created? (list expected MCP servers)
- [ ] Are there n8n workflows involved? (list expected workflows)
- [ ] Any other asset dependencies?

**Business Context (from intent.md/PRD):**
- [ ] Business challenge being addressed
- [ ] Success criteria/metrics
- [ ] Key milestones (if applicable)

### Missing Information Handling

**If ANY required information is missing or unclear:**

1. **DO NOT proceed with file generation**
2. **Ask specific clarifying questions** to fill the gaps
3. **Wait for user response** before continuing

Example clarifying questions:
- "I see the base agent supports tools. Which specific APIs or systems should this extension integrate with?"
- "The agent supports pre-execution and post-execution hooks. Which hooks do you need for your use case?"
- "What additional instructions or guidance should the agent follow when using this extension?"

### Scope Reconciliation (MANDATORY — run before the Confirmation Summary)

After collecting all requirements, reconcile the requested capabilities against what the agent actually supports. Do this **before** presenting the Confirmation Summary.

#### Hooks requested but agent does not support them

If the user requested hooks AND `extensions[].params.supportedHooks` is empty or absent:

1. **Remove hooks from scope** — drop every hook-related requirement collected above.
2. **Remove any n8n workflow from scope** — a workflow whose sole purpose was to back a hook is now a floating asset with no consumer. Do NOT create it.
3. **Evaluate what remains:**
   - **Nothing remains** (hooks were the only requested capability) → **abort the entire agent extension**. Do not create `extension.yaml`, do not create any asset. Inform the user:
     > "The selected agent does not support hooks (`supportedHooks` is empty). Since hooks were the only capability requested, there is nothing to create. Skipping agent extension creation."
   - **Other capabilities remain** (e.g. instruction, tools) → continue with those only. Inform the user:
     > "The selected agent does not support hooks (`supportedHooks` is empty). Hooks and any associated n8n workflows have been removed from scope. Proceeding with: [list remaining capabilities]."

#### Tools requested but agent does not support them

Apply the same pattern for tools: if `tools.additions.enabled` is `false` or absent and the user requested tools, remove tools (and any MCP servers whose sole purpose was to back those tools) from scope, then evaluate what remains using the same abort-or-continue logic above.

#### Nothing is left after reconciliation

If reconciliation removes all requested capabilities, abort entirely — do not create any files. Inform the user which capabilities were requested and why each was dropped.

### Confirmation Summary

Once all information is collected **and scope reconciliation is complete**, **present a summary to the user for confirmation:**

```
📋 Extension Requirements Summary

**Extension Details:**
- Name: `<extension-name>`
- Purpose: `<brief description>`

**Target Agent:**
- Agent: `<agent-name>` (ordId: `<ordId>`, version: `<version>`)
- Supported capabilities: [instructions: yes/no, tools: yes/no, hooks: yes/no]

**Planned Extension Features (after scope reconciliation):**
- Instructions: `<yes/no - description if yes>`
- Tools: `<yes/no - list of tools if yes>`
- Hooks: `<yes/no - list of hooks if yes>`

**Dependencies (only assets that are actually consumed):**
- MCP Servers: `<list or "none">`
- n8n Workflows: `<list or "none — removed because agent does not support hooks">`

**Dropped from scope:**
- `<list any capabilities/assets removed during reconciliation, or "none">`

**Business Goals:**
- Challenge: `<from intent.md>`
- Success Criteria: `<from intent.md>`

Is this information correct? Please confirm or provide corrections before I proceed with generating the extension files.
```

**Wait for explicit user confirmation** (e.g., "yes", "confirmed", "looks good", "proceed") before moving to Step 2.

**If user provides corrections:**
- Update the collected information
- Present the updated summary again
- Wait for confirmation again

**Only proceed to Step 2 after receiving explicit user confirmation.**

### Fast Track Mode Exception

**Even in fast-track mode, this confirmation step MUST be performed.** However, in fast-track mode:
- Use a condensed summary format (3-5 lines instead of full detail)
- Pre-fill supported capabilities based on the discovery response and ask the user to correct them if needed
- **Still require explicit confirmation** before proceeding to Step 2

Example fast-track confirmation:
```
📋 Quick Confirmation: Creating extension `<name>` for agent `<agent-name>` with [tools/hooks/instructions]. Integrating with [API names]. Reply "confirm" to proceed or provide corrections.
```

## Step 2: Generate `extension.yaml`

Create `assets/<agent-extension>/extension.yaml` conforming to the Extension Descriptor schema ([assets/extension.json](assets/extension.json)).

**Always generate this file immediately as an empty skeleton** — do NOT ask the user what to include first. The skeleton is populated based on the extension capabilities returned by the discovery response, further gated by the feature flags from Step 0b.

**Feature-flag gating (applies to every case below):**
- Treat `tools` as available only if `extensions[].params.tools.additions.enabled` is `true` **AND** `enable_agent_extension_mcp_server` is `true`. If the flag is `false`, omit the `tools` section entirely even when the agent supports it.
- Treat `hooks` as available only if `extensions[].params.supportedHooks` is non-empty **AND** `enable_agent_extension_n8n_hooks` is `true`. If the flag is `false`, omit the `hooks` section entirely even when the agent supports it.

The `capabilityImplementations` structure depends on which of `tools` / `hooks` remain available after applying the gating above:

#### If tools AND hooks are supported

(`extensions[].params.tools.additions.enabled` is `true` AND `extensions[].params.supportedHooks` is non-empty)

```yaml
_schema-version: "0.1.0"
kind: Extension

metadata:
  name: "<agent-extension-name>"

agent:
  ordId: "<from tool: ordId>"
  identifier: "<from tool: systemInstance.globalTenantId>"

capabilityImplementations:
  - capabilityId: "<from tool: extensions[].params.capabilityId>"
    tools: []
    hooks: []
```

#### If only tools are supported

(`extensions[].params.tools.additions.enabled` is `true` AND `extensions[].params.supportedHooks` is empty or absent)

```yaml
_schema-version: "0.1.0"
kind: Extension

metadata:
  name: "<agent-extension-name>"

agent:
  ordId: "<from tool: ordId>"
  identifier: "<from tool: systemInstance.globalTenantId>"

capabilityImplementations:
  - capabilityId: "<from tool: extensions[].params.capabilityId>"
    tools: []
```

#### If only hooks are supported

(`extensions[].params.tools.additions.enabled` is `false` or absent AND `extensions[].params.supportedHooks` is non-empty)

```yaml
_schema-version: "0.1.0"
kind: Extension

metadata:
  name: "<agent-extension-name>"

agent:
  ordId: "<from tool: ordId>"
  identifier: "<from tool: systemInstance.globalTenantId>"

capabilityImplementations:
  - capabilityId: "<from tool: extensions[].params.capabilityId>"
    hooks: []
```

#### If neither tools nor hooks are supported

```yaml
_schema-version: "0.1.0"
kind: Extension

metadata:
  name: "<agent-extension-name>"

agent:
  ordId: "<from tool: ordId>"
  identifier: "<from tool: systemInstance.globalTenantId>"

capabilityImplementations:
  - capabilityId: "<from tool: extensions[].params.capabilityId>"
```

**Important rules for extension.yaml:**
- The `capabilityId` must match the `params.capabilityId` from the agent's extension capabilities
- Only include `tools` property if `extensions[].params.tools.additions.enabled` is `true` **AND** `enable_agent_extension_mcp_server` is `true`
- Only include `hooks` property if `extensions[].params.supportedHooks` is non-empty **AND** `enable_agent_extension_n8n_hooks` is `true`
- Only add `instruction` if `extensions[].params.instructionSupported` is `true`
- Do NOT include `tools` or `hooks` properties at all when the capability does not support them or their feature flag is `false`

## Step 3: Setup Solution and Dependencies

Before populating tools or dependencies:

1. Run `setup-solution` from the solution root (not from `assets/<ext>/`) — running it from inside the asset folder creates a misplaced `solution.yaml` inside the asset directory.
2. **CRITICAL — additive only:** If `solution.yaml` already exists, only add the agent-extension entry to the existing `assets:` list. Do NOT regenerate or overwrite the file — doing so drops the MCP server and n8n workflow registrations created by earlier spec steps.
3. Confirm the extension `asset.yaml` exists and contains the agent dependency `requires` entry. If missing, add it manually.
4. Confirm MCP server assets now exist under `assets/` before proceeding to Step 3b.

## Step 3b: Populate Tools and MCP Server Dependencies

Read and follow the [mcp-tools sub-skill](./mcp-tools.md). It checks the `enable_agent_extension_mcp_server` feature flag and skips automatically if disabled.

**Run this step only after Step 3 (`setup-solution`) has completed**, because `setup-solution` creates the MCP server assets in `assets/` that this step reads.

## Step 4: Configure Hooks for n8n Workflows from Same Solution

Read and follow the [hooks sub-skill](./hooks.md). It skips automatically when either condition is unmet: the `enable_agent_extension_n8n_hooks` feature flag is not `true`, or the base agent's `supportedHooks` is empty or absent.

## Step 5: Set `extensionUrl`

After the solution is set up, fetch the solution URL to retrieve the platform URL for the solution. Then **add only** the `extensionUrl` field to the existing `metadata` block in `extension.yaml` — do NOT overwrite or remove other metadata fields like `name`:

```yaml
metadata:
  name: "<keep existing>"
  extensionUrl: "<fetched solution URL>"
```

This step MUST be performed as the final step — the `extensionUrl` is the complete host URL for the solution.
