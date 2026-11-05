# Validate and report

Run this **after** the staged test cases are written to `aeval/.staging/` and **before** they
are published to `aeval/`. Invoked near the end of
[generate-eval-scenarios](./generate-eval-scenarios.md) and
[extend-eval-scenarios](./extend-eval-scenarios.md).

Caution: Publishing operates on the staged set. Ensure `aeval/.staging/testcases/` contains every
test case you intend to keep; any non-staged test case in `aeval/testcases/` will be deleted by
publish.

Test cases are written one at a time into `.staging/testcases/` as they are designed, then
validated for **structure** by [`validateschema.py`](../scripts/validateschema.py) in one
validation phase over the assembled batch. This step is the **semantic** gate over the complete staged set — coverage,
parity, assertion placement, and meaning, the things a schema cannot express — after which the
validated suite is published.

---

## 1. Validate

Check **every staged test case in `aeval/.staging/testcases/`**, not only the ones written on
this run, and fix problems in place. On an extension the staged set includes tests carried
forward from earlier runs; they are bound by the same rules.

**Skip the environment-management templates entirely:**
`000_pre_setup.yaml` and `zzz_post_teardown.yaml` are static files copied at publish, never
staged and never generated. None of the checks below apply to them.

1. **Structural conformance — mechanical, already done.** The whole staged set passed a
   [`validateschema.py`](../scripts/validateschema.py) validation phase in step 5. That script owns all
   of structure: the top-level key set and unknown-key rejection, exactly one explicit
   `dynamic_conversation` step, `user_agent.task_summary` and `max_turns` 1–15,
   `expected_tool_calls` (not `expected_tools`) with exactly one of `value`/`check` per
   `parameters.<name>` and `output`, the `id`/tag `^[a-zA-Z0-9_]+$` pattern, id-equals-filename-stem,
   at least one `agent_response_validations` entry, and the
   no-`forbidden_tool_calls` rule. **Do not re-verify these by eye** — a staged file is already
   structurally valid. That same step-5 pass runs the **enabled-dimension gate**
   (`--enabled .staging/enabled-dimensions.json`): any case whose id Category token maps to a
   dimension outside the enabled set is rejected there, so a disabled dimension (safety, security,
   and business outcome out-of-the-box) cannot reach publish. If this validation phase edits any
   staged case, re-run the phase once more before publishing. The checks below are the ones a
   schema cannot express — meaning, not shape.
2. **Step shape** — mechanical, enforced by the script (check 1): exactly one explicit
   `dynamic_conversation` step with `task_summary` and `max_turns` 1–15. Not re-checked by eye.
3. **Required blocks** — mechanical, enforced by the script (check 1): at least one
   `agent_response_validations` entry, no present-but-empty validation list. Not re-checked by eye.
4. **Assertion placement** — no check in `agent_response_validations` or
   `rule_compliance_validations` asserts that a tool was called, in what order, or with what
   arguments. Those belong in `tool_validations`. This is the most common error and it fails
   silently.
5. **Information correctness** — no check passes against a response carrying the wrong
   customer, wrong amount, or wrong fields. Run the anti-pattern table in
   [writing-checks](./writing-checks.md#validation-anti-patterns).
6. **Values, not placeholders** — every asserted value traces to a `mock_response` or to the
   source document. A value that parses but was never grounded is not a shape error and is not
   caught by the structural validator — check it here. This applies to test cases; a placeholder
   in an `eval.yaml` `tool_requirements` entry marks a value that varies per session and is
   correct there — see [Writing
   `tool_requirements`](./derive-eval-requirements.md#which-values-are-literal-and-which-are-placeholders).
7. **Identifiers** — the `^[a-zA-Z0-9_]+$` pattern, the id-equals-filename-stem rule, and the
   presence of at least one dimension tag are mechanical (check 1). What remains here is what a
   single-file check cannot see: every `id` follows the `<NN>_<Category>_<ShortDescription>`
   form and is **unique across the suite**.
8. **Tool ordering** — dependencies are respected and required parameters are present. No
   `tool_validations` block names a tool the agent is merely permitted to use.
9. **Tool requirements name real tools** — every entry in `eval.yaml`'s `tool_requirements`
   names at least one tool, spelled exactly as the catalog spells it, and every parameter it
   names is one that tool accepts. An entry describing a capability rather than a tool is
   rewritten per [Writing
   `tool_requirements`](./derive-eval-requirements.md#writing-tool_requirements); an entry
   naming a tool the catalog does not hold is a generation error that fails on every run
   looking like an agent bug. Check against whichever catalog the operation used — for an
   extension, the name must be one `extension.yaml` grants, not merely one a translation file
   describes, and not the translation file's `title`.
10. **`TRAP:` discipline** — every adversarial test has a `TRAP:` line written as user
   behaviour, no `TRAP:` line states an agent obligation, and no business-outcome test has
   one at all.
11. **Observable behaviour** — every check is judgeable from the transcript and tool-call
    trace alone. Anything with no observable form is recorded as unassertable and raised
    with the user, never papered over with a proxy — see
    [writing-checks](./writing-checks.md#when-nothing-about-it-is-observable).
12. **Journeys, milestones and metrics** — every user journey has a happy path and at least
    one failure path; every milestone is covered or accounted for as unassertable; every
    qualifying business metric has a business-outcome test.
13. **Source coverage** — walk the source document's requirements, acceptance criteria,
    milestone conditions, and qualifying metrics one at a time, and confirm each one produced
    at least one eval requirement **and** is exercised by at least one test. See [source
    coverage](#source-coverage-is-walked-from-the-source). Anything with neither is an
    omission to fix, or is recorded as unassertable with a reason.
14. **Budget** — **count `eval.yaml` per category, not as a total**: each category is capped at
    10, with **no fixed floor**. `aeval/testcases/` holds **at most 15 files**, exercising every
    enabled dimension that applies and **no file for a disabled dimension**. Count all scenario
    files except the environment-management templates (`000_pre_setup.yaml` and
    `zzz_post_teardown.yaml`). Outside a ceiling, resolve it per [the budgets are
    bounded](#the-budgets-are-bounded), then re-run checks 12 and 13 — a merge that quietly
    drops a behaviour is the one way consolidation breaks coverage.
15. **Parity** — no orphan on either side. Every eval requirement in `eval.yaml` is covered
    by at least one test, and every test covers at least one eval requirement. Walk both
    directions separately; see [the parity rule](#the-parity-rule). Fix every orphan before
    publishing.
16. **Redundancy** — no two tests assert substantially the same behaviour in substantially
    the same situation. Inside a fixed budget a duplicate is not merely waste, it is a
    coverage slot spent on nothing. Fold the distinctive checks of one into the other and
    drop it. For a test **already on disk** from an earlier run, flag it and say which to
    keep rather than deleting it.
17. **Run parameters** — `lookback_duration` is a single segment, unit `h`/`m`/`s`, at most
    24 hours, not compound. `sampling_rate` is between 0.0 and 1.0. `cron_schedule` has five
    whitespace-separated fields and is quoted.
18. **Trust boundary** — run [before writing any
    file](./writing-checks.md#before-writing-any-file).

Report what was fixed.

### Measure coverage and enforce parity

Coverage is a number, not an impression. Because the eval requirements and the test cases
are two independent readings of the source rather than a chain, there are **three
derivations to measure, one parity rule to enforce, and two budgets to stay inside.**

| | Measure | Required |
|---|---|---|
| **Derivation** — source → eval requirements | source requirements that produced at least one eval requirement in `eval.yaml` | all of them |
| **Derivation** — source → tests | source requirements exercised by at least one test | all of them |
| **Derivation** — source → journeys | user journeys with at least one happy-path test and one failure path, and milestones covered | all of them |
| **Parity** — eval requirements ↔ tests | every eval requirement covered by at least one test, **and** every test covering at least one eval requirement | **no orphans in either direction** |
| **Budget** — `eval.yaml` | entries **in each category, separately** | **≤ 10 each (no floor)** |
| **Budget** — `testcases/` | enabled dimensions exercised, and files in total | **every enabled dimension that applies covered, ≤ 15 total** |

#### Source coverage is walked from the source

The two source rows are measured differently from everything else in the table, and the
difference is the whole point of them. **Walk the source document, not the generated files.**

Take the PRD's requirements, acceptance criteria, milestone conditions, and qualifying
metrics in the order they appear, and for each one name the eval requirement covering it and
the test exercising it. Walking `eval.yaml` instead only proves that what was written came
from somewhere — it is structurally incapable of revealing what was never written, which is
the only failure these rows exist to catch.

A source requirement with neither is not a shortfall to note. It is one of three things:

| | Fix |
|---|---|
| **An omission** | Add the eval requirement, and cover it with a check in the test whose scenario already provokes it. |
| **Unassertable** — nothing about it is observable | Keep it out of both files, report it with the one-line reason. It is not an orphan, because it is in neither. |
| **Out of scope** — background, rationale, or a non-functional aside | Report it as out of scope. It was never a testable rule. |

Silence is not on that list. An uncovered requirement produces no failing test — it produces
no test at all, and the suite passes.

#### The budgets are bounded

**Each `eval.yaml` category is capped at 10, with no fixed floor. The suite holds at most 15
test cases, exercising every enabled dimension that applies.** Never exceed a ceiling, and never
fabricate toward a count — least of all for a disabled dimension.

Coverage and budget only conflict when the artifacts are written at the wrong grain — a
requirement per fixture, a test per requirement. When a count exceeds a ceiling, or an enabled
dimension is uncovered, the fix is regrading, re-mining, consolidation, or adding an in-scope
scenario — never deletion of coverage and never padding:

| Situation | Fix |
|---|---|
| **A light or empty category** | Often correct now — only enabled dimensions are mined. Re-check for a bundled or misfiled entry and add any missing **in-scope** error/empty/fabrication/scope rules, per [where the entries come from](./derive-eval-requirements.md#where-the-entries-come-from). Then report it as light, naming the in-scope rows the source skipped. A category light because its dimensions are disabled is not a finding. **Never invent an entry to fill it.** |
| More than 10 in a category | Merge entries describing the same behaviour at different grains, per [consolidate before exceeding 10](./derive-eval-requirements.md#consolidate-before-exceeding-10-in-a-category). Never merge two behaviours into one "and" string. |
| **The categories are unbalanced** — one at 9, another at 1 | Usually misfiling, not asymmetry in the source. A tool-ordering rule in `agent_response_requirements` inflates one category while starving another. Re-file before concluding anything. |
| More than 15 test cases | Move checks from a thin test into the test whose scenario already creates the same situation, per [a new check is cheap](./design-test-cases.md#a-new-check-is-cheap-a-new-file-is-not), and drop the emptied file. |
| **An enabled dimension or journey uncovered** | Add a scenario — or a check in an existing one — that exercises it. If the 15-file cap forces a choice, say which is left uncovered and why. |
| **A disabled dimension present in the suite** | A generation error the enabled-set gate should have caught. Remove the file; it cannot publish. |

There is no corresponding "fewer than 15 test cases" row. The suite has no floor — anything up
to 15 that covers the enabled dimensions and the journeys is legitimate.

After any consolidation or re-filing, re-walk source coverage and parity. Those are the two
things a merge silently breaks.

If full coverage is still impossible inside the bounds, **hold them and report the
shortfall.** Keep the entries highest in the priority orders in
[derive-eval-requirements](./derive-eval-requirements.md#spend-the-budget-in-this-order) and
[design-test-cases](./design-test-cases.md#spend-the-budget-in-this-order), and name every
source requirement left uncovered with the reason it did not fit. A named gap is a decision
the reader can take; an unnamed one is a suite that looks complete.

#### The parity rule

**Every eval requirement in `eval.yaml` is covered by at least one test case, and every test
case covers at least one eval requirement.** Totality in both directions, **not** a
one-to-one mapping — an eval requirement may have several tests and a test may cover several
eval requirements. What is forbidden is an entry on either side mapping to nothing.

Nothing in the generation order produces parity, so check it deliberately.

#### Resolving an orphan

Fix every orphan before publishing. There is no option to note one and move on.

| Orphan | Fix |
|---|---|
| **An eval requirement with no test** | Add a check covering it to the test whose scenario already provokes it. Write a new test only when no existing scenario puts the agent in that situation. |
| **A test with no eval requirement** | Add the eval requirement it implies to `eval.yaml`, **or** delete the test. |

An eval requirement with no test is a requirement nobody checks — it produces no failing
test, just a smaller suite that passes.

A test with no eval requirement is usually the *good* case: reading the source directly
surfaced a scenario the eval requirements abstraction missed. **Add the eval requirement**;
delete the test only when it asserts something the source never asked for. That is not
cheating the measurement — `eval.yaml` is meant to state everything the agent must do.
Report which eval requirements were added this way.

**When the budget is already full**, neither fix is "skip it". An eval requirement orphan is
fixed with a check, which costs nothing against the test budget. A test orphan in a category
already at 10 is fixed by merging the new entry into the existing one that describes the same
behaviour — and if no entry does, by consolidating two that do, per
[consolidate before exceeding 10](./derive-eval-requirements.md#consolidate-before-exceeding-10-in-a-category).
Check the other two categories first: the entry the test implies often belongs in one of
them, and they are rarely at their ceiling at the same time.

The **one exception** is a requirement with no observable form
([writing-checks](./writing-checks.md#when-nothing-about-it-is-observable)). It stays out of
both files, reported as unassertable, and is not an orphan because it is in neither.

#### Do not estimate

Work from the source-to-requirements mapping and the requirement-to-test mapping you built
while designing, and make three passes, not two:

1. **Walk the source document.** Mark each requirement, acceptance criterion, milestone
   condition, and qualifying metric against the eval requirement covering it and the test
   exercising it. This pass is the only one that can find something neither file contains.
2. **Walk `eval.yaml`.** Mark each entry against the tests covering it; an entry nobody
   marked is uncovered, however thorough the set feels.
3. **Walk `testcases/`.** Confirm each test lands on a marked eval requirement. Exclude the
   environment-management templates.

All three are required. Checking one direction and assuming the others is how orphans
survive, and skipping the first is how a whole section of a PRD goes missing while both
generated files look internally consistent.

Then count both files against the budget. A count is not an impression either — count
`eval.yaml` **per category** (ceiling 10, no floor), count the test files (ceiling 15), and
confirm **each enabled dimension that applies is exercised**. A file at 10 entries in one
category can still leave another category light or an enabled dimension uncovered.

All of them must reach 100%, or every shortfall must be named with a reason. The three
legitimate reasons are that a source requirement has no observable form
([writing-checks](./writing-checks.md#when-nothing-about-it-is-observable)), that it is out
of scope for this agent, or that it fell outside a budget that consolidation could not
recover. Anything else is a gap to close before publishing.

Every one of these gaps is invisible downstream. An uncovered eval requirement produces no
failing test — it produces no test at all, and the suite passes.

---

## 2. Publish and report

The validated suite already exists in `aeval/.staging/` — `eval.yaml` and one file per test case
under `testcases/`. Publishing copies it into place; it does not re-generate
anything.

**Confirm `{output_dir}` is an asset folder before publishing** — it must end in
`assets/<asset-name>/`, and that folder must hold an `asset.yaml`. If it does not, the
resolution in [paths](../SKILL.md#paths) went wrong and the files are about to land where
nothing reads them. Stop and re-resolve rather than publishing.

Then publish with the publish script — **one command, do not do these steps by hand:**

```
python3 skills/agent-evaluation/scripts/publish.py <output_dir>
```

It performs the whole publish deterministically: creates `aeval/` and `aeval/testcases/`,
deletes stale generated `<id>.yaml` not in the staged set (never the templates), **copies**
`eval.yaml` from staging into place (the staging copy remains until `rmtree`), **moves** every
staged test case into `aeval/testcases/`, and **copies** `config.yaml` and the static env
templates from `templates/` with no-clobber — then removes `.staging/`. It exits non-zero and changes nothing fatal if staging is missing or a template
cannot be found. The manual multi-step copy is error-prone — the script exists so the publish
tail (templates, staging cleanup) is never dropped. Run it exactly as shown; resolve its path
the same way as `validateschema.py` if the workspace root differs.

**`publish.py` is the final action of the run.** When it prints `publish complete`, the run is
done — write the report and stop. Do not re-list the directory, re-read files, re-run the
validator, or otherwise verify its work: the script already checked that both templates landed
and exits non-zero if anything is wrong. Trust its exit code; a clean exit means you are
finished.

An interrupted run leaves `.staging/` intact and the live `aeval/` untouched, so a re-run
resumes rather than corrupting a half-published suite — see
[generate-eval-scenarios](./generate-eval-scenarios.md).

`eval.yaml` was staged when the eval requirements were first frozen and amended in place while
the test cases were designed and again at validation, wherever parity required an eval
requirement the source did not state outright. The staged file on disk already matches the eval
requirements the tests were measured against; publishing simply copies it.

Quote string values and escape embedded quotes. Use a block scalar (`|`) for `task_summary`
and any multi-line check. Omit `rule_compliance_validations` and `tool_validations` entirely
when they have nothing to assert, rather than writing them empty.

## The report

**Default to short.** The generated files are the deliverable; the report exists to tell the
reader what to check and what went wrong. A run where everything landed cleanly should
produce a dozen lines, not three pages.

Two parts: a fixed summary that is always written, and exceptions that appear **only when
they are non-empty**.

### Always — the summary

Seven lines. No preamble, no restating what the skill does.

```
Wrote   assets/<asset-name>/aeval/ — eval.yaml, N testcases, config.yaml
Scope   <architecture>; <N> user journeys; tools from <source>
Dims    enabled: <list>   off: <list + one-word reason: platform / needs-grounding>
Reqs    response N | tool N | rule N   (max 10 each, no floor)
Tests   N total (max 15), covering <enabled dimensions exercised>
Cover   source→reqs N/N · source→tests N/N · parity N/N both ways
Config  24h / 0.5 / '0 2 * * *' — defaults, unrelated to the PRD
```

State coverage as counts even at 100%, so the reader knows it was measured rather than
assumed. Anything short of 100% moves to the exceptions below.

### Only when non-empty — the exceptions

Write the heading **only if it has entries.** Never write "None", "N/A", or an empty section:
a reader scanning for problems should find only problems.

| Report | When |
|---|---|
| **Uncovered** — source requirements with no eval requirement or no test, by name and reason | Any coverage figure below 100% |
| **Unassertable** — with the one-line reason it has no observable form | Anything recorded as such |
| **Light categories** — which came in light, and the in-scope obligation types the source never mentioned | A category lighter than its in-scope content warrants |
| **Consolidated** — what was merged and what the merged entry now covers | A merge was made to stay inside a budget |
| **Added for parity** — eval requirements the scenarios surfaced, and the test that prompted each | Any were added |
| **Deleted** — tests dropped as asserting what the source never asked for | Any were |
| **Metrics skipped** — the metric and its actual `target` cell value | The gate skipped any |
| **Deferred to grounding** — ground-truth dimensions/metrics off out-of-the-box (business outcome, summarisation quality, RAG relevance, operational constraints), with the exact next step: *put your real expected data in a file and run "create grounded evaluation scenarios, the grounding is at `<path>`"* | A ground-truth dimension or qualifying metric applies to the agent but is off this run |
| **Tool warnings** — tools with no `mock_response`, catalog tools no requirement obliges, unconfirmed span instrumentation | Any apply |
| **Needs real data** — tests whose asserted values no source confirms, with the value to verify | Any test assumes a back-end condition nothing establishes |
| **Dimension gaps** — **only the open rows** of the table in [schemas](./schemas.md#the-gap-report), never the full matrix | An applicable dimension has no coverage |
| **Moved** — an `aeval/` folder was found at the old solution-root location and left untouched | It was |

Keep each to a line per item. The reasoning behind a finding belongs in the reference files,
not repeated per run.

### Never in the report

- **The requirement-to-test and source-to-test mappings.** They are working analysis and were
  what coverage was measured from — but as output they are dozens of rows restating files the
  reader can open. Offer them; do not print them unasked.
- **Gates that passed.** The checklist in [step 1](#1-validate), the trust boundary, schema,
  id, and tag checks are **preconditions for writing at all** — the files could
  not have been written had they failed. Reporting that they passed tells the reader nothing
  and reads as padding. Report a gate only when it changed something.
- **The full dimension matrix.** Only rows that are applicable and uncovered. A row reading
  "applicable: yes, covered: yes" is not a gap report.
- **User journeys that are covered.** The summary already gives the count. Name a journey
  only where its coverage is short.
- **Per-item narration of what went right.** A requirement that produced a test needs no line.
- **Restating rules.** Why parity matters, what a business metric tag does, how the budget
  works — all of it is in the reference files and none of it changes between runs.
- **The generated content itself.** Do not echo requirements or test cases back; they are on
  disk.

### Keep each exception to a line

An exception names the thing and its reason. It does not argue the case.

```
drift   PRD names get-open-billing-items; deployed tool is
        list_openbillingitems_for_billing. Obligation from PRD, identifier from
        extension.yaml.
```

Not three sentences explaining why writing the PRD's name would have failed — that reasoning
is in the reference files and is the same every run. The exception a reader acts on is the
fact, not the rationale.

Where several items share a reason, group them on one line rather than repeating it per item.
Two lines is the ceiling for any single finding.
