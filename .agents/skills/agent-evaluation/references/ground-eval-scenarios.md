# Ground eval scenarios

Upgrades a functional-liveness eval suite into a **grounded** one using the customer's real data.
This is the **only** operation that may assert business-correct values and generate the
ground-truth dimensions — business outcome, summarisation quality, RAG relevance, and
operational constraints. Everything else in the skill is deliberately functional-liveness only,
because out-of-the-box there is no ground truth; this operation is where the customer supplies it.

**Precondition: a functional suite already exists** at `{output_dir}/aeval/` (from
[generate-eval-scenarios](./generate-eval-scenarios.md)). This operation *upgrades* that suite in
place — it does not regenerate it. If no suite exists yet, say so and tell the customer to run the
base generation first.

Read [writing-checks](./writing-checks.md) and [schemas](./schemas.md) first, as every operation
does — most of all [groundedness, not invented
values](./writing-checks.md#groundedness-not-invented-values), whose **grounded** mode is exactly
what this operation switches on.

---

## 1. Collect inputs and locate the grounding

| Input | Required | Notes |
|---|---|---|
| Source document path | yes | The PRD, as in generate. |
| `mcp-mock.json` path | no | Located per [tool-catalog](./tool-catalog.md). |
| The existing `aeval/` suite | yes | The functional baseline this operation upgrades. |
| **The grounding** | yes | Where the customer's real data lives — see below. |

Resolve `output_dir` per [paths](../SKILL.md#paths), exactly as generate does.

**The customer declares where the grounding is**, in their request — e.g. *"create grounded
evaluation scenarios, the grounding is at `assets/<agent>/grounding.yaml`"* or *"…the grounding is
in the PRD under ## Eval Grounding"*. Two forms:

| Form | How to read it |
|---|---|
| **A grounding file** (recommended) — a path to a `.yaml` / `.json` / `.csv` / `.md` file of real expected values | Read that file. |
| **Inline in the PRD** — a named section (`## Eval Grounding`, `## Grounding Data`, or whatever the customer names) | Read that section of the source document. |

**Deterministic access check — do this before anything else.** Attempt to read the declared
location. If it cannot be read — the path does not resolve, the file is empty, or the named PRD
section is absent — **stop.** Report, in one line, exactly what you looked for and where, and that
no grounded cases can be written until the grounding is reachable there. **Never fabricate
grounding, and never fall back to `mcp-mock.json` values as if they were real** — that is the exact
mistake this whole operation exists to avoid. The access check is deterministic: either the
location reads or it does not.

Then run the resume check and set up `.staging/` as in
[generate step 2b's staging](./generate-eval-scenarios.md#where-generation-happens-staging-and-resume).

---

## 2. Read the grounding and establish what it unlocks

Read the grounding data. It supplies the **real expected values** the mock could never give —
per user journey, scenario, tool, or field — and may also declare:

- **Committed metric targets** — the real target for a business metric (enables business outcome).
- **Forbidden operations** — operations the agent must never attempt (enables operational
  constraints). The customer states the operation; the eval asserts the call is absent or refused,
  which is trace-observable and needs no further ground truth.

Grounding content is the customer's, so accept the shape they gave and interpret it against the
journeys and tools — a mapping of *scenario/field → expected value* is the natural form, but do not
reject a reasonable alternative. A field the grounding does **not** cover simply stays functional
(step 4). Record anything in the grounding that maps to nothing, for the report.

Determine the context flags as in [generate step 2](./generate-eval-scenarios.md#2-establish-the-agent-architecture)
(architecture, stateful, summarises, retrieval), **plus** from the grounding: whether a qualifying
metric target is present, and whether a forbidden operation is declared.

---

## 3. Resolve the enabled dimensions — with grounding on

Run the resolver with `--grounding-present` and the flags that hold, writing the enabled set to
staging:

```
python3 skills/agent-evaluation/scripts/resolve-dimensions.py \
  --grounding-present \
  [--qualifying-metrics] [--grounding-forbidden-ops] [--has-retrieval] [--summarizes] \
  [--stateful] [--orchestrator] \
  --out <output_dir>/aeval/.staging/enabled-dimensions.json
```

`--grounding-present` is what distinguishes this operation from generate: it unlocks the
ground-truth dimensions, each still gated by its own `applies_when` (a business-outcome test
appears only if a qualifying metric is present, an operational-constraint test only if one is
declared, and so on). The functional dimensions stay enabled too.

---

## 4. Load the functional suite as the baseline

Copy the published suite into staging to work on — **do not regenerate it:**

- Copy `{output_dir}/aeval/eval.yaml` → `.staging/eval.yaml` and every
  `{output_dir}/aeval/testcases/<id>.yaml` → `.staging/testcases/` (skip the environment
  templates; `publish.py` handles those).
- This is the starting point. The functional cases are correct; grounding makes some of them
  *stronger* and adds what was previously impossible.

---

## 5. Upgrade in place, then add

**Upgrade existing functional cases.** Walk each functional test. Wherever a check asserts that a
value is *grounded and present* and the grounding supplies the **real expected value** for that
field, promote it to the grounded form — assert the exact value, per [groundedness, not invented
values](./writing-checks.md#groundedness-not-invented-values):

```yaml
# before (functional) — groundedness only
- check: 'Every monetary figure in the response is one the tool returned this conversation.'
# after (grounded) — the customer's real expected value
- check: 'The Total Amount in Company Code Currency is approximately 12,922,923.98 — some rounding difference is acceptable.'
```

Keep the functional check as-is wherever the grounding does **not** cover that field, and report it
as still-functional. Upgrading never *removes* a groundedness check; it adds precision where there
is now ground truth.

**Add new grounded cases** for the newly-enabled dimensions:

| Dimension | Add |
|---|---|
| `business_outcome` | One test per qualifying metric, per [design-test-cases](./design-test-cases.md#business-outcome---does-behaviour-advance-the-committed-metrics), now that the target is real. Tag `business_outcome`, id `<NN>_BusinessOutcome_<Metric>`. |
| `operational_constraint` | One per declared forbidden operation: the user asks for it; the test asserts the agent does **not** call the operation (absent from the trace) or refuses. Id `<NN>_Security_<Op>` (`security` tag). Write the pressure as user behaviour, never as the agent's obligation. |
| `summarization` / `rag` | Quality / relevance checks against the grounding reference, where the agent summarises or retrieves. |

A mixed suite — functional cases alongside grounded ones — is the expected outcome. The budget
ceilings still hold (**10 per `eval.yaml` category, 15 test files**); if grounding pushes the suite
over 15, consolidate and prioritise per [the budget](./design-test-cases.md#the-budget), keeping
the grounded business-outcome and operational-constraint cases (they are the point of grounding).

Amend `.staging/eval.yaml` as you go: the business-metric tags that generate deferred are now
written (business outcome is enabled), and any requirement a new grounded case implies is added,
staying within each category's ceiling of 10.

---

## 6. Validate and publish

Follow [validate-and-report](./validate-and-report.md). The batched `validateschema.py --enabled`
pass now **permits** the grounded dimensions (the enabled set from step 3 includes them), and still
rejects anything outside it. The semantic gate measures coverage and parity over the **expanded**
set — every requirement, functional and grounded, covered by a test; every test covering a
requirement. Then publish with `publish.py`, which replaces the live suite with the upgraded one
and deletes any stale generated case not in the staged set.

---

## Report

The summary is the same seven lines as generate, with the `Dims` line now showing the grounded
dimensions as enabled. Add these exceptions when non-empty:

| Report | When |
|---|---|
| **Upgraded** — functional checks promoted to grounded values, by test | Any were |
| **Still functional** — fields the grounding did not cover, left as groundedness checks, by test and field | Any remain |
| **Grounded cases added** — business-outcome / operational-constraint / summarisation / RAG tests created | Any were |
| **Unmapped grounding** — grounding the customer supplied that matched no scenario or field | Any |

Keep each to a line. The grounding the customer gave is high-signal — if some of it mapped to
nothing, that is worth their attention, not a silent drop.
