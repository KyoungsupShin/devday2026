# Fix a failing eval scenario

Repairs a **single** failing eval scenario. The user sees the failure in the Joule Studio results
view and triggers this operation with a thin trigger (`executionId`, `solutionId`,
`semanticVersion`). For a whole-run fix, use [fix-eval-run](./fix-eval-run.md) instead.

The shared mechanics — evidence pull, `/tmp`/`write_file` discipline, the `gradeable`/`traceStatus`
handling, source loading, adjudication, applying the fix, and the pre-finalize checklist — live in
[fix-common](./fix-common.md). This file carries only the single-scenario specifics: slicing one
scenario out of the run bundle, and the four diagnostic questions.

---

## 1. Pull and slice the evidence

Pull the run's evidence per [fix-common — Evidence](./fix-common.md#evidence-pull-it-keep-it-on-disk)
(`get_results` → `/tmp/results.json`, `get_traces` → `/tmp/traces.json`; keep on disk, check
`.isError`, obey the `/tmp`-only / `write_file` rules).

Then slice **just this scenario** by `conversationId` (preferred over name; from `results.json` or
the UI `promptContext`). `get_results` uses `conversation_id` while `get_traces` uses
`conversationId` — coalesce in `jq`:

```sh
jq -e --arg id '<conversationId>' '
  first(.failedScenarios[] | select((.conversationId // .conversation_id) == $id))
' /tmp/traces.json > /tmp/scenario.json \
  || { echo "No failed scenario matches conversationId=<conversationId>" >&2; exit 1; }
```

`first(...)` guarantees a single object (so `/tmp/scenario.json` is a valid document even if the
id somehow matched more than one entry), and `jq -e` exits non-zero when nothing matched — so a
bad id fails here, at the slice, rather than downstream in `parse-trace.py` or diagnosis.

The slice is one scenario trace: `conversationId`, `traceStatus`, `traceIds`, `spanCount`,
`truncated`, `scenario { name, description, failedChecks: [{ type, criterion }], scores }`,
`conversation.turns` (`[]` unless `traceStatus === 'AVAILABLE'`), and `promptContext`. See
[fix-common — What the turns contain](./fix-common.md#what-the-turns-contain) for the turn shape.

---

## 2. Load sources

Load the three sources (evidence → eval source → agent source) and the optional customer context
per [fix-common — Load sources](./fix-common.md#load-sources). Resolve `output_dir` there too.

---

## 3. Read the transcript

Parse the sliced scenario and redirect the facts to a file per
[fix-common — Trace facts](./fix-common.md#trace-facts-parse-once-grep-the-file):

```sh
python3 skills/agent-evaluation/scripts/parse-trace.py - < /tmp/scenario.json > /tmp/fix-facts.txt
```

Act on the `gradeable` verdict as described there — `gradeable: NO` → apply the HARD GATE in
[fix-common — Adjudication](./fix-common.md#adjudication-agent-bug-or-test-bug) immediately;
`gradeable: n/a` → follow `traceStatus` handling, diagnosis ungrounded; `gradeable: YES` →
continue below.

`conversation.turns` is chronological. Work through it in order and answer four questions before
step 4:

**1. Did the agent retrieve the right data?**
Pair each `tool_call` turn with its following `tool_result` turn. For each pair: what did the
call's `toolArguments` request, and what did the result's `toolResult` return? Was the returned
data correct, complete, and sufficient for the task summary in the scenario's testcase YAML? A
`tool_call` with no `tool_result` is an unterminated call — treat it as a retrieval failure (a
likely hang), not as missing data.

**2. Did the agent have what it needed when it made its decision?**
A decision made with incomplete or missing data is a retrieval failure — even if the decision
logic is also wrong. Name both, separately. Do not merge them into a single cause.

**3. What did the agent produce as its final output?**
Find the last `assistant` turn with non-empty `content`. Read it in full. Map it against each
`failedCheck.criterion` directly — against the literal text, not a summary. If there is no such
turn, the agent produced no answer — a `gradeable: NO` case.

**4. Were there errors or unexpected finish reasons mid-conversation?**
Check `status` and `error` on every `tool_result` turn (`status: failure` carries the reason in
`error`), and `finishReason` on the final turn. A tool failure, an unterminated call, an early
stop, or a timeout changes where the failure sits.

If `truncated` is `true`, note it: the transcript may not cover the full conversation.

---

## 4. Localize each failed check

For each entry in `failedChecks`:

1. State the `criterion` (the rule that failed) and its `type`.
2. Identify the transcript turn(s) most relevant to it — the tool call that should have fetched
   the required value, the assistant message that should have stated it, the decision point where
   the agent chose the wrong path.
3. State precisely what the agent produced there and how it diverges from the criterion.
4. Classify where the failure occurred:

| Failure point | What it means |
|---|---|
| **Retrieval** | Wrong tool, wrong arguments, or incomplete/incorrect data returned |
| **Decision** | Correct data, wrong conclusion |
| **Expression** | Correct conclusion, stated in a way that violated the criterion — wrong vocabulary, format, or level of detail |
| **Coverage** | The agent never addressed the requirement at all |

One failed check can fail at more than one point. Name all of them.

---

## 5. Trace to root cause

Each failure localized in step 4 has a cause in the agent source or the test definition:

**Retrieval failure:** look at tool wiring in the entry point and the tool definitions. Did the
correct tool exist and was it called with correct arguments? If the same tool succeeds elsewhere
with different arguments, the agent is constructing a malformed call — fix the call construction,
not the tool or the test. Does `mcp-mock.json` contain the value the criterion expects — if not,
the test may be asserting a value the data cannot produce.

**Decision or expression failure:** look at the system prompt and `SKILL.md`. What decision rule
was the agent given? Does it correctly map the available data to the required output? Then look
for any deterministic logic module that handles this decision — and ask: **is it in the runtime
call path?** A module imported but whose core function is never called at runtime is a wiring bug.

**Coverage failure:** look at what the system prompt says about this requirement. Does it instruct
the agent to address it at all? Is it in scope for this agent?

**Root cause taxonomy:**

| Type | Pattern |
|---|---|
| **Prompt / SKILL.md bug** | The agent is told to check a field/state/condition that does not exist in the data, or given a decision rule that produces the wrong output for valid inputs |
| **Wiring bug** | Correct logic exists in a module but is not in the runtime call path |
| **Logic bug** | The agent's code or prompt computes the wrong result given inputs it correctly receives |
| **Test bug** | The criterion contradicts the PRD, asserts a value the data cannot produce, or makes an impossible demand of a correctly-behaving agent |

A single scenario can have causes of more than one type. Name all before adjudicating.

---

## 6. Adjudicate and apply the fix

Adjudicate per [fix-common — Adjudication](./fix-common.md#adjudication-agent-bug-or-test-bug)
(default fix the agent; HARD GATE for no-output; the narrow test-bug conditions; preserve passing
scenarios; no symptom fixes). Apply per
[fix-common — Apply the fix](./fix-common.md#apply-the-fix) — agent-fix constraints, or the
test-fix path with the **stage-the-full-suite + HARD STOP** discipline. Then run the pre-finalize
self-check in [fix-common — Before finalizing](./fix-common.md#before-finalizing).

---

## Report

After applying the fix, write exactly this — no more, no less:

```
Scenario   <id> — <description from the test case>
Diagnosis  <agent bug | test bug | both> — <root cause in one sentence>
Fix        <file(s) changed and what changed>
Evidence   <which transcript turns / which criterion / which source location grounded this>
Trace      <traceStatus value> — <if PENDING or UNAVAILABLE: state that conclusions are ungrounded>
```

If the fix is to the test: append the six summary lines from
[validate-and-report](./validate-and-report.md).

After an agent-side fix: tell the user to deploy the agent first, then re-run the eval to confirm
the scenario now passes. Both are outside this operation's scope.

