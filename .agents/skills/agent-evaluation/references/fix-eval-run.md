# Fix a failing eval run

Repairs the failing scenarios across a **whole** eval run. The user triggers this from the
run-level results view with a thin trigger — the run's `executionId` and `solutionId` (no
transcripts). This operation pulls the run's evidence itself, finds **shared causes** across
failures, fixes each once, and verifies nothing that was passing breaks. For a single-scenario
fix, use [fix-failing-scenario](./fix-failing-scenario.md).

The shared mechanics — evidence pull, `/tmp`/`write_file` discipline, the `gradeable`/`traceStatus`
handling, source loading, adjudication, applying the fix, and the pre-finalize checklist — live in
[fix-common](./fix-common.md). This file carries only the run-level specifics: clustering,
per-cluster diagnosis, and the regression guard.

---

## 1. Pull the run's evidence

Pull per [fix-common — Evidence](./fix-common.md#evidence-pull-it-keep-it-on-disk)
(`get_results` → `/tmp/results.json`, `get_traces` → `/tmp/traces.json`; keep on disk, check
`.isError`, obey the `/tmp`-only / `write_file` rules). `/tmp/traces.json` holds the whole run
inline, including `passingScenarios` (the regression guard, used in steps 2 and 5) and
`run.iterations` (report it so pass/fail percentages make sense).

The preflight is optional in general, but **required for a run fix when the run has skipped
scenarios** — step 3 and the Report read `skippedScenarios` from `/tmp/results.json`. Pull it up
front to avoid a mid-flow backtrack.

---

## 2. Load sources

Load the three sources and customer context per
[fix-common — Load sources](./fix-common.md#load-sources), and resolve `output_dir` there. For a
run fix the load has one addition: read **`passingScenarios`** from `/tmp/traces.json` before any
fix and keep it in view throughout — a fix that costs a passing scenario is not valid (step 5).

---

## 3. Cluster failures before diagnosing

Parse the whole run and redirect the facts to a file per
[fix-common — Trace facts](./fix-common.md#trace-facts-parse-once-grep-the-file):

```sh
python3 skills/agent-evaluation/scripts/parse-trace.py /tmp/traces.json > /tmp/fix-facts.txt
```

`grep 'gradeable: NO' /tmp/fix-facts.txt` lists the HARD-GATE candidates (agent bug, never a test
rewrite — see step 5); the `trace_qa` line gives the Trace QA counts. Then build a symptom index
across all `failedScenarios` — for each, extract `scenario.name`, every `failedChecks[].type`, and
the first `failedChecks[].criterion` — and group by shared failure signature:

- the same failed check type
- similar criterion wording
- evidence of the same agent or tool path (the parser's `gradeable` reasons and tool names in
  `/tmp/fix-facts.txt` are a strong clustering signal — a shared failing tool across scenarios is
  one root cause)

Give each cluster a one-line label and **work the largest cluster first**: more scenarios in a
cluster means a single root cause and a single fix are more likely. A shared cause fixed once
beats the same fix repeated per scenario, and an unshared one-off cause is cheaper to spot after
the shared ones are cleared.

Handle `skippedScenarios` (from the `/tmp/results.json` preflight — fetch it now if you skipped
step 1) **separately** — they have no runtime evidence, so keep them out of failure clustering:

- For each skipped scenario, locate the matching testcase YAML and run the structural validator.
- If it validates, compare its structure against a passing scenario from the same primary
  dimension to spot obvious gaps.
- Classify any schema/testcase-shape correction as a **test-side** fix (never the HARD GATE — that
  concerns runtime no-output, which a skipped scenario does not have).

```sh
for testcase in "<output_dir>/aeval/testcases/"*.yaml; do
  python3 skills/agent-evaluation/scripts/validateschema.py "$testcase" \
    || echo "Schema validation failed for $testcase" >&2
done
```

---

## 4. Diagnose each cluster

For each cluster, pull **one representative scenario's turns** out of `/tmp/traces.json` — extract
just the one, do not read the whole file into context. Pass the name with `--arg` so quotes,
backslashes, or newlines in a name cannot malform the filter:

```sh
jq --arg name '<name>' '.failedScenarios[] | select(.scenario.name == $name) | .conversation.turns' \
  /tmp/traces.json
```

Apply the single-scenario diagnosis method —
[fix-failing-scenario](./fix-failing-scenario.md) steps 3 through 5 (read the transcript, localize
each failed check, trace to root cause). If the diagnosis holds across the cluster (same root
cause, same agent path), it covers the whole cluster; if one scenario has a different root cause,
split it out and diagnose it separately.

The HARD GATE applies per-scenario: if `/tmp/fix-facts.txt` reported `gradeable: NO` for any
scenario in the cluster (tool failure, a tool call with no result, or no final agent output), that
cluster is **always** an agent bug (missing failure handling) regardless of the criteria.

---

## 5. Adjudicate, apply, and verify against `passingScenarios`

Adjudicate each cluster per
[fix-common — Adjudication](./fix-common.md#adjudication-agent-bug-or-test-bug) and apply per
[fix-common — Apply the fix](./fix-common.md#apply-the-fix) (agent-fix constraints, or the
test-fix path with the **stage-the-full-suite + HARD STOP** discipline; validate each edited test
file). Apply the fix **once** for the shared cause — do not repeat the same change per scenario;
if two clusters share a fix, verify it does not over-reach.

Then — before the pre-finalize gate — **verify against `passingScenarios`**: map the changed logic
against the passing list, state which passing scenarios touch the same agent path, and confirm
their criteria still hold. If a fix would regress a passing scenario, revise the fix, not the
passing scenario. Finish with the self-check in
[fix-common — Before finalizing](./fix-common.md#before-finalizing).

---

## Report

```
Run        <executionId> — <status> — <iterations> iteration(s)
Scores     success_rate <N> | output_correctness <N> | rule_compliance <N> | tool_call_correctness <N>
Clusters   <N> failure cluster(s) identified
Trace QA   <N> available | <N> pending | <N> unavailable | <N> truncated
Skipped    <N> scenario(s) — schema fixes applied where needed

  Cluster <label>
  Scenarios  <list of scenario names in this cluster>
  Diagnosis  <agent bug | test bug | both> — <root cause in one sentence>
  Fix        <file(s) changed and what changed>
  Evidence   <transcript turns / criterion / source location>

  [repeat per cluster]

Regression <N> passing scenarios checked — none affected | <name(s) that needed attention>
```

Tell the user to deploy the agent first, then re-run the eval to confirm. Both are outside this
operation's scope.

