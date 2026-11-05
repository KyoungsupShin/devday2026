# Generate eval scenarios

The main flow. Generates two artifacts from the source document, and writes a third that is
pure runtime configuration:

| File | Holds | Derived from |
|---|---|---|
| `aeval/eval.yaml` | The eval requirements — what the agent must do. | the source document |
| `aeval/testcases/<id>.yaml` | One dynamic conversation per scenario. This folder is the dataset. | the source document |
| `aeval/config.yaml` | Run parameters — lookback window, sampling rate, schedule. | **nothing** — user input or defaults |

One pass over the source produces both generated files.

**`eval.yaml` and the test cases are both generated directly from the source document.**
Neither derives from the other — see [One flow, two generated
artifacts](../SKILL.md#the-invariants). The eval requirements say what must be true; the
test cases say what situation to put the agent in. Write the tests from the source, not from
the eval requirements: the identifiers, the personas, and the edge case mentioned once in
prose do not survive abstraction into an eval requirement.

They are then cross-checked in two directions. **Against each other** — every eval
requirement covered by a test, every test covering an eval requirement. **Against the
source** — every requirement, acceptance criterion, milestone condition, and qualifying
metric in the document producing an eval requirement and being exercised by a test. Step 7
measures both and reports them as numbers rather than claims.

Both files are bounded and **registry-gated**: `eval.yaml` holds **up to 10 eval requirements
per category** (no fixed floor) and the suite holds **at most 15 test cases**, covering only the
dimensions [step 2b](#2b-resolve-which-dimensions-this-run-may-generate) enables for this run.
The eval requirement bound is per category, never a total — see [the
invariants](../SKILL.md#the-invariants).

`config.yaml` is excluded from all of that. It is runtime configuration, holds no eval
requirements, and appears in no coverage figure.

For an agent extension with an existing base evaluation, this is the wrong operation — see
[extend-eval-scenarios](./extend-eval-scenarios.md).

---

## Where generation happens: staging and resume

Generation does **not** hold the whole suite in memory and write it at the end. It writes as it
goes, into a scorer-invisible staging directory, and publishes only once the complete suite has
passed validation.

**Everything is written under `{output_dir}/aeval/.staging/` first:**

```
{output_dir}/aeval/
  .staging/                 scorer-invisible; the only place this run writes until publish
    progress.json           the one manifest — PRD hash, phase marker, source→req mapping,
                            the test-case plan, and the ids written so far
    eval.yaml               the frozen eval requirements, final shape
    testcases/<id>.yaml     each test case, written one at a time, batch-validated before publish
  eval.yaml                 ← published here at the end, never before
  testcases/<id>.yaml
  config.yaml
```

The downstream scorer reads only `aeval/testcases/*`; `.staging/` is a sibling of `testcases/`,
so a half-written suite is never visible to it. The live `aeval/` is untouched until the
publish step.

**On every invocation, check for `{output_dir}/aeval/.staging/` first.**

- **It exists, and `progress.json`'s stored PRD (and `mcp-mock.json`) hash matches the current
  inputs** → a previous run was interrupted. **Resume:** reload the frozen requirements from
  `.staging/eval.yaml` and the mapping and plan from `progress.json`; **do not re-derive** —
  re-reading the source produces a second, drifted set that turns covered requirements into
  orphans. Generate only the test cases in the plan not yet in `.staging/testcases/`, then
  continue to validation and publish. Say "resumed from staging" in the report.
  - If `progress.json` exists and has a matching hash but **no plan recorded** (interrupted
    before planning completed), re-plan from the staged `eval.yaml` and generate all cases.
- **It exists, but the hash does not match** → the source changed since staging. The staged work
  is stale; delete `.staging/` and start fresh. Say so in the report.
- **It exists, but `progress.json` is missing or has no hash field** → staging is corrupt or
  incomplete from a very early interruption; treat it as stale, delete `.staging/`, and start
  fresh. Say so in the report.
- **It does not exist** → start fresh: create it and write `progress.json` as step 1 proceeds.

To abandon a staged run and start fresh regardless of the hash, delete
`{output_dir}/aeval/.staging/` and re-invoke.

The practical case is a run that exhausted its output budget and is immediately re-run against
the same PRD — the hash matches and it resumes. The hash check is a cheap safety net, not the
common path.

---

## 1. Collect inputs

| Input | Required | Notes |
|---|---|---|
| Source document path | yes | The PRD or equivalent requirements document. |
| `mcp-mock.json` path | no | Located automatically per [tool-catalog](./tool-catalog.md). Used as is when found. |
| Number of test cases | never asked | **At most 15 in total**, covering every enabled dimension — see [the budget](./design-test-cases.md#the-budget). |
| Number of eval requirements | never asked | **Up to 10 per category, no fixed floor** — counted per category, not as a total. See [the budget](./derive-eval-requirements.md#the-budget). |
| Lookback duration, sampling rate, cron schedule | never asked | Runtime knobs, not derived from the source. Defaults applied in step 6. |

**Ask for nothing.** The test case count and the runtime parameters have defaults and are
applied silently — a question about either buys nothing and stalls the run. Ask only when
the request itself is ambiguous, or when nothing determines `output_dir`.

Then resolve `output_dir` per [paths](../SKILL.md#paths) — the agent's asset folder,
`<solution-root>/assets/<asset-name>/`. **Not the PRD's parent directory**, which is the
solution root and puts `aeval/` where the downstream scorer cannot see it.

Once `output_dir` is resolved, run the resume check in [staging and
resume](#where-generation-happens-staging-and-resume): resume from an existing `.staging/` if
its hash matches, discard it if it does not, or create `{output_dir}/aeval/.staging/` and
`{output_dir}/aeval/.staging/testcases/` for a fresh run. Record the PRD (and `mcp-mock.json`)
hash in `.staging/progress.json` as you start.

### Read these files and no others

The source document, `mcp-mock.json`, and nothing else. **Do not read the agent's
implementation** — not its source modules, prompts, tests, notebooks, dependency manifests,
or deployment configuration. `mcp-mock.json` already carries every tool's description,
schema, and deterministic response, which is the whole of what a test needs to know about
the agent's capabilities. Reading further burns context and produces tests asserting what
the code happens to do rather than what the source document requires — step 7 deletes those.

The one exception is a run where no `mcp-mock.json` exists at all, which triggers the
fallback in [tool-catalog](./tool-catalog.md#fallback-no-mcp-mockjson). Even then, the scan
is narrow: `@tool`-decorated functions only.

---

## 2. Establish the agent architecture

It decides which categories apply and whether tool validations are meaningful at all.
Determine it from the source and the tool catalog, and **state which you concluded in the
report** — an orchestrator tested as an agent with tools produces `tool_validations` that
can never pass; an agent with tools tested as an orchestrator produces a suite with no tool
assertions at all, which passes trivially.

| Architecture | What to test |
|---|---|
| **Agent with tools** — calls tools directly | The full matrix: tool parameter and output correctness, safety, error handling, response information correctness. |
| **Sub-agent** — receives routed intent, calls tools | Same as agent with tools. |
| **Orchestrator (routing only)** — no direct tool access | Routing correctness only, inferred from response content. No `tool_validations`. |
| **Orchestrator with tools** | Both of the above. |

**Routing-only orchestrators.** Aeval cannot validate a routing decision directly, so every
response check must be specific enough that only the correct sub-agent's output could
satisfy it — a check any sub-agent's reply would pass asserts nothing about routing.
Enumerate the **routing paths**: every sub-agent reachable and the trigger that activates
it. They are the orchestration equivalent of user journeys, and each needs a correctness
test.

**Tool span instrumentation.** `tool_validations` are judged from OTel traces and need spans
carrying `gen_ai.operation.name = execute_tool`, `gen_ai.tool.name`,
`gen_ai.tool.call.arguments`, and `gen_ai.tool.call.result`. LangChain `create_agent`,
LangGraph `create_react_agent`, and PydanticAI `create_agent` emit these automatically;
anything else needs verifying. If unconfirmed, say so in the report — the validations are
still written, but may report as skipped on the first run.

---

## 2b. Resolve which dimensions this run may generate

Which dimensions a run may produce is **not a fixed list** — it is resolved from the registry
([`dimensions.json`](../dimensions.json)) against what this agent is. Do not decide it by hand; resolve
it deterministically, so a platform-owned or ground-truth dimension can never slip in.

From step 2 and the metric gate you already know the agent's shape. Run the resolver, passing only the
flags that hold, and write the result into staging:

```
python3 skills/agent-evaluation/scripts/resolve-dimensions.py \
  [--stateful] [--summarizes] [--has-retrieval] [--orchestrator] \
  --out <output_dir>/aeval/.staging/enabled-dimensions.json
```

- `--stateful` — step 2's statefulness check found the agent carries conversation state across turns.
- `--orchestrator` — the agent is a routing orchestrator.
- `--summarizes` / `--has-retrieval` — the agent summarises, or retrieves documents (RAG).
- **Never pass `--grounding-present` in this operation.** Base generation has no customer-seeded
  ground truth, so the ground-truth dimensions — business outcome, summarisation quality, RAG
  relevance, operational constraints — stay off here. They are produced only by the grounding
  operation, which supplies and access-verifies the grounding.

The resolver's `enabled` set is **the whole of what this run may generate.** Every test case you design
must belong to an enabled dimension (step 5). The platform-owned dimensions — safety, stability,
performance, UI — are never enabled at all: they are covered a layer down (Joule scenario
matching, the run harness), not by generated agent-eval cases. Operational constraints are off here
for a different reason — they are a ground-truth dimension, gated on a customer-declared forbidden
operation, so they belong to the grounding operation rather than to this one. Step 7 hands this
file to the structural validator, which rejects any case whose dimension is outside the set — the
deterministic backstop to this instruction.

---

## 3. Read the source and define the user journeys

From the source document extract requirements, milestones, and business metrics — the detail
is in [derive-eval-requirements](./derive-eval-requirements.md) step 1, which runs next.

Then define the **user journeys** per
[design-test-cases](./design-test-cases.md#define-the-user-journeys). They are the coverage
unit, and step 5 generates one goal-completion test per journey.

---

## 4. Resolve the tools and derive the eval requirements

**Tools.** Follow [tool-catalog](./tool-catalog.md). It reads `mcp-mock.json` **through
`extract-tool-catalog.py`** (never raw — the script strips `mock_response` to field-name-only type
skeletons so invented values never enter context), collects each
tool's name, description, `input_schema` and `mock_response` field names, and maps the dependencies that
govern `expected_tool_calls` ordering. Nothing is written. **Take the file as it stands** —
no cross-checking it against the agent's code, and no reading the implementation of a tool
to understand it better.

**Eval requirements.** Follow [derive-eval-requirements](./derive-eval-requirements.md). It
sorts every testable rule into the three categories, applies the metric target gate and the
`[BUSINESS_METRIC: …]` tagging, fills each category to [the
budget](./derive-eval-requirements.md#the-budget) of 5, and applies the trust boundary.
Write the derived requirements, in final shape per [schemas](./schemas.md#shape), to
`.staging/eval.yaml`, and record the **source-to-requirements mapping** in
`.staging/progress.json`. This is the frozen set — step 5 amends it in place as scenarios
surface what the source implied. Mark the requirements phase done in `progress.json`.

**On resume, reload `.staging/eval.yaml` and do not re-derive.** The staged requirements are
what the already-written test cases were measured against; a second reading of the source
drifts and turns covered requirements into orphans.

**If a previous run already published a complete evaluation, read the live `aeval/eval.yaml`
and do not re-derive.** The test cases beside it were written and measured against those eval
requirements; replacing them with a second, slightly different reading of the source turns eval
requirements the tests satisfy into eval requirements nothing covers. Re-derive only when the
user asks or the source has changed, and say which you did.

**Complete means `eval.yaml` with a populated `testcases/` folder beside it.** An `eval.yaml`
standing alone in the live `aeval/` is debris from an old run: it was never parity checked and
nothing covers it. Re-derive from the source, overwrite it, and say so — treating it as
authoritative carries an unvalidated file into every later run.

**Nothing is published at this step.** Step 5 adds an eval requirement whenever a test covers
something no eval requirement states, and step 7 adds any still missing at the parity check.
What this step establishes is the eval requirements the source states outright; the scenarios
surface the rest. Landing each category near 5 rather than at 10 leaves room for that — a
category already at its ceiling can only take a new entry by re-consolidating.

The **source-to-requirements mapping** recorded in `progress.json` is what step 7 measures
coverage against, and it is the only thing that can show a source requirement neither artifact
ever picked up.

---

---

## 5. Plan and write the test cases

Follow [design-test-cases](./design-test-cases.md#design-the-test-cases). It covers the
three test groups, [the budget](./design-test-cases.md#the-budget) and how to spend it, the
rules that apply to every test case, and the parity bookkeeping to maintain while designing.

**Plan first, then write one at a time.** Design the whole suite as a compact *plan* — a list
of test-case stubs, each with its `id`, the journey it maps to, and the eval requirements it
will cover — and record the plan in `.staging/progress.json`. The plan is small; holding it
costs little. Then write the cases **one file at a time** into `.staging/testcases/<id>.yaml`,
appending each id to `progress.json` as it is written. Do not hold the full set of written-out
test cases in memory — that is what exhausts the output budget mid-suite. On resume, skip any
id already present in `.staging/testcases/`.

**Validate the whole staged batch in one validation phase, after the cases are written.** Do not run the
validator once per file — run it over every staged case in one validation phase, passing the enabled
set from step 2b so the dimension gate is enforced:

```
for f in <output_dir>/aeval/.staging/testcases/*.yaml; do
  python3 skills/agent-evaluation/scripts/validateschema.py "$f" \
    --enabled <output_dir>/aeval/.staging/enabled-dimensions.json
done
```

Each case prints nothing on success and its exact problem (path, expected, found) on failure. A case
whose dimension is **not** in the enabled set is rejected here (`dimension "…" is disabled for this
run`) — that should not happen if you designed only enabled dimensions, and if it does, the fix is to
drop the case, not to widen the enabled set. Fix every flagged file from the reported notes, then
re-run the validation phase until it is clean. The validator is the deterministic structural **and
enabled-dimension** gate; one validation phase catches the same errors as per-file checks in a fraction
of the round-trips.

When a scenario surfaces something no eval requirement states, amend `.staging/eval.yaml` in
place (and the mapping in `progress.json`), exactly as before.

---

## 6. Write `config.yaml`

`config.yaml` is a static template — `publish.py` copies it from the skill's `templates/`
directory at publish time. There is nothing to write here.

---

## 7. Validate, publish, and report

Follow [validate-and-report](./validate-and-report.md). It runs the **semantic** validation
checklist over the complete staged set in `.staging/`, measures coverage, enforces parity,
then **publishes** the validated suite by running
`python3 skills/agent-evaluation/scripts/publish.py <output_dir>` — one deterministic command
that moves the staged files into `aeval/`, copies the static environment-management templates,
deletes stale generated cases, and removes `.staging/`.

Structure is already guaranteed: every staged test case passed the batched `validateschema.py`
pass in step 5. This step adds the checks a schema cannot express — coverage, parity, and
assertion placement — some of which change staged files before they are published (parity
orphans add eval requirements to `.staging/eval.yaml`; misplaced assertions move between
validation blocks). Make those amendments in `.staging/`, not in the live `aeval/`.

The environment-management templates (`000_pre_setup.yaml`, `zzz_post_teardown.yaml`) are
handled entirely by `publish.py`, which copies them from the skill's
[`templates/`](../templates/) directory — never generated, never overwritten. There is no
separate step to write them.
