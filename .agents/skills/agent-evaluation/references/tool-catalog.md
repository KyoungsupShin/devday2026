# Tool catalog

Resolves the agent's tools into working memory. **This operation writes no file.** It is a
read that other operations perform; the result is used in place and discarded.

## Which source applies

**`mcp-mock.json` is preferred wherever it exists, and optional everywhere.** Look for it
first, whatever the operation. When it is absent, fall back to the discovery the operation
supports.

| Order | Source | Applies to |
|---|---|---|
| 1 | **`mcp-mock.json`** — see [Locate the file](#1-locate-the-file) | Either operation, whenever the file is present |
| 2 | **`extension.yaml` + the MCP translation files** — see [Extension tool source](#extension-tool-source) | An extension with no `mcp-mock.json` |
| 2 | **`@tool` scan of the agent's code** — see [Fallback](#fallback-no-mcp-mockjson) | An agent with no `mcp-mock.json` |

Prefer it because of its **`mock_response` field names**: each tool declares the shape of what it
returns, so an in-kind `output` check can name the real fields a call must carry (`supplier`, `net
order value`). No rank-2 source has even that, and tools resolved from one assert a looser in-kind
output — see [Without a `mock_response`](#without-a-mock_response). You read it through the
redaction script (step 2), so you get the field names and never the values.

**On an extension, the two sources compose rather than compete.** `mcp-mock.json` describes
tools; `extension.yaml` decides which ones the extended agent may call and states when it
must. Read `extension.yaml` either way — its `instruction` block is a behavioural source, not
merely a tool list, and it is the richest input for `tool_requirements`.

| Question | Answered by |
|---|---|
| Which tools can the agent call? | `extension.yaml`'s `mcpToolName` on an extension; the `mcp-mock.json` tool list on an agent |
| What does each take, and what does it return? | `mcp-mock.json` if present, else the translation file or the `@tool` scan |
| When must it be called, and with what? | The capability `instruction` and the source document |

A tool in `mcp-mock.json` that `extension.yaml` does not grant is **not callable** by the
extended agent. Do not write a requirement for it; report the discrepancy.

---

## The preferred source: `mcp-mock.json`

When present — on either operation — `mcp-mock.json` is the tool source. It is written by the `mcp-mock-config`
skill, not by this one — never modify it, and never write a derived copy of it. You read it only
through the redaction script in [step 2](#2-read-the-tools--through-the-redaction-script-never-raw);
do not open the raw file.

It is what the agent runs against in test mode — its MCP provider builds its tools from this
file, so every tool here is a tool the agent has, with the parameters the agent will see.

**When it exists, use it (via the script) and stop looking.** It is complete by construction for
what a test needs to know: the tool name, description, `input_schema`, and the `mock_response`
field names. Opening
the agent's source to verify a signature, understand what a tool "really" does, or look for
tools the file might have missed is wasted context, and it seeds tests with implementation
detail the source document never required. Do not run a rank-2 source as a supplement or a
cross-check — the one thing still read alongside it on an extension is `extension.yaml`, for
grants and the instruction block, never to re-describe a tool.

---

## 1. Locate the file

Search in the order given in [paths](../SKILL.md#paths):

1. `{output_dir}/mcp-mock.json` — the agent's asset root, where it belongs
2. `<solution-root>/assets/*/mcp-mock.json`
3. Anywhere under the solution root, **excluding any path containing a `.claude/` segment**

**Stop at the first hit.** Report which path was used, then go straight to step 2 — no
further searching, and no reading of anything else in the repository.

A hit at step 2 in an asset folder other than `{output_dir}` is worth a line in the report:
either the tool catalog or the resolved asset folder is wrong, and the tests will be written
against another asset's tools if it is the latter.

If none is found, go to [Fallback](#fallback-no-mcp-mockjson).

---

## 2. Read the tools — through the redaction script, never raw

**Do not read `mcp-mock.json` directly.** Run the extraction script and read *its* output as the
catalog:

```
python3 skills/agent-evaluation/scripts/extract-tool-catalog.py <path-from-step-1>
```

(workspace-root-relative, like the other scripts — if the skill is mounted under a different root,
resolve it beside this skill at `scripts/extract-tool-catalog.py`.) It prints the full catalog with
every `mock_response` reduced to a **type skeleton**: field names and structure kept, every leaf
value replaced by a `<string>` / `<integer>` / `<number>` / `<boolean>` / `<null>` placeholder, and
lists collapsed to a single skeleton element. It writes no file; its stdout *is* the catalog.

Why through the script: the raw `mock_response` carries invented values (`"Supplier":
"SUPPLIER-001"`, `"NetOrderValue": "45000.00"`). Reading them into context is what makes the
generator pin them into test cases — a value the model never sees is a value it cannot assert. The
skeleton keeps exactly what a test legitimately needs (the real **field names**, so an in-kind
output check can name `supplier` and `net order value`) and removes exactly what poisons it (the
values). The aeval **runtime** still reads the full `mcp-mock.json` for its deterministic responses;
only the **generator** reads this redacted view.

The script's output shape is:

```json
{
  "servers": {
    "<server-slug>": {
      "mcp_server_name": "com.sap.s4/API_SUPPLIERINVOICE_PROCESS_SRV",
      "description": "...",
      "tools": {
        "<tool_name>": {
          "description": "...",
          "input_schema": { "type": "object", "properties": {}, "required": [] },
          "mock_response": { "SupplierInvoice": "<string>", "InvoiceGrossAmount": "<string>" }
        }
      }
    }
  },
  "metadata": { }
}
```

For every server in `servers`, iterate its `tools` map and collect per tool:

| Field | From | Missing |
|---|---|---|
| `name` | the tool key | — |
| `server` | the server slug | — |
| `description` | `tools.<name>.description` | `"No description available."` |
| `parameters` | `tools.<name>.input_schema` | `{"type": "object", "properties": {}, "required": []}` |
| `required` | `input_schema.required` | `[]` |
| `mock_response` | `tools.<name>.mock_response` — the **type skeleton** (field names + types, no values) | absent — note it |

Tool names are unique across the whole catalog in practice. If two servers define the same
tool name, keep both and record the collision — a `tool_validations` entry names a tool by
name alone and cannot disambiguate, so the report must say which one the tests target.

Report: `Loaded N tools from M servers in <path>`.

---

## Mock responses make the run deterministic — not the answer key

**Applies whenever `mcp-mock.json` was found**, on either operation. Where it was not, the
substitute is [Without a `mock_response`](#without-a-mock_response).

`mock_response` is what the tool returns when the agent runs in test mode. It is
deterministic by construction — which makes the **run** reproducible, so the agent can proceed
and the test runs the moment it is written. It does **not** make the agent's answer *correct*:
the mock is invented data, not the customer's real system, so a check asserting a mock value as
the right business result tests fixture-parroting and breaks against live data. See
[groundedness, not invented values](./writing-checks.md#groundedness-not-invented-values).
**You never see the mock's values** — the catalog you read is the redacted skeleton (step 2), so
the figures are not in your context to assert even by accident. You see the **field names**; use
them, never a value.

Use it two ways:

**1. Take realistic identifiers from `input_schema`, and assert the exact `parameters`.** The
identifiers the simulated user supplies (a PO number, an invoice id) come from the parameter
descriptions in `input_schema` — e.g. `"PurchaseOrder": {"description": "... (e.g.,
'4500001234')"}` — and from the source document, never from a `mock_response` value (you no longer
see those). The mock resolves any input to its deterministic response, so a realistic, well-formed
identifier is all a happy-path test needs. Assert the tool `parameters` from these **exactly**;
they are the agent's contract.

**2. Use the response *field names* in the `output` check — the skeleton gives you exactly
these.** Out-of-the-box, describe what the call must return in kind, naming the fields the skeleton
shows but never a value:

```json
"mock_response": {
  "results": [
    {"SupplierInvoice": "<string>", "InvoiceGrossAmount": "<string>", "DocumentCurrency": "<string>"}
  ]
}
```

```yaml
          output:
            check: >
              The tool returns a non-error response carrying a supplier invoice with a gross
              amount and a document currency.
```

Under the grounding operation the real values come from the **grounding file** (not the mock), so
there you assert them exactly (`supplier invoice 5100000001, gross amount 75000.00 USD`). The same
holds for `agent_response_validations`: out-of-the-box, assert every figure the agent states is
grounded in what the tool returned; under grounding, name the real value from the grounding.

Where a tool has no `mock_response`, say so in the report: its tests assert parameters and an
in-kind output description — which is the out-of-the-box default anyway. See
[writing-checks](./writing-checks.md#tool-validations-need-both-halves).

---

## Tool dependencies

Before generating anything, work out which tools consume another tool's output. Record only
real dependencies:

```
book_flight        needs get_user_details, search_flights
send_confirmation  needs book_flight
```

Infer these from parameter names matching another tool's output fields, and from the source
document's described flow. **Where the source states an explicit sequence, that takes
precedence over inference.**

This governs the ordering of `expected_tool_calls`. A dependency-violating order produces a
test that can never pass and looks like an agent bug.

---

## Extension tool source

For [extend-eval-scenarios](./extend-eval-scenarios.md). Two files, each answering a
different question.

**`extension.yaml` is read on every extension run.** It answers which tools the agent may
call and when it must call them, and no other source answers either. **The translation file
is the rank-2 description**, read only when no `mcp-mock.json` was found — when one was, it
describes the tools instead and the translation file is redundant.

### 1. `extension.yaml` — which tools, and when

At `<solution-root>/assets/*/extension.yaml`, in the asset whose `asset.yaml` declares
`type: agent-extension`. Read two things per capability under
`capabilityImplementations[]`:

| Field | Gives |
|---|---|
| `tools[].mcpToolName` | **The authoritative list of tools the extension grants.** A tool absent here is one the extended agent cannot call, whatever a translation file says. |
| `instruction` | When each tool must be used, in the capability's own numbered steps — frequently including the exact filter expression and the fields to select. |

The `instruction` block is the richest single source for `tool_requirements`. A step reading
*"Use the `list_openbillingitems_for_billing` tool with filter:
`SalesOrganization eq '<salesOrg>' and OverallBillingDocReqStatus eq 'A'`"* supplies the tool,
the parameter, the constant, and the varying value in one line — which is exactly the shape
an entry needs, per [Writing
`tool_requirements`](./derive-eval-requirements.md#writing-tool_requirements).

Also record `hooks[]`, whose agent-visible consequences are derivable but whose execution is
not — see
[writing-checks](./writing-checks.md#when-nothing-about-it-is-observable).

### 2. The translation file — what each tool takes

**Skip this when `mcp-mock.json` was found** — it already carries each tool's description and
`input_schema`, with mock values the translation file does not have.

At `<solution-root>/assets/*/mcp-translation/translation.json`, in the MCP server assets.
These are **sibling assets** of the extension, so resolve them from the solution root, not
from `output_dir`.

```json
{
  "target":     { "ordId": "example:apiResource:OPEN_BILLING_ITEMS:v1" },
  "serverInfo": { "name": "example.mcp/billing" },
  "tools": [
    {
      "name": "list_openbillingitems_for_billing",
      "title": "list_OpenBillingItems_for_billing",
      "description": "Retrieve a list of OpenBillingItem entities. Supports $filter (e.g. SalesOrganization eq '0001' ...), $select, $top, ...",
      "odataType": { "entitySet": { "name": "OpenBillingItem", "crudOperation": "read",
                                    "parameters": [ { "name": "filter" }, { "name": "top" } ] } }
    }
  ]
}
```

| Field | From | Notes |
|---|---|---|
| `name` | `tools[].name` | **The name to use everywhere.** Matches `mcpToolName`, and is what the runtime registers. |
| `description` | `tools[].description` | Often carries a worked filter example — the best available substitute for a mock response. |
| `parameters` | `tools[].odataType.<kind>.parameters[].name` | The parameter names a requirement or validation may cite. |
| `crudOperation` | `tools[].odataType.<kind>.crudOperation` | `read` versus a write operation decides whether confirmation-before-action applies. |

**Use `name`, never `title`.** Both exist and differ only in casing —
`list_openbillingitems_for_billing` against
`list_OpenBillingItems_for_billing`. `name` is what `extension.yaml` references and
what the trace reports, so a validation written against `title` fails on every run while
looking like the agent called the wrong tool.

A sibling `.tool-list.json` is the full, un-pruned backup of every tool the API exposes.
`translation.json` is the pruned set that is actually deployed and wired into the agent, so the
entries in its `tools` property are a **subset** of the entries in `.tool-list.json` (the rest
of `translation.json`, e.g. the MCP server metadata, has no counterpart in the backup).
**Use `translation.json`**: it reflects the tools the
agent can really call. Do not build the catalog from `.tool-list.json`; it lists tools that were
deliberately disabled and are not available to the extended agent. If `translation.json` is
missing while `.tool-list.json` is present, do **not** fall back to `.tool-list.json`: the MCP
server asset is corrupted (the authoritative tool set has been lost). Report it and stop rather
than building a catalog from the backup.

### Reconcile grants against descriptions

`extension.yaml` decides membership; whichever description source applies fills in the
detail. The same reconciliation holds whether that source is `mcp-mock.json` or a translation
file:

| Case | Do |
|---|---|
| Described but **not granted** by `extension.yaml` | Not available to the extended agent. Write no requirement for it, and report it. |
| Granted but **not described** anywhere | Available but undescribed. Name it, assert parameters only where the `instruction` states them, and say so in the report. |

Report: `Loaded N tools granted by the extension, described by M entries in <source>`.

### Without a `mock_response`

**Applies whenever no `mcp-mock.json` was found** — an extension falling back to translation
files, or an agent falling back to a `@tool` scan. When one *was* found, none of this applies
and the expected values are knowable as usual.

No rank-2 source says what a tool returns, so the deterministic expected values are not
available. Three consequences:

| | |
|---|---|
| `tool_validations` `output` | A `check` describing what the call must return in kind — entity, key fields, ordering — never an invented literal. Parameters stay exactly asserted; only the output softens. |
| Concrete values in `task_summary` | Taken from the `instruction`'s filter constants, the worked example in a tool `description`, and the PRD. Where none supplies one, say in the report which tests need real data before they can pass. |
| The report | Must state that output assertions are descriptions rather than known values, so nobody reads a passing run as confirmation of the returned data. |

**Never invent a plausible response and assert it.** A fabricated literal fails against the
real backend and looks like an agent defect — the exact failure the mock existed to prevent.

---

## Fallback: no `mcp-mock.json`

**Agent flow only.** On an extension the rank-2 source is
[`extension.yaml` and the translation files](#extension-tool-source): the solution does not
contain the base agent's implementation, so there is nothing here to scan.

**Only when the search in step 1 finds nothing.** This is the sole circumstance in which the
agent's code is read at all. If a `mcp-mock.json` was found, this section does not apply —
do not run it as a supplement, a cross-check, or a completeness sweep.

Say so first:

> No `mcp-mock.json` found. It is normally generated by the `mcp-mock-config` skill, and
> running that first gives the tests deterministic mock responses to assert against.

If the user proceeds anyway, scan the agent source for `@tool`-decorated **module-level**
functions, excluding any path containing a `.claude/` segment. Per function take the name as
written, the first non-empty docstring line as the description (else `"No description
available."`), and one parameter per argument excluding `self` — `required: true` when it
has no default. Take each parameter description from the matching `<param>: <text>` line in
the docstring's `Args:` block. Skip class methods, nested functions, and names starting with
`_`.

**Keep the scan narrow.** Read only what is needed to find `@tool` definitions and their
signatures. Do not read tool bodies, prompts, orchestration code, tests, or configuration —
none of it changes the catalog, and all of it costs context.

Map type hints: `str`→`string`, `int`→`integer`, `float`→`number`, `bool`→`boolean`,
`List`/`list`→`array`, `Dict`/`dict`→`object`, `Optional[X]`→ map `X` with `required:
false`. Anything else, including `Any` and unhinted, → `string`.

**Write nothing** — the result stays in working memory.

These tools have **no mock responses**, so every `output` assertion becomes a description
rather than a known value and `task_summary` values are invented. Say so in the report.

If neither the file nor any `@tool` function is found, **stop**. A suite generated against
no tools has no `tool_validations`, passes trivially, and looks like coverage.

---

## Return to the caller

**This is a subroutine. It emits no report section of its own** — an extension run that let
every sub-operation report separately produces four stacked reports saying overlapping
things. Return these to the caller, which folds what matters into [the one
report](./validate-and-report.md#the-report):

- **Source used**, and whether a `mcp-mock.json` was found — that single fact decides whether
  output assertions carry real values.
- **Tools resolved**: count, and for an extension how many are granted versus described.
- **Tools with no `mock_response`**, by name.
- **Dependencies**, per [Tool dependencies](#tool-dependencies).
- **Warnings**: duplicate names across servers, missing descriptions or schemas, and — on an
  extension — anything granted but undescribed, or described but not granted.

Of these, only the source, the count, and any warnings normally reach the reader. The
dependency map and the per-tool detail are working analysis.
