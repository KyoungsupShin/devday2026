# n8n Hooks Sub-Skill

**MANDATORY FIRST STEP — Check Feature Flag**

Before executing anything in this sub-skill, run:

```bash
jl feature-flags get enable_agent_extension_n8n_hooks
```

- If the result is `true` → proceed to the agent capability check below.
- If the result is `false` → **skip this entire sub-skill**. Do not add any `hooks` sections to `extension.yaml`, do not add n8n workflow `requires` entries to `asset.yaml`. Inform the user: "n8n hook integration is currently disabled (`enable_agent_extension_n8n_hooks = false`). Skipping hooks configuration."
- If the command **errors, returns non-zero, prints anything other than a clear `true`, or the value cannot be retrieved for any reason** → **fail closed**: treat the capability as disabled and **skip this entire sub-skill**. Do NOT assume it is enabled and do NOT proceed. Inform the user: "Could not retrieve `enable_agent_extension_n8n_hooks` — treating n8n hook integration as disabled and skipping hooks configuration."

**MANDATORY SECOND STEP — Check Agent Capability**

Even if the feature flag is `true`, verify that the base agent actually supports hooks:

- If `extensions[].params.supportedHooks` from the agent discovery response is **non-empty** → proceed with the steps below.
- If `extensions[].params.supportedHooks` is **empty, absent, or null** → **skip this entire sub-skill**. Do not add any `hooks` sections to `extension.yaml`, do not add n8n workflow `requires` entries to `asset.yaml`. Inform the user: "The selected agent does not expose any supported hooks (`supportedHooks` is empty). Skipping hooks configuration."

Both conditions must be satisfied — the feature flag must be `true` **and** the agent must expose at least one `hookId` in `supportedHooks` — before this sub-skill executes.

This step applies **only when a new n8n workflow was created in the same solution** and needs to be connected as a hook to the agent extension. Skip this sub-skill if the workflow comes from UMS (external fetch).

---

## Step 1: Gather Hook Configuration

**Enumerate REST APIs first.** Read the workflow's `asset.yaml` and collect **all** `provides.apis[]` entries where `kind: rest` — every one of them will become a hook entry. No user selection is needed; the requirements confirmation already covered which workflows and hooks are in scope. The hook config values below (hookType, timeout, onFailure, canShortCircuit) are collected once and applied uniformly to all hooks generated from this workflow.

#### From Base Agent (do NOT ask user)

| Parameter | Source |
|---|---|
| `hookId` | Read from `extensions[].params.supportedHooks` in agent discovery response |

#### Fast Track Mode

**IMPORTANT:** In Fast Track Mode, use the **default values** from the table above. Do NOT ask the user for hook configuration parameters.

#### Normal Mode (Non-Fast Track)

**CRITICAL: You MUST ask the user for the following values if they were not explicitly provided in the conversation. Do NOT guess or use default values — always ask the user first.**

**For pre-hooks (hookType = BEFORE) — ask ALL 4 parameters:**

| Parameter | Allowed Values | Description |
|---|---|---|
| `hookType` | `BEFORE` or `AFTER` | BEFORE = pre-hook, AFTER = post-hook |
| `timeout` | `5`, `10`, `30`, `60`, or `120` | Timeout in seconds for hook execution |
| `onFailure` | `FAIL` or `CONTINUE` | FAIL (stop on error) or CONTINUE (ignore errors) — block or continue agent execution on error during hook invocation |
| `canShortCircuit` | `true` or `false` | Whether this hook can stop agent execution |

**For post-hooks (hookType = AFTER) — ask only 2 parameters:**

| Parameter | Allowed Values | Description |
|---|---|---|
| `hookType` | `BEFORE` or `AFTER` | BEFORE = pre-hook, AFTER = post-hook |
| `timeout` | `5`, `10`, `30`, `60`, or `120` | Timeout in seconds for hook execution |

For post-hooks, do NOT ask for `onFailure` and `canShortCircuit`. Use default values: `onFailure: CONTINUE` and `canShortCircuit: true`.

**Example prompt for pre-hook (BEFORE):**
> To configure the hook for the workflow, I need the following information:
> 1. **Hook Type**: Should this hook run BEFORE (pre-hook) or AFTER (post-hook) the agent processing?
> 2. **Timeout**: What timeout in seconds? Options: 5, 10, 30, 60, 120
> 3. **On Failure**: If the hook fails, should the agent BLOCK (stop on error) or CONTINUE (ignore errors)?
> 4. **Can Short-Circuit**: Can this hook stop agent execution? (true/false)

**Example prompt for post-hook (AFTER):**
> To configure the hook for the workflow, I need the following information:
> 1. **Hook Type**: Should this hook run BEFORE (pre-hook) or AFTER (post-hook) the agent processing?
> 2. **Timeout**: What timeout in seconds? Options: 5, 10, 30, 60, 120

**Do NOT proceed to Step 2 until you have all required values from the user.**

---

## Step 2: Read Workflow Configuration

Fetch workflow asset files from the same solution. Then follow these steps:

1. **Get REST API ordIds**: Read the workflow's `asset.yaml` and extract **all** `provides.apis[]` entries where `kind: rest`. Each entry produces one hook — collect every `ordId` from these entries.

2. **Get HTTP method per REST API**:
   - From the workflow's `asset.yaml`, get the file path from `workflow.definitionFile`
   - Read that workflow JSON file
   - Normalize both the API `path` and the webhook node's `parameters.path` before comparing: trim surrounding whitespace, remove a single leading `/`, and remove a trailing `/` if present (n8n stores the path without the leading slash)
   - For each REST API collected in step 1, find the webhook node whose normalized `parameters.path` matches the normalized API `path`
   - Extract `parameters.httpMethod` from that matched node
   - Each REST API gets its own method from its own webhook node

3. **Generate hook entries in `extension.yaml`** — one entry per REST API collected in step 1, all sharing the same hookType, timeout, onFailure, canShortCircuit, and method:

**For pre-hooks (BEFORE):**
```yaml
hooks:
  # One entry per kind:rest API in provides.apis[] — repeat the block below for each
  - hookId: "<from base agent supportedHooks>"
    name: "<descriptive name>"
    hookType: BEFORE
    deploymentType: N8N
    onFailure: "<FAIL or CONTINUE - from user input>"
    timeout: <5|10|30|60|120 - from user input>
    canShortCircuit: <true|false - from user input>
    n8nWorkflowConfig:
      ordId: "<ordId of this REST API from provides.apis[]>"
      name: "<from workflow asset.yaml: workflow.name>"
      method: "<parameters.httpMethod of the webhook node whose path matches this API's path>"
```

**For post-hooks (AFTER):**
```yaml
hooks:
  # One entry per kind:rest API in provides.apis[] — repeat the block below for each
  - hookId: "<from base agent supportedHooks>"
    name: "<descriptive name>"
    hookType: AFTER
    deploymentType: N8N
    onFailure: CONTINUE
    timeout: <5|10|30|60|120 - from user input>
    canShortCircuit: true
    n8nWorkflowConfig:
      ordId: "<ordId of this REST API from provides.apis[]>"
      name: "<from workflow asset.yaml: workflow.name>"
      method: "<parameters.httpMethod of the webhook node whose path matches this API's path>"
```

---

## Step 3: Add Workflow Dependency to `asset.yaml`

Add a `requires` entry for the n8n workflow to the agent extension's `asset.yaml`. Do NOT replace existing entries — append to the existing `requires` block, preserving the agent and any MCP server entries already present.

**One requires entry per workflow, regardless of how many hooks it backs.** If the workflow exposes two REST APIs and produces two hooks, still add only a single `type: n8n-workflow` entry:

```yaml
requires:
  - name: "<agent-title-kebab-case>"
    type: agent
    version: "<from tool: version>"
    ordId: "<from tool: ordId>"
  - name: "<from workflow asset.yaml: workflow.name>"
    type: n8n-workflow
```

**Important**: The `name` in the requires entry MUST match the `name` from `workflow.name` in the workflow's `asset.yaml`, NOT the `metadata.name`.

---

## Example

Given a workflow folder `assets/workflows/invoice-notification-workflow/` with:

**asset.yaml:**
```yaml
apiVersion: asset.sap/v1
kind: Asset

metadata:
  name: invoice-notification-workflow
  description: Invoice unmatched notification workflow
  version: 1.0.0
  type: n8nworkflow

projectVersion: "1"
sourceRoot: "."

workflow:
  definitionFile: invoice-unmatched.n8n.json
  name: invoice-unmatched-notification
  ordId: sap.btpn8n:apiResource:ManagedN8nMcpServer:v1  # DEPRECATED: use provides.apis[].ordId in hooks instead

provides:
  apis:
    - name: invoice_notification
      path: /invoice-notification
      kind: rest
      description: Triggers the invoice unmatched notification workflow
      ordId: customer.build:apiResource:invoice-notification.invoiceNotification:v1
    - name: invoice_reminder
      path: /invoice-reminder
      kind: rest
      description: Triggers the invoice reminder workflow
      ordId: customer.build:apiResource:invoice-notification.invoiceReminder:v1
    - name: invoice_notification_mcp_server
      kind: mcp-server
      description: MCP server for invoice notification operations
      ordId: customer.build:apiResource:invoice-notification.invoiceNotificationMcpServer:v1
```

**invoice-unmatched.n8n.json:**
```json
{
  "nodes": [
    {
      "parameters": {
        "httpMethod": "POST",
        "path": "invoice-notification"
      },
      "type": "n8n-nodes-base.webhook",
      "webhookId": "abc123-def456"
    },
    {
      "parameters": {
        "httpMethod": "POST",
        "path": "invoice-reminder"
      },
      "type": "n8n-nodes-base.webhook",
      "webhookId": "abc123-def789"
    }
  ]
}
```

The resulting hook entries in `extension.yaml`:
```yaml
hooks:
  - hookId: agent_pre_hook
    name: Invoice Notification
    hookType: BEFORE
    deploymentType: N8N
    onFailure: CONTINUE
    timeout: 30
    canShortCircuit: true
    n8nWorkflowConfig:
      ordId: customer.build:apiResource:invoice-notification.invoiceNotification:v1
      name: invoice-unmatched-notification
      method: POST
  - hookId: agent_pre_hook_2
    name: Invoice Reminder
    hookType: BEFORE
    deploymentType: N8N
    onFailure: CONTINUE
    timeout: 30
    canShortCircuit: true
    n8nWorkflowConfig:
      ordId: customer.build:apiResource:invoice-notification.invoiceReminder:v1
      name: invoice-unmatched-notification
      method: POST
```

And the `requires` entry in `asset.yaml` (one entry for the workflow, regardless of how many hooks it backs):
```yaml
requires:
  - name: base-agent
    type: agent
    version: "1.0.0"
    ordId: "sap.ai:agent:example:v1"
  - name: invoice-unmatched-notification
    type: n8n-workflow
```
