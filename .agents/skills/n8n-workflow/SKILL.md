---
name: n8n-workflow
description: "Creates and edits workflows (.n8n.json files) for SAP-managed n8n. Activate this skill if n8n or workflow is requested or a solution will likely involve a workflow. Activate early as it contains relevant knowledge and constraints for the intent-analysis and PRD phases already (e.g. checking existance of available nodes which might change the approach)"
metadata:
  version: 1.0.0
  author: sap-joule-studio
---

## Reference Files

**Do not plan nodes, topology, or workflow structure until you have read the files marked "Always".** The rules governing every decision live in those files, not here.
**Always ensure the correct order is followed:** intent-analysis (produces intent.md) → product-requirements-document (produces product-requirements-document.md) → specification (produces files in the specification/ folder) → workflow generation (this skill). If any of these artifacts are missing, run the upstream skills first and continue with workflow generation only afterward. Follow this process even if the needed information is already present in context. Skip it only if the user explicitly requests that these phases be bypassed.

### IBD Flow

| File | When to read | What it covers |
|---|---|---|
| [intent-analysis](./references/intent-analysis.md) | **Always** | Solution category, asset type, clarifying questions |
| [guidelines-n8n-workflow](./assets/guidelines-n8n-workflow.md) | **Always, before planning any node or topology** | Key constraints and credential rules |
| [execution](./references/execution.md) | **Always, before planning any node or topology** | All node/routing/convergence/validation rules — the authoritative source |
| [setup-solution](./references/setup-solution.md) | **Always, when executing setup-solution, before generating the n8n workflow** | Asset scaffold: `asset.yaml` structure, naming rules, `requires` declarations |
| [workflow-hooks](./references/workflow-hooks.md) | When building a pre/post hook workflow for A2A agent extension | Hook-specific rules: A2A message protocol, webhook trigger/response shape, hook patterns |

### n8n Node References

Read the respective following files when generating or editing an n8n workflow.

| File | When to read | What it covers |
|---|---|---|
| [n8n-expressions](./references/n8n-expressions/n8n-expressions.md) | MUST read when writing any node parameter with `{{ }}` expressions, `$json`, `$('Node Name')` references, Luxon date math, data transformation, or when a webhook workflow accesses request body fields or constructs a JSON response | Expression syntax, reference-by-node-name rules, method chains, Luxon date math, anti-patterns |
| [n8n-code-nodes](./references/n8n-code-nodes/n8n-code-nodes.md) | MUST read when any Code node is being written, evaluated, or justified; when the user reaches for JavaScript or Python; or when "transform data" / "custom logic" / "loop" comes up and the right tool is unclear | Last-resort principle, decision tree summary, Crypto/XML node traps, anti-patterns |
| [n8n-code-nodes-decision-tree](./references/n8n-code-nodes/n8n-code-nodes-decision-tree.md) | Read when using decision trees in code nodes; Prerequisite: n8n-code-nodes | Full 3-stage decision logic: expression → Edit Fields → Code node, with examples by category |
| [n8n-code-nodes-arrow-functions](./references/n8n-code-nodes/n8n-code-nodes-arrow-functions.md) | Read when using arrow functions in code nodes; Prerequisite: n8n-code-nodes | IIFE pattern, cross-item aggregation with Execute Once, performance tradeoffs, common mistakes |
| [n8n-code-nodes-javascript-patterns](./references/n8n-code-nodes/n8n-code-nodes-javascript-patterns.md) | Read when using JavaScript patterns in code nodes; Prerequisite: n8n-code-nodes | Run modes, return shape, available libraries, binary handling, error patterns, testing |
| [n8n-loops](./references/n8n-loops/n8n-loops.md) | MUST read when any looping, iteration, batching, rate limiting, or paginated API call is involved | Covers Loop Over Items node, HTTP Request pagination modes, and stateful iteration patterns |
| [n8n-loops-loop-over-items](./references/n8n-loops/n8n-loops-loop-over-items.md) | Read when configuring the Loop Over Items node; Prerequisite: n8n-loops | Configuring the Loop Over Items node, batching, rate limiting, stateful iteration |
| [n8n-loops-http-pagination](./references/n8n-loops/n8n-loops-http-pagination.md) | Read when calling a paginated API; Prerequisite: n8n-loops | Calling a paginated API, configuring HTTP Request pagination modes |
| [n8n-sap-agent](./references/n8n-sap-agent/n8n-sap-agent.md) | MUST read when generating SAP Agent nodes | Agent invocation, mandatory parameters, `agents`/`agentName` key order, multi-agent orchestration |
| [n8n-sap-ai-core](./references/n8n-sap-ai-core/n8n-sap-ai-core.md) | MUST read when generating LLM operations (chat, extraction, summarization, OCR) | SAP AI Core node structure, parameter reference, model names, translation codes, LangChain connection pattern |
| [n8n-sap-mcp-client](./references/n8n-sap-mcp-client/n8n-sap-mcp-client.md) | MUST read when invoking any SAP system or S/4HANA action | Mandatory use for all SAP calls, tool selection modes, credential resolution, no-Set-node rule |
| [n8n-sap-task-center](./references/n8n-sap-task-center/n8n-sap-task-center.md) | MUST read when building approval or human-in-the-loop workflows | Mandatory Switch node pattern after Task Center, recipient rules, post-decision SAP MCP Client requirement |
| [n8n-trigger-nodes](./references/n8n-trigger-nodes/n8n-trigger-nodes-webhook.md) | MUST read when placing any Webhook trigger node | responseMode decision table, fire-and-forget vs synchronous vs responseNode patterns, common errors|
