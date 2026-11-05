# n8n SAP Task Center Node Generation

## Overview

Ensures **stable and correct** generation of SAP Task Center nodes for human-in-the-loop (HITL) approval workflows. It enforces strict validation rules and mandatory structural patterns to prevent common errors.

**Critical Mission:** SAP Task Center nodes MUST always be followed by a switch node because they have only ONE output that contains the decision result.

---

## CRITICAL RULES (DO NOT SKIP)

### 1. **ALWAYS use MCP to get node metadata**

**BEFORE generating a SAP Task Center node:**
```javascript
// Call MCP tool
search-nodes-catalog("task center")
```

**Use the returned values:**
- `name` → use as `type` in workflow
- `version` → use as `typeVersion` in workflow
- `properties` → use to understand available parameters

**NEVER hardcode typeVersion** - always get it from MCP.

---

### 2. **ALWAYS Ask for the recipient first**

Before writing the Task Center node's parameters — before choosing subject, priority, or task definition — you must have an explicit, **user-chosen** recipient source for this Task Center node. The source is one of three: a static email (`userId`), a static group ID (`groupId`), or a **dynamic binding** to a known workflow input field (an expression, `userId` **or** `groupId`). What you must never do is invent the recipient yourself.

**The ask.** Stop and ask the user, offering all three as equal, first-class choices, for example:

> "Who should receive this approval task in SAP Task Center? Choose one:
> 1. **A fixed email address** — used exactly as you provide it (`userId`).
> 2. **A group ID** — the task goes to a recipient group (`groupId`).
> 3. **A value from the workflow's incoming input** — bind the recipient to a field on the request payload (e.g. the submitter's email arriving on the webhook), so each run routes to whoever the input specifies."

Do **not** frame the dynamic option as risky, unsupported, or a last resort — it is a fully valid choice.

**Bypass rule.** Only skip the ask if the *current* user prompt in this conversation already settles the source — an unambiguous email address or group ID intended for this Task Center node, **or** an explicit instruction to populate the recipient from a specific incoming input field. A recipient mentioned for a *previous* Task Center node in the same workflow does not carry over unless the user explicitly says so.

**Sufficient answer.** Any one of the three settles it — a static email (`userId`), a static group ID (`groupId`), **or** a confirmed dynamic binding (to `userId` or `groupId`).

**Binding without a round-trip.** When the user chooses dynamic and the recipient field is already identifiable — a named-node output or a webhook field documented in this conversation — bind directly to it; do **not** ask again to confirm the path. Ask for the exact field path **only** when the input shape is ambiguous (multiple plausible fields, or an undocumented payload).

**Expression style.** Prefer a named-node reference when the source node is known; use `$json` only when the current node input is the intended source and no clearer named-node reference is available. Webhook data lives under `.body.*`.

**Valid when the user chose dynamic routing:**

- ✅ `{ userId: "={{ $('Webhook').item.json.body.email }}" }`
- ✅ `{ groupId: "={{ $('Webhook').item.json.body.approverGroup }}" }` — groups are symmetric
- ✅ `{ userId: "={{ $json.body.email }}" }` — only when the current input already comes from that payload

**Forbidden — a recipient the user never authorized:**

- ❌ `{ userId: "user@example.com" }` — generated placeholder
- ❌ `{ userId: "manager@company.com" }` — copied from this skill's example
- ❌ `{ groupId: "finance-approvers" }` — guessed or example-copied group ID
- ❌ Any value — literal **or** expression — the user neither provided nor opted into. Never silently guess, and never bind to the payload unless the user chose the dynamic option.
- ✅ Ask the user first (the three-way question above), then set the recipient from their chosen source — a static `{ userId: "<exact email provided>" }` / `{ groupId: "<exact group ID provided>" }`, or a dynamic expression bound to the input field they chose.

---

### 3. **Mandatory Switch Node After Task Center**

SAP Task Center has **only ONE output** containing the decision in `$json.result.response`.

**Required pattern:**
```
Webhook → [Processing] → SAP Task Center → Switch Node → [Branches]
```

**Switch node configuration:**
```json
{
  "type": "<Switch node from MCP>",
  "typeVersion": "<from MCP>",
  "name": "Route Approval Decision",
  "parameters": {
    "mode": "rules",
    "rules": {
      "values": [
        {
          "conditions": {
            "options": {
              "caseSensitive": true,
              "leftValue": "",
              "typeValidation": "strict"
            },
            "conditions": [
              {
                "leftValue": "={{ $json.result.response }}",
                "rightValue": "approved",
                "operator": {
                  "type": "string",
                  "operation": "equals"
                }
              }
            ],
            "combinator": "and"
          },
          "renameOutput": true,
          "outputKey": "approved"
        },
        {
          "conditions": {
            "options": {
              "caseSensitive": true,
              "leftValue": "",
              "typeValidation": "strict"
            },
            "conditions": [
              {
                "leftValue": "={{ $json.result.response }}",
                "rightValue": "rejected",
                "operator": {
                  "type": "string",
                  "operation": "equals"
                }
              }
            ],
            "combinator": "and"
          },
          "renameOutput": true,
          "outputKey": "rejected"
        }
      ]
    }
  }
}
```

---

### 4. **Iterating over a Collection with Approval**

When a prompt describes both collection processing and human approval, decide which approval pattern applies **before** placing Task Center nodes. Decide in this order:

1. **What is being approved?**
   - **Each item individually** → continue to the next question.
   - **The full collection as one result** → use **Bulk approval**. Stop here.

2. **How are items delivered to the workflow?**
   - **One item per invocation** → use **Per-item approval, submitted sequentially by the caller**.
   - **A full collection in one invocation** → if items are independent (no ordering dependency, approval coupling, or rate-limit constraint between items), use **Parallel per-item processing with individual approvals**.

| Pattern | Invocation shape | Approval scope | Iteration owner | Best fit |
|---|---|---|---|---|
| Per-item approval, submitted sequentially by the caller | One item per invocation | Per item | Caller | Event-driven item intake, caller-controlled sequencing |
| Bulk approval | Full collection in one invocation | Full collection | Workflow | One approval decision for the aggregated result |
| Parallel per-item processing with individual approvals | Full collection in one invocation | Per item | Workflow | Batch trigger with independent items |

> **What "parallel"/"concurrent" means here:** independent **branches or per-item iteration within this one workflow** — not a separately-executing sub-workflow (this instance does not support sub-workflows). Convergence of any resulting branches follows the single Branch convergence decision in `execution.md` Rule 9. See the "Runtime capabilities" gate at the top of `execution.md`.

**Per-item approval, submitted sequentially by the caller:** the human reviews each item separately, and the caller controls when to submit each item.
- The iteration belongs to the caller. The workflow handles a single item: it receives one item, processes it through analysis and human approval, and returns the result.
- Choose this pattern when the prompt implies items arrive one at a time (for example, "when an invoice is submitted" or "for each incoming request") or when the caller must control sequencing because of ordering dependencies, rate limits, or partial processing.
- **If the prompt implies a batch trigger** (for example, "process all blocked invoices," "run for the backlog," or "handle the collection"), **do not use this pattern; use the parallel pattern instead.**
- Reason: sequential submission avoids embedding human wait time inside a long-running workflow. Each invocation handles one item, and the caller decides when to submit the next item.

**Bulk approval:** the human reviews and decides on the full collection in one step.
- The automated processing runs over the collection, results are consolidated, and a single human approval step covers the whole batch.
- Reason: because the wait occurs once regardless of collection size, the workflow correctly owns both the iteration and the single approval gate.

**Parallel per-item processing with individual approvals:** the workflow receives the full collection in a single invocation, processes items concurrently, and sends each item for approval independently.
- The iteration stays inside the workflow. Automated analysis runs in parallel across all items, and each approval request is issued independently.
- Choose this pattern when the prompt implies a batch trigger (for example, "process all blocked invoices," "run nightly for the backlog," or "handle the collection on schedule"), items are independent, and no ordering dependency, approval coupling, or rate-limit constraint is mentioned.
- If external systems impose strict concurrency limits, use the **Per-item approval, submitted sequentially by the caller** pattern instead.
- Reason: concurrent processing and approval dispatch make total elapsed time depend on the slowest approval response rather than the sum of all approval times.

Whichever pattern applies, each Task Center node still follows the single-item rules above — one recipient decision routed through a Switch node on `$json.result.response`.

---

### 5. **Contextual Node Name (canvas `name`)**

The Task Center node's `name` field MUST describe the approval's purpose in the context of the surrounding solution — never the generic `"SAP Task Center"` or `"Task Center"`.

Choose a name that makes the step's intent obvious to anyone reading the workflow.

- ✅ Good: `"Approve Travel Expense"`, `"Review Budget Increase Request"`, `"Approve Leave Request"`, `"Approve Purchase Requisition"`.
- ❌ Bad: `"SAP Task Center"`, `"Approval"`, `"Task"`, `"Review Step"`.

---

### 6. **Mandatory Parameters**

**Always required:**
- `subject` (string) - Task title shown to user
- `priority` (enum) - One of: `"VERY_HIGH"`, `"HIGH"`, `"MEDIUM"`, `"LOW"`.
  - **Default to `"MEDIUM"` unless the user explicitly specified a different priority.**
- Configure at least one non-empty recipient target:
  - `recipients.recipientValues: [{ "userId": "email@example.com" }]` or `[{ "userId": "={{ $('Webhook').item.json.body.email }}" }]`
  - `recipientGroups.recipientGroupValues: [{ "groupId": "group-id" }]` or `[{ "groupId": "={{ $('Webhook').item.json.body.approverGroup }}" }]`
- You may configure both at the same time.
- Do not emit empty arrays for either field.

**Optional:**
- `taskDefinition.definitionName` (string) - Name displayed in SAP Task Center. If the user hasn't specified an explicit definition name, set this to the same value as the node's canvas `name` (see **Contextual Node Name**).
- `customAttributeDefinitions.attributes[]` - Decision-context fields shown to the approver. Each row requires `value`, `code`, `name`, and `type`. Max 30. Add only when relevant to the approval and helpful to the recipient's decision — see **Custom Attributes (Optional Decision Context)**.

**Example:**
```json
{
  "name": "Approve Travel Expense",
  "parameters": {
    "subject": "Travel Expense Approval Request",
    "priority": "MEDIUM",
    "recipients": {
      "recipientValues": [
        { "userId": "manager@company.com" }
      ]
    },
    "recipientGroups": {
      "recipientGroupValues": [
        { "groupId": "finance-approvers" }
      ]
    },
    "taskDefinition": {
      "definitionName": "Approve Travel Expense"
    }
  }
}
```

---

### 7. **Recipient Email — Must Be Explicitly Provided by the User**

**NEVER generate or guess recipient emails.**

The recipient email must come from an explicit user instruction in the conversation.
If the user has already provided the recipient email, use that exact value.
If the user chose to populate it dynamically, bind it to the known input field.
If the user has not provided it yet, stop and ask before emitting the Task Center node.

```
❌ WRONG: { userId: "user@example.com" }                          // generated placeholder
✅ RIGHT: { userId: "={{ $('Webhook').item.json.body.email }}" }  // user chose dynamic; bound to a known field
✅ RIGHT: { userId: "<the exact email they provided>" }           // user chose a static recipient
```

---

### 8. **Custom Attributes (Optional Decision Context)**

Custom attributes are labeled key/value fields attached to the task and shown to the approver **inside** SAP Task Center. Use them to put the information the recipient needs to decide right in front of them — so they don't have to leave the task to find context.

**When to use.** Add a custom attribute when a piece of information from the workflow is **relevant to this specific approval and would help the recipient decide**. Examples: the Purchase Order Number on a PO approval, the amount and currency, the requesting employee, an invoice ID.

- ✅ **Do** add attributes that aid the decision — e.g. `Purchase Order Number`, `Requested Amount`, `Vendor`.
- ❌ **Do not** add noise: attributes that are irrelevant to the decision, that merely restate the `subject`/`description` verbatim, or that add nothing the approver would act on.
- **Default to none.** If nothing adds decision value, emit no custom attributes.

**The four fields (per attribute row).** Each row lives under the node parameter `customAttributeDefinitions.attributes[]` and has exactly these fields — **all four are required**:

| Field | Param | Meaning |
|---|---|---|
| Value | `value` | The attribute's value — a static literal, or an expression referencing workflow input. |
| Attribute Code | `code` | Stable, human-readable ID in camelCase, e.g. `purchaseOrderNumber`. Max 64 characters. |
| Display Label | `name` | Human-facing label shown to the approver, e.g. `Purchase Order Number`. |
| Type | `type` | Data type of the value. One of `BOOLEAN`, `DATE`, `DATETIME`, `FLOAT`, `INTEGER`, `STRING`, `TIME`. |

**Order matters.** Attributes appear to the approver in the order you list them. List the **primary business-object key first** (e.g. Purchase Order Number, Invoice ID), then secondary details. Never bury the key at the end.

**Static vs. referenced values.** The `value` field is populated one of two ways:

- **Static** — when the agent knows the value directly, set it as a literal:

  ```json
  { "value": "Procurement" }
  ```

- **Referenced** — when the agent knows the input shape (a prior step or webhook delivers a known field, e.g. `json.body.purchaseOrderId`), reference it as an expression. Prefer a **named-node reference** over `$json`, and note that webhook data lives under `.body.*`:

  ```json
  { "value": "={{ $('Purchase Request').item.json.body.purchaseOrderId }}" }
  ```

**Limits.** Maximum **30** attributes. `code` must be ≤ 64 characters. Every row must have all four of `value`, `code`, `name`, `type` — rows missing any of these are rejected or dropped.

**Example** — the `customAttributeDefinitions` parameter nested inside a `CUSTOM.sapTaskCenter` node's `parameters` (same nesting style as `recipients` / `taskDefinition`):

```json
"customAttributeDefinitions": {
  "attributes": [
    {
      "value": "={{ $('Purchase Request').item.json.body.purchaseOrderId }}",
      "code": "purchaseOrderNumber",
      "name": "Purchase Order Number",
      "type": "STRING"
    },
    {
      "value": "={{ $('Purchase Request').item.json.body.amount }}",
      "code": "requestedAmount",
      "name": "Requested Amount (EUR)",
      "type": "FLOAT"
    }
  ]
}
```

---

### 9. **NEVER Pin Data on the Task Center Node**

**Applies ONLY to the `CUSTOM.sapTaskCenter` node** — other nodes may be pinned for testing.

Never add a `pinData` entry for the Task Center node. Pinned output replaces its execution, so **no task is created** and the approval is silently skipped. To test, pin the **trigger** instead and let the Task Center node run; to exercise post-decision branches, simulate the response **downstream** (a Set/Code node feeding the Switch), never on the node itself.

---

## Common Errors to Avoid

❌ **ERROR 1:** Missing switch node after Task Center
```
Task Center → Respond to Webhook  // WRONG - no branching
```
✅ **FIX:** Add switch
```
Task Center → Switch → [approved/rejected branches]
```

---

❌ **ERROR 2:** Recipient the user never authorized
```json
"recipientValues": [{ "userId": "user@example.com" }]                     // WRONG — generated placeholder
"recipientGroupValues": [{ "groupId": "finance-approvers" }]              // WRONG — guessed or copied value
"recipientValues": [{ "userId": "={{ $json.body.email }}" }]              // WRONG — only if the user did NOT choose dynamic routing
```
✅ **FIX:** If no source is settled, stop and ask (see **ALWAYS Ask for the recipient first**). If the user chose dynamic, bind to the known field, preferring a named node: `"recipientValues": [{ "userId": "={{ $('Webhook').item.json.body.email }}" }]`.

---

❌ **ERROR 3:** Generic Task Center node name
```json
"name": "SAP Task Center"  // WRONG — unclear to workflow readers and maintainers
```
✅ **FIX:** Rename to reflect the approval purpose, e.g. `"Approve Travel Expense"`.

---

## Example: Travel Expense Approval with SAP Task Center

```json
{
  "name": "Travel Expense Approval",
  "description": "Handles travel expense approval requests. Automatically approves expenses below 50 EUR; routes higher amounts to a manager via SAP Task Center for manual approval or rejection. Responds to the requester with the final decision.",
  "nodes": [
    {
      "parameters": {
        "httpMethod": "POST",
        "path": "expense-submitted",
        "responseMode": "responseNode",
        "options": {}
      },
      "id": "f87b684f-c68e-4019-b22e-53a8b75d6cf4",
      "name": "Expense Submitted",
      "type": "n8n-nodes-base.webhook",
      "typeVersion": 2.1,
      "position": [-416, -48],
      "webhookId": "e57d9e77-30a3-4b7f-bad5-1e3288f68617"
    },
    {
      "parameters": {
        "conditions": {
          "options": {
            "caseSensitive": true,
            "leftValue": "",
            "typeValidation": "strict"
          },
          "conditions": [
            {
              "id": "condition1",
              "leftValue": "={{ $json.body.amount }}",
              "rightValue": 50,
              "operator": {
                "type": "number",
                "operation": "lt"
              }
            }
          ],
          "combinator": "and"
        },
        "options": {}
      },
      "id": "1ef04aff-4ebe-45e1-9ebc-05874cb79392",
      "name": "Amount Below 50 EUR?",
      "type": "n8n-nodes-base.if",
      "typeVersion": 2.3,
      "position": [-176, -48]
    },
    {
      "parameters": {
        "assignments": {
          "assignments": [
            { "id": "field1", "name": "status", "value": "approved", "type": "string" },
            { "id": "field2", "name": "message", "value": "=Expense of {{ $('Expense Submitted').item.json.body.amount }} EUR auto-approved (below 50 EUR threshold).", "type": "string" },
            { "id": "field3", "name": "expenseId", "value": "={{ $('Expense Submitted').item.json.body.expenseId }}", "type": "string" }
          ]
        },
        "options": {}
      },
      "id": "4ceabcf2-ae77-4179-a5a0-7d86e38ea32a",
      "name": "Set Auto-Approved",
      "type": "n8n-nodes-base.set",
      "typeVersion": 3.4,
      "position": [416, -192]
    },
    {
      "parameters": {
        "subject": "=Approve Travel Expense for {{ $('Expense Submitted').item.json.body.employeeName }}",
        "priority": "MEDIUM",
        "description": "=Travel expense of {{ $('Expense Submitted').item.json.body.amount }} EUR submitted for approval.",
        "dueDate": "2026-04-30T00:00:00",
        "recipients": {
          "recipientValues": [
            {
              "userId": "manager@company.com"
            }
          ]
        },
        "taskDefinition": {
          "definitionName": "Approve Travel Expense"
        }
      },
      "type": "CUSTOM.sapTaskCenter",
      "typeVersion": 1,
      "position": [192, 48],
      "id": "29656fda-7d54-4279-8362-c034b6085a3c",
      "name": "Approve Travel Expense",
      "webhookId": "515abf90-3602-472a-96e6-4163feeba231"
    },
    {
      "parameters": {
        "rules": {
          "values": [
            {
              "conditions": {
                "options": {
                  "caseSensitive": true,
                  "leftValue": "",
                  "typeValidation": "strict"
                },
                "conditions": [
                  {
                    "leftValue": "={{ $json.result.response }}",
                    "rightValue": "approved",
                    "operator": {
                      "type": "string",
                      "operation": "equals"
                    }
                  }
                ],
                "combinator": "and"
              },
              "renameOutput": true,
              "outputKey": "Approved"
            },
            {
              "conditions": {
                "options": {
                  "caseSensitive": true,
                  "leftValue": "",
                  "typeValidation": "strict"
                },
                "conditions": [
                  {
                    "leftValue": "={{ $json.result.response }}",
                    "rightValue": "rejected",
                    "operator": {
                      "type": "string",
                      "operation": "equals"
                    }
                  }
                ],
                "combinator": "and"
              },
              "renameOutput": true,
              "outputKey": "Rejected"
            }
          ]
        },
        "options": {}
      },
      "type": "n8n-nodes-base.switch",
      "typeVersion": 3.4,
      "position": [416, 48],
      "id": "8c69ea2e-e2a8-4dcb-92d3-28a3b9af0a68",
      "name": "Approval Decision"
    },
    {
      "parameters": {
        "assignments": {
          "assignments": [
            { "id": "field1", "name": "status", "value": "approved", "type": "string" },
            { "id": "field2", "name": "message", "value": "=Expense of {{ $('Expense Submitted').item.json.body.amount }} EUR approved by manager.", "type": "string" },
            { "id": "field3", "name": "expenseId", "value": "={{ $('Expense Submitted').item.json.body.expenseId }}", "type": "string" }
          ]
        },
        "options": {}
      },
      "id": "60bc7ca5-3c6c-4440-b64b-55677c90a05a",
      "name": "Set Manager Approved",
      "type": "n8n-nodes-base.set",
      "typeVersion": 3.4,
      "position": [688, -32]
    },
    {
      "parameters": {
        "assignments": {
          "assignments": [
            { "id": "field1", "name": "status", "value": "rejected", "type": "string" },
            { "id": "field2", "name": "message", "value": "=Expense of {{ $('Expense Submitted').item.json.body.amount }} EUR rejected by manager.", "type": "string" },
            { "id": "field3", "name": "expenseId", "value": "={{ $('Expense Submitted').item.json.body.expenseId }}", "type": "string" }
          ]
        },
        "options": {}
      },
      "id": "39f2460c-6635-41a0-8015-9c8dc072e01e",
      "name": "Set Manager Rejected",
      "type": "n8n-nodes-base.set",
      "typeVersion": 3.4,
      "position": [688, 144]
    },
    {
      "parameters": {
        "respondWith": "json",
        "responseBody": "={{ JSON.stringify({ expenseId: $json.expenseId, status: $json.status, message: $json.message }) }}",
        "options": {
          "responseCode": 200
        }
      },
      "id": "e92a8cbd-de06-42ff-a44b-e461b766f6e2",
      "name": "Respond to Requester",
      "type": "n8n-nodes-base.respondToWebhook",
      "typeVersion": 1.5,
      "position": [1040, -128]
    }
  ],
  "connections": {
    "Expense Submitted": {
      "main": [[{ "node": "Amount Below 50 EUR?", "type": "main", "index": 0 }]]
    },
    "Amount Below 50 EUR?": {
      "main": [
        [{ "node": "Set Auto-Approved", "type": "main", "index": 0 }],
        [{ "node": "Approve Travel Expense", "type": "main", "index": 0 }]
      ]
    },
    "Approve Travel Expense": {
      "main": [
        [{ "node": "Approval Decision", "type": "main", "index": 0 }]
      ]
    },
    "Approval Decision": {
      "main": [
        [{ "node": "Set Manager Approved", "type": "main", "index": 0 }],
        [{ "node": "Set Manager Rejected", "type": "main", "index": 0 }]
      ]
    },
    "Set Auto-Approved": {
      "main": [[{ "node": "Respond to Requester", "type": "main", "index": 0 }]]
    },
    "Set Manager Approved": {
      "main": [[{ "node": "Respond to Requester", "type": "main", "index": 0 }]]
    },
    "Set Manager Rejected": {
      "main": [[{ "node": "Respond to Requester", "type": "main", "index": 0 }]]
    }
  },
  "pinData": {},
  "meta": {
    "templateCredsSetupCompleted": true
  }
}
```

---

## Testing Checklist

Before considering a Task Center workflow complete:

- [ ] Used MCP `search-nodes-catalog` to get typeVersion
- [ ] Task Center node has a contextual canvas `name` describing the approval purpose (not generic `"SAP Task Center"`)
- [ ] `taskDefinition.definitionName` is set — defaults to the node's canvas `name` unless the user specified a different label
- [ ] Task Center node has all mandatory parameters (`subject`, `priority`, at least one recipient or recipient group)
- [ ] Custom attributes are included only when they help the approver make a decision
- [ ] Each custom attribute row includes `value`, `code`, display label (`name`), and `type`
- [ ] No more than 30 custom attributes are defined
- [ ] Switch node placed immediately after Task Center
- [ ] Switch branches on `$json.result.response`
- [ ] Recipient source is user-authorized: static `userId`, static `groupId`, or approved dynamic binding
- [ ] Dynamic recipient bindings target a known input field
- [ ] Named-node expressions preferred over `$json` when the source node is known
- [ ] No guessed, placeholder, example-copied, or unapproved payload-derived recipient values
- [ ] No `credentials` block included in the workflow JSON — credentials are resolved automatically during deployment
- [ ] Workflow validates with `validate-n8n-workflow` MCP
