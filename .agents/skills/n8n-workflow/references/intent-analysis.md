### Solution Category

| Category   | What gets built                                                                                   | Asset Type|
|------------|---------------------------------------------------------------------------------------------------|-----------|
| **n8n Workflow**           | n8n workflow written as a `.n8n.json` file                                        |`n8n-workflow`|

### Decision Flow

- Is there a clearly defined workflow (steps and routing known upfront), all AI involvement can be handled by a static LLM node, or the user explicitly calls out n8n as the orchestrator? → **n8n Workflow is required**
- Is there a clearly defined workflow AND at least one step requires open-ended reasoning, context retention, or dynamic tool use that a static node cannot reliably handle? → **Both n8n Workflow and an AI Agent are required**

### Asset Creation Defaults
#### Agent asset
 - **ASK WHEN APPLICABLE** — when the solution requires a workflow to call an agent (via SAP Agent node), ask the user whether this is a new agent in the current solution or an existing agent from another solution **if the original prompt does not make this explicit**. If the prompt clearly references an existing agent or clearly implies a new one, infer accordingly and skip the question.
 - If the user confirms a new agent: plan an AI Agent asset in this solution.
 - If the user confirms an existing agent: do NOT plan a new agent asset. Record the reference in the Fit Gap Notes.

**Fast Track exception for agent asset:**
 - In Fast Track mode, if the user did not explicitly specify whether the agent is new or existing, do **NOT** create an in-solution agent asset and do **NOT** hallucinate/fabricate agent ordId or name values.
 - Instead, configure the `CUSTOM.sapAgent` node with empty agent parameters: `"agentName": ""` and `"agents": "[]"`.
 - Add a `n8n-nodes-base.stickyNote` node directly above the SAP Agent node with this content: "⚠️ Agent not configured — select the target agent in this node before deploying the workflow."
 - This allows the user to select the target agent manually in the n8n editor after deployment.

#### MCP server asset
 - **Default: create a new MCP server asset** — when the workflow or agent in the same solution reads business data from SAP or a LOB system, include a new MCP server asset in the solution unless the user explicitly confirms that an existing external agent or integration already provides the required data access.
 - If coverage is unclear, ask the user rather than assuming no MCP server is needed.

### Node Availability Check (MANDATORY)

Run `list-supported-nodes` immediately on activation, in parallel with landscape investigation. Treat the returned list as the exclusive set of available nodes on this instance.

For each capability relevant to the user's request, check whether a supported node exists and record any gaps in `intent.md` using the Fit Gap Analysis table.

| Capability | What to look for | Sensible default if absent | Confirm with user? |
|---|---|---|---|
| Scheduled / time-based trigger | `scheduleTrigger`, `cron` | Use a webhook and note that an external scheduler must be configured | No |
| Email delivery | `gmail`, `microsoftOutlook`, `sendGrid`, SMTP nodes | No default; record as a gap | Yes |
| Chat / messaging delivery | `microsoftTeams`, `slack` | No default; record as a gap | Yes |
| Webhook / manual trigger | `n8n-nodes-base.webhook` | Expected to be available on managed n8n | No |
| Human-in-the-loop / approval | `sapTaskCenter`, supported HITL nodes | No default; record as a gap | Yes |

Default silently only when the user's stated business outcome is fully preserved by the workaround.
If the workaround changes what the user gets, ask explicitly before proceeding.

For each affected capability, add a row to the Fit Gap Analysis table in `intent.md`:
- Use a business-readable requirement label (e.g. "Automated evening scheduling")
- Set Gap to Yes
- In the Notes column, state the workaround in one plain sentence, or state that the capability is unavailable and a decision is needed
- Do NOT add a separate technical section — the Fit Gap table is sufficient

### Clarifying Questions

1. Scan for all unresolved items from the prompt (vague thresholds e.g. "needs attention", missing scheduling details e.g. "every evening", missing context, unknown dependencies, data structure e.g. "structured response", approval owners).
2. **If required information is missing or unclear:** 
    - Ask follow-up questions when the missing detail would materially change the workflow structure or make the output incorrect. 
    - If the missing detail is structured, bounded, and a reasonable default exists, choose the default, state the assumption clearly, and continue. 
    - Do not fabricate routing logic or business rules.

Decision rule:
- If a workaround preserves the user's requested business outcome, apply it by default and document it in the Fit Gap Analysis table.
- If a workaround changes the business outcome, user experience, delivery channel, or operational responsibility, stop and ask the user before proceeding.

### Common Solution Patterns for SAP System Interactions

| Business Need | Likely Solution | Category |
|---|---|---|
| Event-driven trigger → condition-based routing → automated actions with no open-ended reasoning | Webhook → IF/Switch node → SAP Task Center Node → Respond to Webhook | n8n Workflow |
| Event-driven trigger → read data from SAP system → agent analyses and returns structured response | Webhook → SAP MCP Client Node → SAP Agent Node → Respond to Webhook | n8n Workflow, MCP Server, AI Agent |
| Same as above + human approval required before write-back to SAP | Webhook → SAP MCP Client Node → SAP Agent Node → SAP Human-in-the-Loop Node → SAP MCP Client Node (write) | n8n Workflow, MCP Server, AI Agent |
| Event-driven trigger → agent reads business data via MCP, analyses and returns structured response → human approval via Task Center → respond to webhook | Webhook → SAP Agent Node (uses MCP server to get business data, analyses and returns structured response) → SAP Task Center Node (approval) → Respond to Webhook | n8n Workflow, MCP Server, AI Agent |

### Eliciting routing rules and configuration data

When to ask:
- Ask when the prompt describes routing that maps a known set of values to different actions or recipients — for example when terms such as "rules", "matrix", "policy", "routing", "lookup", "conditions", "thresholds", "assignments", "tiers", or "mappings" appear, or when the prompt describes a lookup table (e.g. company code → reviewer, amount → approval tier).

Ask once, concisely:

> "It looks like your workflow uses a routing policy or lookup table. To generate this correctly, I need: the field being evaluated, the possible values or ranges, and the action for each. You can paste a table, a list, or a short description."

Proceed only if:
- The user provides the data, or
- The user explicitly confirms they want placeholder values generated and will replace them after generation.

Fast-track exception:
- If the user's request contains "fast track" or "fast-track" (case-insensitive), skip the question.
- Translate any data already present in the prompt into a complete named constant block as far as possible.
- Use clearly marked placeholders (e.g. `"YOUR_VALUE_HERE": "YOUR_ACTION_HERE"`) only for values genuinely absent from the prompt.
- The "Structure user-provided configuration as a named constant block" rule (with its sticky-note requirement) defined in `execution.md` still applies.

### Post-Decision Action

When the prompt describes a workflow that produces a decision result (e.g. an approval, a routing outcome, a condition branch), classify the prompt's intent **before** planning any post-decision nodes:

| Scenario | Signal in the prompt | Output node to use |
|---|---|---|
| SAP action required | Prompt says to record a decision, create/update a document, post a status, approve/reject in SAP, or trigger a downstream SAP process | `CUSTOM.sapMcpClient` — executes the actual SAP call |
| Shape/relay the outcome only | Prompt says to relay a decision back to the caller, format a response, or no SAP write is mentioned or implied | `n8n-nodes-base.set` to shape the response payload, then `respondToWebhook` |
| Ambiguous — SAP write is plausible but not stated | Prompt mentions an approval/decision but does not state what should happen in SAP afterward | Stop and ask: "Should this decision be recorded in SAP (e.g. update a status, post a result), or should the workflow just return the decision to the caller?" |
