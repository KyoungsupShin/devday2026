# Derive eval requirements

Reads the source document and returns the eval requirements — the three categorised lists,
with the metric gate, the `[BUSINESS_METRIC: …]` tagging, and the trust boundary already
applied.

**A subroutine, never invoked on its own.** It writes nothing. The caller decides what
happens to the result: [generate-eval-scenarios](./generate-eval-scenarios.md) writes it to
`eval.yaml`; [extend-eval-scenarios](./extend-eval-scenarios.md) reconciles it against a
baseline first.

---

## 1. Read the source

Extract three things.

**Requirements and business rules** — everything stating what the agent must, must not, or
may do. Keep each one's identifier if the document has them; they anchor the coverage
mapping in step 5.

**Milestones**, if present — id, name, the condition that counts as achieved, and any stated
failure conditions.

**Business metrics**, if present — the `## Business Metrics` table, parsed into rows of
`metric`, `baseline`, `target`, `timeline`, `process`, `source`.

### Which metrics qualify

A metric produces an eval requirement and a test only if it carries a committed target.
Apply this gate mechanically — do not judge it case by case, because the coverage score is
computed as *metrics matched ÷ metrics expected* and a silently dropped metric lowers it
with no stated reason.

| Condition | Result |
|---|---|
| Any cell is a bracketed template placeholder — `[metric name]`, `[target]` | **Skip** the row entirely. It is an unfilled template. |
| `target` is empty | **Skip** — no target committed. |
| `target` is exactly `—` (em dash) | **Skip** — the table's convention for "no target". |
| `target` is `TBD` or `N/A`, in any casing | **Skip** — not yet committed. |
| Anything else, including `0`, `>90%`, `2.0%`, `8 days` | **Qualifies.** |

`0` is a legitimate target — zero defects, zero manual touches — and must not be treated as
an empty cell.

**Report every skipped metric with the actual cell value**, so the omission is a visible
decision rather than a silent one.

Record each qualifying metric name **exactly as written**. It is copied verbatim into a tag
in step 3, and a downstream scorer matches on it.

### Tools

**Resolve the tool catalog from [tool-catalog](./tool-catalog.md) before writing any
`tool_requirements`.** Every entry in that category names a tool, and the name and its
parameters come from whichever source resolved — `mcp-mock.json` wherever it exists,
otherwise the MCP translation files on an extension or a `@tool` scan on an agent. An entry
naming a tool that does not exist, or a parameter the schema does not define, can never pass.
Deriving the other two categories without the catalog is possible; deriving this one is
not.

**Take the name the runtime uses.** On an extension that is `extension.yaml`'s `mcpToolName`
or the translation file's `tools[].name` — never the translation file's `title`, and never
what the PRD calls the capability. See [the extension tool
source](./tool-catalog.md#extension-tool-source).

See [Writing `tool_requirements`](#writing-tool_requirements) for the form.

---

## 2. Sort every rule into a category

| Category | Holds |
|---|---|
| `agent_response_requirements` | What the agent must include or communicate in its responses. |
| `tool_requirements` | How and when it must call specific tools, **named**. See [Writing `tool_requirements`](#writing-tool_requirements). |
| `rule_compliance_requirements` | Policies and constraints it must enforce. |

**Extract every testable rule the source states**, then state it at the level of generality
that covers a whole family of the source's statements rather than one of them.

**Every category holds 5 entries, and may hold up to 10.** Fifteen entries is the normal
file. A category that comes out at 2 or 3 usually means that category was not mined
thoroughly, rather than a PRD with nothing to say on it — [the budget](#the-budget) says where the missing ones
live. Work category by category and fill each one before moving on.

`rule_compliance_requirements` reads as `WHEN … the agent MUST …`. The conditional form
makes the trigger explicit, which matters most for the rules that are constraints rather
than actions.

**Name the semantic values, not a single fixture.** An eval requirement saying "the agent
reports the total" produces a test asserting a shape; "the agent reports the total
outstanding amount for the requested customer" identifies the value that matters without
binding the requirement to one customer, identifier, or mock response. Concrete identifiers,
names, dates, and amounts belong in the user journey and its validations, where they can be
checked against the relevant `mock_response`.

**This is about fixture *values*, never about tool *identity*.** A tool name and a parameter
name are not fixtures — they are the agent's contract, fixed for every session, and stripping
them produces a requirement no judge can decide. "The agent retrieves the employee's time-off
data" passes against any tool, or none. See [Writing
`tool_requirements`](#writing-tool_requirements).

### Applicability and precision

Eval requirements are reusable criteria, not copies of a single test case. Apply an
**applicability gate** to every candidate requirement:

1. State the task or response condition that makes the requirement relevant.
2. Describe the behavior that must hold across the natural variation of that task.
3. Keep concrete fixture values for the test case unless the value is itself a policy limit,
   committed business target, required field, or other invariant of the behavior.

Ask: *If the employee, customer, amount, or number of returned records changed while the task
stayed the same, would this requirement still be valid?* If not, it is too narrow for
`eval.yaml`; retain the concrete assertion in an offline or goal-completion test instead.

```yaml
# Too narrow — applies only to one fixture and belongs in a concrete test case.
- 'For employee E-1001, the response identifies the employee by name, role, and location, and states their 185.00 USD medical contribution.'

# Well-scoped — applies whenever the agent performs this task, while the test checks the
# retrieved employee's actual profile and contribution values.
- 'When preparing personalized benefits recommendations, the agent uses the verified employee profile and available plan data, and explains the rationale for the recommendations.'
- 'When discussing a benefit plan, the agent states the applicable employee contribution from the retrieved plan data.'
```

Do not create a separate requirement for every field or value in one fixture merely to make
the test more deterministic. Split requirements by meaningful behavior or task outcome, not
by rows in `mock_response`. A check such as "the agent states exactly 3 unmatched invoices"
is too narrow when the general behavior is to state the count of unmatched invoices after
matching; the exact count belongs in the test. Conversely, preserve a number when it is the
actual rule, threshold, target, required amount, or other invariant that must hold across
all applicable sessions.

Where a rule has no observable form, do not force it into an eval requirement — record it as
unassertable with a reason, per
[writing-checks](./writing-checks.md#when-nothing-about-it-is-observable).

---

## Writing `tool_requirements`

Every entry in this category **names the tool it is about, exactly as `mcp-mock.json` spells
it.** An entry that describes the capability instead of the tool — "the agent retrieves the
employee's time-off data" — is satisfied by any tool, by the wrong tool, or by an agent that
answered from memory and called nothing. It reads like a requirement and checks nothing.

State four things. The first two are mandatory; the rest apply when the source or the schema
supplies them.

| | |
|---|---|
| **The tool**, by its exact catalog name | `list_EmployeeTime_for_sfodata`, never "the time-off tool" |
| **The condition** that obliges the call | the task, the trigger, or the preceding step |
| **The parameters that matter**, by their `input_schema` names | `filter`, `approval_id` — with the value where it is fixed |
| **The ordering**, where one call must precede another | naming both tools and the relation |

```yaml
tool_requirements:
  - 'Agent must call list_EmployeeTime_for_sfodata with filter=userId eq ''<employee_id>'' to retrieve leave/time-off data for the authenticated employee.'
  - 'Agent must call get_approval_status with the approval_id before calling update_payment_info to verify the approval is in ''approved'' status.'
  - 'Agent must call get_employee_profile before recommending any benefit plan, and must not recommend a plan when the profile call returns no record.'
```

### Which values are literal and which are placeholders

The tool name and the parameter names are invariants — always literal. A parameter **value**
is literal only when it is fixed for every session.

| Value | Write it as | Why |
|---|---|---|
| An enum, status, or constant the rule depends on — `'approved'`, `status=open`, `top=50` | **Literal** | It is the rule. Softening it moves the bar. |
| A filter or query expression the source or schema mandates — `filter=userId eq '<employee_id>'` | **Literal expression, placeholder value** | The shape of the call is the contract; the id varies per session. |
| An identifier that changes per session — employee id, customer account, invoice number | **`<descriptive_placeholder>`** | Binding the requirement to one fixture makes it a test case. |
| A retrieved amount, date, name, or record count | **Omit it** | It belongs in the test's checks, against `mock_response`. |

Use a plain `<snake_case_noun>` for a placeholder — `<employee_id>`, `<company_code>`. It
names what varies without pretending to a value.

**This is the one place a placeholder is correct.** In a test case a placeholder is a defect:
the judge reads `<employee_id>` literally and the check can never pass, which is why
[validate-and-report](./validate-and-report.md#1-validate) rejects them there. In `eval.yaml`
an entry is a reusable rule rather than a judged string, and the placeholder is what keeps it
reusable. The concrete value appears in the test that covers it.

### Every named tool must exist

Check each name against the catalog before writing it. A misspelt or invented tool name
produces a `tool_validations` block asserting a call that can never happen — the test fails
on every run, and it fails looking like an agent bug rather than a generation error.

On an extension, "exists" means **granted by `extension.yaml`**, not merely present in a
translation file. A tool the translation file describes but the extension does not grant is
not callable by the extended agent, and a requirement for it can never pass.

Where two servers define the same tool name, say which one the entry means, per
[tool-catalog](./tool-catalog.md#2-read-the-tools).

### Do not require a tool the agent is merely permitted to use

An entry here makes the call **mandatory**: the covering test fails if the tool was not
called at all. Write one only for a call the source obliges. A tool the agent may use at its
discretion belongs in no requirement — turning an option into an obligation marks down an
agent that solved the task a better way.

For a routing-only orchestrator with no direct tool access, this category is not applicable.
Report it as such rather than inventing entries for tools the agent cannot call.

---

## The budget

Applies while sorting in step 2, and again before returning in step 5.

**Up to 10 eval requirements per category — 10 is the ceiling, and there is no fixed floor.**
Counted per category, not across the file: `agent_response_requirements`, `tool_requirements`,
and `rule_compliance_requirements` are each capped at 10. Derive what the source states and what
the **enabled** dimensions require (resolved in
[generate step 2b](./generate-eval-scenarios.md#2b-resolve-which-dimensions-this-run-may-generate))
— no more. **Do not mine requirements for a disabled dimension** (safety, security, and —
without customer grounding — business outcome): a requirement no in-scope test can cover is an
orphan the parity check rejects. An out-of-the-box file is therefore smaller than it used to be,
and that is correct — there is genuinely less to assert without ground truth.

| Per category | Meaning |
|---|---|
| **1–10** | Everything the source states and the enabled dimensions require, within scope. |
| **0** | Legitimate when the enabled dimensions imply nothing for that category. Write an empty list and say so; never invent an entry to fill it. |

Balance across the three still matters: a file that checks what the agent *says* in detail and
barely checks what it *does* has a hole no total reveals. Re-file a misplaced entry before
concluding a category is light.

Two rules hold simultaneously and neither yields to the other:

| | |
|---|---|
| **Coverage** | Every source requirement, acceptance criterion, milestone condition, and qualifying business metric produces at least one eval requirement. |
| **Budget** | Each category holds 5 to 10 entries. |

### Where the entries come from

Each category has a small number of recurring obligation types that an agent PRD implies.
**Walk the rows, and for each one ask what this source says about it — but skip any row whose
dimension is disabled for this run** (step 2b). A row the source genuinely does not touch is
skipped too; most sources touch most in-scope rows.

Every entry still traces to something the document states or directly implies — the table
tells you where to look, not what to invent, and the enabled set tells you which rows are in
scope.

**`agent_response_requirements` — what the agent must communicate**

| Look for | Typical entry |
|---|---|
| The outcome of each user journey | What the response must contain for the task to be done. |
| How retrieved values must be presented | Amounts with currency, records with their identifiers, dates in the stated form. |
| The empty or zero-result path | What the agent says when there is nothing to report. |
| The error path | What it says when a tool or upstream system fails. |
| Missing or ambiguous input | That it asks for the missing input rather than assuming one. |
| Recommendations or next actions, where the source asks for them | That they are specific to the retrieved situation, not generic. |
| Any qualifying business metric whose obligation is about output | The tagged entry. |

**`tool_requirements` — how and when tools are called.** Every entry names its tool, per
[Writing `tool_requirements`](#writing-tool_requirements). Walk the catalog alongside the
source: each tool the agent has is a candidate row, and the source says when it is obliged.

| Look for | Typical entry |
|---|---|
| The tool each journey depends on | `Agent must call <tool> when <trigger>, rather than answering from prior context.` |
| Required parameters from `input_schema` | `Agent must call <tool> with <param>=<value or placeholder> taken from what the user supplied.` |
| Ordering and dependencies | `Agent must call <lookup_tool> before <action_tool> to <reason>.` |
| Tool failure | `WHEN <tool> returns an error, the agent must report the failure and must not state that <action> succeeded.` |
| State-changing tools | `Agent must not call <write_tool> before the user confirms <the details the source names>.` |
| Tool selection | `Agent must call <tool> rather than <near_neighbour_tool> when <the distinguishing condition>.` |

**`rule_compliance_requirements` — the constraints, in `WHEN … the agent MUST …` form**

| Look for | Typical entry |
|---|---|
| Stated policies and business rules | The rule as written, in conditional form. |
| Thresholds, limits, and approval gates | The obligation the limit creates. |
| Fabrication *(`groundedness` — enabled)* | That the agent states no figure it did not retrieve. |
| Scope *(`digression` — enabled)* | That out-of-scope requests are declined rather than attempted. |
| Data disclosure and permissions *(`security` — disabled out-of-the-box)* | What must not be revealed, and to whom. Mine only when `security`/operational-constraint is enabled (grounding present). |
| Confirmation before consequential action *(`safety` — disabled out-of-the-box)* | What must be restated back before it proceeds. Mine only when `safety` is enabled. |

### A light category

A category with few entries is often correct now — there is simply less in scope. Before
concluding it is light, check two things:

1. **Split a bundled entry.** An entry joined by "and" was always two entries — separating them
   is a correction, not padding.
2. **Add the error and empty paths, and the fabrication and scope rules — but only for enabled
   dimensions.** The error/empty-result obligations and the fabrication (`groundedness`) and
   scope (`digression`) rules are in scope out-of-the-box; disclosure (`security`) and
   confirmation (`safety`) are not, so do not add them to reach a count.

Then **write what is real and report it** — naming the in-scope rows the source said nothing
about. **Never invent an entry to reach a count**: a requirement the source never stated is one
the tests must then satisfy, and the agent is marked down for behaviour nobody asked of it. A
category that is light because its dimensions are disabled is not a finding — it is the cut
working as designed.

A genuinely inapplicable category — `tool_requirements` for a routing-only orchestrator — is
reported as not applicable rather than as light.

### Spend the budget in this order

Within each category, work down the list. Everything above a line gets an entry before
anything below it does.

1. **Every qualifying business metric — only when `business_outcome` is enabled** (grounding
   present). One tagged entry each, in whichever category fits. Out-of-the-box the dimension is
   off: skip these and report the metrics as deferred to the grounding operation, rather than
   writing a tagged requirement no test can cover.
2. **Every stated MUST, MUST NOT, and policy constraint** — the rules whose violation is a
   defect.
3. **Every milestone's achieved condition** that has an observable form.
4. **The core obligations of each user journey** — what the agent has to produce for the
   journey to have delivered anything.
5. **The recurring obligation types** from the tables above that the source implies but never
   spells out.

### Consolidate before exceeding 10 in a category

At 11 in one category, check the surplus is not one of these:

| Pattern | Fix |
|---|---|
| One entry per field or row of a `mock_response` | One entry naming the behaviour; the fields go in the test's checks. |
| One entry per fixture — per customer, employee, invoice | One entry scoped to the task; the identifiers go in `task_summary`. |
| Two entries differing only in which tool is named, where the obligation is identical | One entry stating the obligation, with the tools enumerated in it. |
| An entry restating another at a different grain | Keep the one that fails when the behaviour breaks; drop the other. |
| An entry covering a PRD sentence that is background, rationale, or a non-functional aside | Not a testable rule. Record it as out of scope, not as an entry. |
| An entry sitting in the wrong category | Move it. A tool-ordering rule in `agent_response_requirements` inflates one category while starving another. |

**Consolidating is not bundling.** An entry joined by "and" is two entries wearing one
string, and a judge given it has no correct verdict for the half-satisfied case — see
[writing-checks](./writing-checks.md#one-check-one-claim). Merge requirements that describe
*the same behaviour*; never staple together two behaviours to save a slot.

If a category genuinely holds more than 10 distinct obligations after that, keep the 10
highest in the priority order above and report every source requirement left uncovered by
name, with the reason it did not fit.

---

## 3. Tag the business metrics

**Only when the `business_outcome` dimension is enabled** (step 2b — i.e. customer grounding is
present). Out-of-the-box business outcome is disabled: a `[BUSINESS_METRIC: …]` requirement with
no business-outcome test to cover it is an orphan, and without grounding there is no ground
truth to measure the metric against. When the dimension is off, skip this step and report the
qualifying metrics as deferred to the grounding operation.

For every metric that qualified in step 1, write **at least one** eval requirement prefixed
with `[BUSINESS_METRIC: <metric name>]`, the name copied exactly from the table.

Place it in whichever category fits: output → `agent_response_requirements`, tool invocation
→ `tool_requirements`, policy → `rule_compliance_requirements`.

```yaml
  agent_response_requirements:
    - '[BUSINESS_METRIC: AP exception rate] The agent states, per invoice, whether it was processed cleanly or flagged, referencing the 2.0% target governed by Invoice to Pay.'
  rule_compliance_requirements:
    - '[BUSINESS_METRIC: AP exception rate] WHEN an invoice carries an unresolved variance, the agent MUST flag it rather than post it.'
```

Name the metric's target inside the eval requirement text as well as in the tag. The tag is
what the scorer matches; the target in the body is what makes the eval requirement testable.

**The tag is a prefix on a normal string.** It is never a new field, never a new key, and
never a new top-level category. Adding one produces a file that parses and that the scorer
reads as empty.

The tag must be copied verbatim and may only assert observable behaviour — see
[writing-checks](./writing-checks.md#tag-business-metrics-verbatim).

---

## 4. Apply the trust boundary now

Run [the trust boundary](./writing-checks.md#the-trust-boundary) over every eval requirement
**before** it reaches the file or the caller. Any rule describing a security control in
operational detail is rewritten to the obligation it checks.

Do it here, not later. An eval requirement rewritten once is rewritten everywhere it is
read; catching it after the test cases are written means fixing the same wording in several
files and missing one.

---

## 5. Return and map

Return the categorised eval requirements to the caller. **Write nothing.**

Record the **source-to-requirements mapping** — each source requirement, acceptance
criterion, milestone condition, and business metric against the eval requirement or
requirements it produced. This is working analysis, not a file, and it is what the caller
measures coverage against.

**Build it while deriving, not afterwards.** A requirement that never became an eval
requirement fails nothing and shows up nowhere — the run looks entirely healthy with half
the source missing, which is exactly what this mapping exists to catch. Anything that
produced no eval requirement is either **unassertable**, with a one-line reason, or an
**omission** to fix.

**Walk the source, not the requirements.** Go through the source document's rules in order
and confirm each one has a row in the mapping. Walking the eval requirements instead only
proves that what you wrote came from somewhere — it can never reveal what you never wrote.

Then check the count against [the budget](#the-budget) before returning — **per category, not
just the total.** A light category is re-checked against its in-scope table rows before it is
reported as light. Over 10 in a category, consolidate per the table above and re-check the
mapping afterwards, because a merge that quietly drops a behaviour is the one way consolidation
breaks coverage.

**Return these to the caller. Do not write a report section** — this is a subroutine, and
the caller folds what matters into [the one
report](./validate-and-report.md#the-report):

- **How many eval requirements in each category** (ceiling 10, no fixed floor). Give the three
  numbers separately; a total hides an unbalanced file.
- **Every category that came in light**, with the in-scope rows of its table in [where the
  entries come from](#where-the-entries-come-from) that the source said nothing about.
- **Every source requirement with no eval requirement**, and why — unassertable, out of
  scope, or not a testable statement.
- **Every consolidation** that merged two or more source rules into one entry.
- **Every business metric skipped in step 1**, with its actual `target` cell value.
- Any eval requirement rewritten under the trust boundary, described by what it now checks.
