# Design test cases

The user journeys and the test cases that cover them. Called by
[generate-eval-scenarios](./generate-eval-scenarios.md) and, for new and changed tests, by
[extend-eval-scenarios](./extend-eval-scenarios.md).

Requires the eval requirements and the tool catalog to already be resolved.

---

## Define the user journeys

A user journey is a concrete, end-to-end interaction a user can have with the agent. These
are the coverage unit: a suite that covers every eval requirement but no complete journey
has never checked that the agent delivers anything.

If the source already documents journeys, milestones, or flows, use those. If it does not,
derive them and list them in the report so the reader can correct them.

```
User Journey ID: UJ-01
Name: Top Receivables Analysis
Trigger utterance: "Analyse my top receivables for customer C0001, company code F001"
Expected flow: fetch_accounts_receivable_data(company_code=F001, customer_account=C0001),
               then calculator for the disputed share
Expected outcome:
  - Summary identifies customer C0001 under company code F001
  - Total outstanding is approximately 12,922,923.98 - rounding acceptable
  - Disputed % of Outstanding is approximately 62.73%
  - Recommendation is specific to the overdue status, not generic
  - Actions include a Set Payment Block option with pre-filled document details
Edge cases: missing company code, unknown customer, large result volume
```

**Fill in realistic values.** Take the identifiers the journey uses from the tool's
`input_schema` — the parameter descriptions carry realistic examples (e.g. `PurchaseOrder`
*"(e.g., '4500001234')"*) — and from the source document, see
[tool-catalog](./tool-catalog.md#mock-responses-make-the-run-deterministic--not-the-answer-key).
These are the scenario's **inputs** - what the user supplies and what the tool resolves - not an
answer key. You do not see `mock_response` values (the catalog is redacted); you do not need them
for inputs. A journey written with `<AMOUNT>` produces a test written with `<AMOUNT>`, and that
test cannot run.

**Where no `mcp-mock.json` was found there is no `mock_response`**, which is the common case
on an extension. The values come from the sources that do exist, in this order:

| Take from | Gives |
|---|---|
| The capability `instruction` in `extension.yaml` | Filter constants the agent must use - a status code, a fixed flag - and the fields it must select |
| The worked example in a tool's `description` | A realistic identifier, often the only one available: `SalesOrganization eq '0001'` |
| The extension PRD and `intent.md` | Personas, scenarios, and any identifiers the document names |

Assert the parameters exactly; let the **output** check describe what the call must return in
kind rather than inventing a literal - see [Without a
`mock_response`](./tool-catalog.md#without-a-mock_response). Where no source supplies a
usable identifier, say in the report which tests need real data before they will pass. Never
invent one that looks plausible: it fails against the real backend and reads as an agent
defect.

Concrete values belong in `task_summary` as the scenario's inputs - the employee ID, customer
ID, names, codes the simulated user knows, taken from the selected mock response. The
**validations** follow the mode in
[writing-checks](./writing-checks.md#groundedness-not-invented-values): out-of-the-box they
assert that what the agent states is grounded in the tool's response, not that it equals a mock
amount; under grounding they name the real values. Do not retreat to a vague shape check either
way - "grounded and present" is a precise claim, not a shape check.

---

## The budget

**Cover every enabled dimension that applies; at most 15 test cases in total.** There is no fixed
floor — but **the target is the minimum number of files that achieves full coverage**. For a
typical OOTB run (3 enabled dimensions, 2–3 user journeys) that is **4–6 files**. Stop as soon as
coverage is complete; do not continue adding files toward the ceiling. The dimensions a run may generate are resolved in
[generate step 2b](./generate-eval-scenarios.md#2b-resolve-which-dimensions-this-run-may-generate) and
recorded in `.staging/enabled-dimensions.json`. The suite must put the agent in a situation that
exercises each enabled dimension that applies to it, and **nothing is ever generated or padded for a
dimension the registry disabled** — out-of-the-box that means safety, security, and business outcome.
Never ask the user for the number.

Coverage is per enabled dimension because each answers a different question, and a suite that exercises
one thoroughly while skipping another has a hole no total reveals. A **disabled** dimension is not a
hole — it is out of scope for this run by design, and padding toward a count that includes it is the
"never invent to reach a floor" anti-pattern.

| | |
|---|---|
| **Coverage** | Every user journey has a happy path and at least one failure path; every **enabled** dimension that applies to the agent is exercised by at least one test; every eval requirement is covered; every source requirement is exercised. |
| **Budget** | At most 15 files in total. No per-group floor — generate what the enabled dimensions and journeys require, and no more. |

### Applicability is set by the registry, not padded to a floor

A dimension contributes tests only if it is **enabled for this run** (step 2b) **and** the agent
actually implements the capability it checks. A dimension that is disabled, or that the agent has
nothing to do with, contributes nothing and **is never padded**. Report it as not applicable with the
reason.

| Group | Sized by | Not applicable when |
|---|---|---|
| Goal completion | The user journeys — one happy path plus one or two failure paths each | Never; every agent has at least one journey. |
| Correctness and compliance | The **enabled** dimensions the agent exercises — out-of-the-box `groundedness` and `digression`, plus `memory` on a stateful agent | A dimension is disabled for this run, or the agent does not implement it. `safety`/`security` are disabled (platform-owned), so they contribute nothing here. |
| Business outcome | **One test per qualifying metric — only when the `business_outcome` dimension is enabled** | Off out-of-the-box: it needs a committed metric *and* customer-seeded grounding. Returns through the grounding operation. |

### A new check is cheap, a new file is not

**The budget counts files, not assertions.** A test case carries as many checks as its
scenario supports, and a check costs a line. So the first move for an uncovered requirement
is always to look for a test already putting the agent in a situation where that requirement
applies, and add the check there.

| The uncovered requirement is about… | Add |
|---|---|
| Something the agent must say or include, in a situation an existing test already creates | a check in that test's `agent_response_validations` |
| A constraint on what it may say or must refuse, in a situation an existing test already creates | a check in that test's `rule_compliance_validations` |
| A tool call an existing test already provokes | an entry or parameter in that test's `tool_validations` |
| A *situation no existing test creates* - a different journey, a different failure, a different adversarial framing | **a new test case** |

That last row is the only one that justifies a file. The question is never "is this a
different requirement" - it is "does checking this need the agent to be somewhere no test
puts it".

Do not stretch a scenario to fit. A check only belongs in a test whose conversation actually
triggers the behaviour: bolting an authentication-refusal check onto a happy-path receivables
test gives the judge nothing to decide, and it passes or fails at random. When the situation
does not arise in that conversation, it is a new test case and it was worth the file.

This is also how the per-group floor is met honestly. Reaching 3 in a group means three
genuinely distinct situations, not one scenario written out three times with the wording
changed.

### Spend the budget in this order

Cover the essentials first, then spend what is left. Everything above a line gets a file before
anything below it does.

1. **One happy path per user journey** - without it, nothing shows the agent delivers
   anything.
2. **One failure path per journey**, drawn from its edge cases and stated failure conditions.
   Similar failure modes across journeys (e.g. two different "missing input" variants) share
   a file — only a genuinely different *situation* justifies a separate file.
3. **One test per enabled dimension that applies and is not already exercised** - a
   groundedness scenario, an off-topic/digression turn; and a business-outcome test per
   qualifying metric **only when `business_outcome` is enabled** (grounding present).
   A dimension is **already exercised** when any existing test carries a validation check
   for it — a `rule_compliance_validations` groundedness check on the happy-path test is
   sufficient; a dedicated groundedness file is not needed and must not be added.
4. **The remaining scenarios the source describes**, while files are left (ceiling 15).

### When coverage and the cap collide

Coverage can demand more than 15 - several journeys plus every enabled dimension the agent
exercises. The cap is 15. Resolve it in this order, and **never by dropping an enabled
dimension's or a journey's only coverage silently**:

1. **Fold checks rather than adding files**, per the table above. A second failure path for
   one journey is often two more checks on the first.
2. **Cut the lowest-priority files** - items 4 then 3 in the order above, taking from wherever
   coverage is most redundant.
3. **If an enabled dimension or a journey must go uncovered**, say which, by how much, and
   what is consequently unchecked.

Then report every source requirement left uncovered by name, with the reason it did not fit.

---

## Design the test cases

Every test case is a single `dynamic_conversation` step. See
[testcase-schema](./schemas.md#test-cases--testcasesidyaml) for the shape, the id format,
and how to write `task_summary`.

**Work from the source document, not from `eval.yaml`.** Go back to the PRD for the
scenario: the user journeys, the acceptance criteria with their concrete examples, the
failure conditions, the policy prose, the persona the document had in mind. The eval
requirements are a checklist to measure against - they are not the material to write from,
because the detail that makes a scenario real does not survive being compressed into a
one-line rule.

**The source document and the tool source are the only material** - `mcp-mock.json` where it
exists, otherwise the translation files or the `@tool` scan, plus `extension.yaml` on an
extension. Scenarios come from the
source; concrete values come from the mocks. Not from the agent's code - a test written
against what the implementation does asserts the agent matches itself, which every agent
passes and no regression fails.

**How many test cases is decided by [the budget](#the-budget), never by the user.** Cover
every enabled dimension that applies; at most 15 in total.

**Expect every test to cover several eval requirements.** `eval.yaml` holds several
entries and the suite holds at most 15 files, so a one-requirement-per-test suite cannot
reach parity - it is not the shape to aim for. A single receivables happy path legitimately
covers a response requirement about the summary, another about how amounts are presented, a
tool requirement about the lookup and its parameters, and a compliance requirement about not
stating unretrieved figures. Four entries, one file, four checks.

**Maintain parity as you go.** Keep the eval requirements list open beside you. Mark each
eval requirement as a test covers it, and for each test you write, note which eval
requirement or requirements it covers. When a test does not land on any eval requirement -
which happens, because the source carries scenarios the eval requirements abstracted away -
**add that eval requirement to `eval.yaml` then and there**, provided its category is still
under its ceiling of 10. That is expected, not a correction: step 4 captures what the
source states outright, and designing the scenarios is what surfaces the rest. Fixing parity
while designing is cheap; leaving it to validation means auditing the whole suite at once.

An entry added this way often belongs in a category the first pass left light; adding it
while designing is how coverage reaches the enabled dimensions.

**Track the source requirements too, not only the eval requirements.** Keep a second column:
each source requirement, acceptance criterion, milestone condition, and qualifying metric
against the test that exercises it. Parity between `eval.yaml` and the suite can be perfect
while a PRD requirement nobody turned into either is missing from both, and that is the gap
this column exists to catch.

Test cases fall into three groups, distinguished by the question each answers. **Only the
enabled dimensions are generated** (step 2b), and the suite holds at most 15 - see [the
budget](#the-budget).

### Goal completion - *is the agent delivering value?*

One test per user journey, and per milestone where the source defines them.

- **Happy path**: the full flow to successful completion, asserting the journey's expected
  outcome field by field with the real values.
- **Failure paths**: one or two per journey, drawn from its edge cases and any stated
  milestone failure conditions - upstream errors, empty results, missing input, policy
  violations.

**Coverage.** A happy path plus at least one failure path per journey. A single-journey agent
still warrants a second, distinct failure path where its edge cases justify one - two
different things going wrong, not the same failure phrased twice.

Tag `correctness`. Id `<NN>_Correctness_<Journey>`.

For a routing-only orchestrator, substitute routing paths for journeys, tag `orchestration`
plus `routing_correctness`, and omit `tool_validations`.

### Correctness and compliance - *is the agent working correctly?*

From the source document's rules, constraints, and policy statements, **limited to the
dimensions enabled for this run** (step 2b). Cover each enabled dimension the agent exercises,
and enough that **every eval requirement in `eval.yaml` is covered by at least one test** and
every source rule in scope is exercised somewhere - but write them as *situations*, not as one
file per rule. Group the rules that share a plausible conversation into one scenario and assert
each of them as its own check; a single well-chosen exchange routinely carries four or five
compliance checks.

Read the eval requirements to find out *what* must be covered; read the source to find out
*how* to provoke it. An eval requirement reading `WHEN a tool returns an error, the agent MUST
report the failure` tells you the assertion - the PRD tells you the scenario in which that
failure plausibly arises, and what the user would say.

Out-of-the-box the enabled dimensions here are **`groundedness`** (the agent states nothing
absent from its tool outputs) and **`digression`** (off-topic handling), plus **`memory`** on a
stateful agent. These are not adversarial, so most carry no `TRAP:` line. A
`TRAP:` line belongs only where an enabled dimension genuinely calls for user pressure (for
example an operational-constraint scenario once grounding is present) - see
[testcase-schema](./schemas.md#adversarial-scenarios-the-trap-line); write the trap as what the
user does, never as what the agent must do. **Never write prompt-injection or
role-play/jailbreak scenarios** ("ignore your instructions", "pretend you are…") — out of
scope, see [SKILL.md](../SKILL.md).

**`safety` and `security` are disabled here** (platform-owned - Joule scenario matching and
principal propagation), so do not generate them: step 2b leaves them out of the enabled set and
step 7's gate rejects them. Tag each test by its enabled dimension. Id
`<NN>_<Category>_<Scenario>`.

### Business outcome - *does behaviour advance the committed metrics?*

**Generated only when the `business_outcome` dimension is enabled** (step 2b) — i.e. a
committed metric *and* customer-seeded grounding are both present. **Out-of-the-box this group
is not applicable** and is reported as such: the base generate operation has no grounding, so
asserting that behaviour advanced a metric has no ground truth to measure against. It returns
through the grounding operation. The rest of this section applies once the dimension is enabled.

One test per business metric that qualified under the gate in
[derive-eval-requirements](./derive-eval-requirements.md#which-metrics-qualify).

**This group is sized by the metrics table.** Two qualifying metrics means two tests; none
means the group is not applicable and is reported as such. Never invent one to reach a count -
it would assert behaviour no committed metric asked for.

Each is anchored to a specific `[BUSINESS_METRIC: …]` eval requirement in `eval.yaml`. The
test's `description`, `agent_response_validations`, and `rule_compliance_validations` derive
directly from that eval requirement - do not invent behaviour it does not imply - and **at
least one check names the metric and its target explicitly.**

```
description: Business Outcome - agent must advance AP exception rate toward 2.0% in Invoice to Pay.
id:          04_BusinessOutcome_ApExceptionRate
tags:        [correctness, business_outcome]
```

**These are never adversarial, and they carry no `TRAP:` line.** That absence is what marks
them. The scenario is a normal request inside the metric's governed process, and the test
asserts the agent does the work that moves the metric and communicates the result.

The eval requirement supplies the assertion; the **source supplies the scenario**. Take the
governed process from the metric's `process` column and the surrounding PRD narrative, so
the request the simulated user makes is one that process would actually receive.

Assert only observable behaviour - the actions taken and what was said, never the metric
value itself. A judge scoring one conversation cannot see an aggregate rate.

### Applies to every test case

- **One `dynamic_conversation` step** per test case.
- **Put the concrete values in `task_summary`** - the identifiers, codes, and amounts the
  simulated user knows, taken from `mcp-mock.json`.
- **Set `initial_message`** when the opening turn is part of the test - a specific phrasing,
  an adversarial framing, a particular entry point. Omit it for ordinary flows.
- **Set `max_turns` deliberately.** 2–3 for a single-request scenario or a stateless agent,
  5–8 where the agent must gather missing information. It is a safety limit, not a target.
- **Never design a turn whose user input is empty or blank.** Every turn the simulated user
  sends must carry non-empty text. The evaluator rejects a turn with no user input before any
  check runs — it raises *"missing agent input"* and the whole step errors, so a test built on
  an empty or whitespace-only message never produces a verdict, only an execution error. This
  binds `initial_message` and anything `task_summary` instructs the simulated user to send. A
  source requirement about **empty-input behaviour** (e.g. "given an empty message, the agent
  still replies X") is therefore **unassertable by this harness**: do not write a test that
  sends an empty message to cover it — record it as unassertable with that reason and raise it
  with the user, exactly as for a requirement with no observable form (see
  [writing-checks](./writing-checks.md#when-nothing-about-it-is-observable)).
- **Assert groundedness, not invented values.** Out-of-the-box a check names what must be
  grounded and present - every value the agent states traces to a tool response - never a
  specific mock figure; under grounding it names the real value. See
  [writing-checks](./writing-checks.md#groundedness-not-invented-values).
- **Assert both halves of every tool call** - parameters and output. Parameters stay exactly
  asserted (the agent's contract); the output check asserts a non-error response of the expected
  kind out-of-the-box, and exact `mock_response`/real values only under grounding or where the
  value is a stated invariant.
- **Do not include deletion-type tool calls in `expected_tool_calls`.**
- Treat a tool as deletion-type when its primary effect is to remove, delete, drop, deactivate,
  or archive an entity.
- If `crudOperation` is available in the tool catalog, it is the authoritative source - use it
  and ignore the tool name and `description`. Fall back to name and description only when
  `crudOperation` is absent.
- Read, create, and update operations are permitted.
- If a scenario is only meaningful when it includes a deletion step, exclude that scenario from
  the suite instead of writing a reduced version.
- **Respect tool dependencies** from [tool-catalog](./tool-catalog.md#tool-dependencies)
  when ordering `expected_tool_calls`, and include every required parameter.
- **Put each assertion in the block that can judge it** - tool-call claims in
  `tool_validations`, never in the response blocks.
- **Give each test a unique id** in the `<NN>_<Category>_<ShortDescription>` form, matching
  `^[a-zA-Z0-9_]+$` and equal to its filename stem.
- **Give every test at least one dimension tag** from
  [test-dimensions](./schemas.md#the-tag-set). Never leave a test untagged.
- **Make every test earn its file.** Before writing one, name the eval requirements and
  source requirements it covers. A test covering exactly what another already covers is
  redundancy inside a fixed budget - fold its distinctive check into that test instead.
- **Load each test to its scenario's capacity.** Once the agent is in a situation, assert
  everything that situation makes judgeable: the values, the refusals, the tool parameters
  and outputs, the ordering. Leaving a judgeable requirement unasserted means paying for a
  second file to check it.

Vary coverage across eval requirements, tool sequences, user personas, and adversarial
setups. Avoid a set of tests that differ only in wording.

---
