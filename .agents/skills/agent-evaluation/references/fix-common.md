# Fix operations — shared mechanics

Shared by [fix-failing-scenario](./fix-failing-scenario.md) (one scenario) and
[fix-eval-run](./fix-eval-run.md) (a whole run). Both are triggered from the Joule Studio results
view with a **thin trigger** (`executionId`, `solutionId`, and for the scenario op
`semanticVersion`); neither receives transcripts. Each pulls its own evidence via the sanctioned
MCP tools, diagnoses against the agent and eval sources, and applies a correct, scoped fix. This
file is the single source of truth for everything the two operations do the same way; the
operation files hold only what differs.

---

## Evidence: pull it, keep it on disk

The backend exposes two read tools on `ibd-mcp-server`: `get_results` (run header, per-scenario
`conversation_id`, `skippedScenarios`, `promptContext`) and `get_traces` (the whole run inline).
Pull through these tools only — **do not** call the backend `getRunTraces`/`getScenarioTrace`
APIs directly; the sandbox guardrail blocks raw internal-API calls and these tools are the
sanctioned path.

Scratch and evidence go to **`/tmp` only — never under `aeval/` or `.evidence/`**. The container
reverse-syncs the project tree back into the agent's code (debounced, no flush), so a scratch
file written there would leak into the agent and can race the backend's own `.evidence/` cache.
`/tmp` is outside that sync and outside context. The **only** writes into the project tree are
the actual fixes, applied through the durable `write_file` tool (see *Durability* below).

**1) Optional preflight** — header, `conversation_id` mapping, `promptContext`, skipped list:

```sh
jl mcp call ibd-mcp-server get_results \
  solutionId="$JOULE_STUDIO_SOLUTION_ID" executionId="<executionId>" > /tmp/results.json
if jq -e '.isError == true' /tmp/results.json > /dev/null; then
  echo "get_results failed:" >&2; cat /tmp/results.json >&2; exit 1
fi
```

**2) Whole-run traces** — pull fresh at the start of the operation so you always hold *this*
run's evidence (unconditional, not `test -f`-guarded — `get_traces` is idempotent and
server-cached, so a re-pull is cheap and returns the identical payload):

```sh
jl mcp call ibd-mcp-server get_traces \
  solutionId="$JOULE_STUDIO_SOLUTION_ID" executionId="<executionId>" > /tmp/traces.json
if jq -e '.isError == true' /tmp/traces.json > /dev/null; then
  echo "get_traces failed:" >&2; cat /tmp/traces.json >&2; exit 1
fi
```

**`jl` exits 0 even when the tool failed** — never trust the exit code; inspect the JSON body for
`.isError` as above. If it errored, report the failure to the user and stop — do not diagnose
from nothing.

`/tmp/traces.json` is the whole run, **inline** (`getRunTraces` shape): a `run` summary,
`passingScenarios: [{ name }]` (the regression guard), and `failedScenarios[]` where **each entry
is a full scenario trace** — `conversationId`, `traceStatus`, `traceIds`, `spanCount`,
`truncated`, `scenario { name, description, failedChecks: [{ type, criterion }], scores }`, and
`conversation { turns: [...] }` (`[]` unless `traceStatus === 'AVAILABLE'`), plus `promptContext`.

`failedChecks` is the starting point for diagnosis — each entry names a criterion the agent's
output did not satisfy. `conversation.turns` is the chronological reconstruction of what the
agent actually did. `promptContext` is a lead to verify against the trace and sources, not
gospel. `run.iterations` tells you how many times each scenario ran — include it when reporting
rates so percentages make sense.

**Keep the payload on disk; never `cat` the whole file into context** — a run can be hundreds of
KB. Use `parse-trace.py` for per-scenario facts and `jq` to pull one scenario's turns only when
you need a transcript (see *Trace facts* below).

### What the turns contain

Each turn carries a `kind`: `user`, `assistant`, `tool_call`, or `tool_result`. A tool call and
its result are **separate turns**, reconstructed from different spans: the `tool_call` turn comes
from the model span's output and carries `toolName` and `toolArguments`; the `tool_result` turn
comes from the `execute_tool` span and carries `toolResult`, `status` (`success`/`failure`),
`error` — **and its own `toolName`/`toolArguments` too**, so a result turn alone identifies which
tool ran. A `tool_call` with no following `tool_result` is an unterminated call — a likely
task-layer hang. Tool results are OData-stripped deterministically (envelope unwrapped, metadata
dropped, every business field preserved, 4000-char backstop); a thin or empty `toolResult` means
the tool genuinely returned little, not that it was trimmed. Agent and user messages are full and
unredacted.

### Durability and crash-resume

`/tmp` is **transient** — a container crash/restart loses it (your conversation survives; the
file does not). Two consequences:

- **Resume by re-pull.** On a sandbox-restart / file-not-found signal mid-operation, re-pull the
  evidence (`get_traces` is idempotent and cached) and re-check the working tree — what you have
  already changed — before continuing, rather than assuming mid-operation state survived.
- **Apply every fix through `write_file`.** It persists to the backend first, then the live
  container, so a fix survives a crash. **Never** edit project files with in-container shell
  (`sed`, redirects) — those ride the reverse-sync debounce with no SIGTERM flush and are lost if
  the crash lands in the down-window.

---

## Trace facts: parse once, grep the file

Before reading turns by hand, run the deterministic parser and **redirect its summary to a file**,
then grep that file instead of re-reading the parser's output from context each time. This keeps
the facts on disk (grep-able, re-readable) rather than re-flooding context on repeat use.

```sh
# whole run (fix-eval-run):
python3 skills/agent-evaluation/scripts/parse-trace.py /tmp/traces.json > /tmp/fix-facts.txt
# one sliced scenario (fix-failing-scenario):
python3 skills/agent-evaluation/scripts/parse-trace.py - < /tmp/scenario.json > /tmp/fix-facts.txt
```

`/tmp/fix-facts.txt` carries `traceStatus`, `truncated`, per-turn tool-result outcomes (with tool
names), whether a final agent turn has content, and a `gradeable` verdict per scenario — plus the
`trace_qa` counts (available / pending / unavailable / truncated) for a whole run. Grep it:
`grep 'gradeable: NO' /tmp/fix-facts.txt` finds HARD-GATE candidates; the per-scenario tool names
are a strong clustering signal.

The three `gradeable` states are load-bearing:

- **`gradeable: NO`** — the agent produced no gradeable output (a tool result failed, a tool call
  had no result, or there is no final answer). This is an immediate **HARD GATE**: an agent bug,
  never a test rewrite (see *Adjudication*). Confirm the cause in the transcript.
- **`gradeable: n/a`** — no runtime trace (`PENDING`/`UNAVAILABLE`); weaker evidence, **not** an
  automatic agent bug. Follow `traceStatus` handling below; re-pull a `PENDING` one shortly for
  grounded evidence.
- **`gradeable: YES`** — retrieval succeeded and the agent answered. Continue the diagnosis
  against the criteria.

### `traceStatus` handling

| Status | What it means | How to proceed |
|---|---|---|
| `AVAILABLE` | Full runtime transcript is present | Full grounded diagnosis against the transcript |
| `PENDING` | Trace exists but ingestion lag means it is not in CLS yet | Tell the user a retry will give grounded evidence. You may proceed from `failedChecks` + agent source + eval source, but flag that the diagnosis lacks runtime evidence. |
| `UNAVAILABLE` | No trace for this run | Proceed from `failedChecks` + agent source + eval source only. State plainly that you are reasoning without the agent's actual output — conclusions are weaker and the fix carries more uncertainty. |

When `traceStatus` is not `AVAILABLE`, say so in every diagnostic conclusion. Do not present a
diagnosis as grounded when it is not.

---

## Load sources

Resolve `output_dir` first via the standard path resolution in
[SKILL.md — Paths](../SKILL.md#paths) — the fix targets the same asset folder as the generate and
extend operations. Then load, **in this order**:

**a. The evidence** — the sliced scenario (`/tmp/scenario.json`) or the run bundle
(`/tmp/traces.json`) plus `/tmp/fix-facts.txt`. Read `failedChecks` and the turns before opening
any file.

**b. The eval source** — what was expected and how the test was defined:
- `{output_dir}/aeval/eval.yaml` — find the requirement(s) whose text matches or underlies each
  failed criterion
- `{output_dir}/aeval/testcases/<scenario-id>.yaml` — the full test case: task summary, persona,
  setup steps, and all three validation blocks
- `{output_dir}/mcp-mock.json` — tool definitions and mock responses; needed to verify whether an
  asserted value is actually producible from the agent's available data

**c. The agent source** — what the agent was built to do:
- The system prompt and `app/SKILL.md` or equivalent — the agent's decision rules
- `app/agent.py` or equivalent entry point — tool wiring and the runtime call path
- Any domain logic modules (verdict rules, classification, computation) — often where correct
  logic lives that is not always called
- Tool definitions — what tools exist and what they return

Read **(b) before (c)**. The eval source tells you what was expected; the agent source tells you
why the agent did what it did. The wrong order makes you evaluate the agent against your
assumptions about the test rather than against the actual criterion.

**d. Customer context** — if the UI forwarded free-text alongside the trigger, treat it as
high-signal and thread it into the diagnosis and fix. The customer knows their agent.

---

## Adjudication: agent bug or test bug?

**Default: fix the agent.** The eval cases are LLM-generated and can be wrong — but the default
assumption is that the failure reflects a real agent defect.

**HARD GATE — before considering whether the test is at fault, confirm two things: (1) every tool
call returned successfully with data, and (2) the agent produced a gradeable answer.** If *any*
tool call returned `status: failure`, returned nothing, or has no result turn — even when others
succeeded — or the agent produced no answer or stalled, the criteria are irrelevant: there is
nothing to grade. That is **always** an agent bug: missing failure handling. Fix the agent. Never
rewrite or loosen the test for a no-output scenario — the test cannot pass regardless and the
rewrite only masks the bug. This is exactly the `gradeable: NO` verdict from `parse-trace.py`.

Fix the test **only** when every tool call succeeded, the agent produced a graded answer, and you
can state explicitly which of the following is true:

- The criterion asserts a value that `mcp-mock.json` does not and cannot produce for this scenario
- The criterion directly contradicts a stated requirement in the PRD
- The scenario setup makes it logically impossible for a correctly-behaving agent to satisfy it
- The criterion was generated from a misreading of the PRD and checks something the PRD never
  required

**Never loosen a criterion because it is hard to satisfy.** Difficulty is not a justification. If
the PRD requires specific behavior and the criterion checks it, the criterion is correct however
hard it is for the current agent to pass.

**Preserve passing scenarios.** Before applying any fix, review the passing scenarios most likely
to exercise the same logic, tool path, or prompt instruction (`passingScenarios` in
`/tmp/traces.json`). If the changed surface is shared broadly, expand the review to the full set
of test cases in `{output_dir}/aeval/testcases/`. A fix that makes the failing scenario pass but
causes a currently-passing scenario to fail is **not** a valid fix — revise the fix, never the
passing scenario.

**Do not fix the symptom.** Editing a criterion or mock value to match the agent's wrong output,
or broadening a rule until the number moves, is not a fix — it is concealment. The goal is a
correct agent, not a higher score.

---

## Apply the fix

### Agent fix

Edit one or more of: system prompt, `app/SKILL.md` or equivalent, skill files under `app/skills/`,
domain logic modules, tool wiring in the entry point. Constraints:

- **Honor the agent's own guardrails.** A read-only agent stays read-only; an agent scoped to a
  domain stays in it. Do not introduce behavior the agent is forbidden from having.
- **Scope the fix.** No refactor, restructure, or feature beyond what is needed to make the
  criterion pass without breaking other scenarios.
- **Prefer the more scoped fix.** Given a choice between wiring a deterministic module into the
  runtime path and editing the system prompt or a shared skill file, prefer the module wiring. A
  system prompt is shared across all the agent's capabilities — a change for one scenario can
  silently alter paths it was never meant to touch; a module wired into one call path cannot
  regress an unrelated path. After any shared-surface change, re-read the passing scenarios and
  confirm none of their criteria intersect the changed logic.
- **Implement failure and timeout handling as code** — a try/except or a timeout-mapped fallback
  (e.g. → a defined outcome like BLOCKED or not-found) belongs in the code path, not the prompt.
  A prompt instruction cannot stop a task-layer hang.
- State precisely: which file, which section, what changed, and why it satisfies the failed
  criterion.

### Test fix

When adjudication concludes the test is wrong, treat it the way the generate and extend operations
treat a corrected case:

- Edit `aeval/eval.yaml`, `aeval/testcases/<id>.yaml`, and/or `mcp-mock.json`.
- Every modified test case must be schema-valid — run
  `python3 skills/agent-evaluation/scripts/validateschema.py` on each affected file and fix every
  error before continuing.
- A rewritten criterion meets the same standards as a generated one — apply
  [writing-checks](./writing-checks.md) and [schemas](./schemas.md).
- You may **not** change `config.yaml`, `000_pre_setup.yaml`, or `zzz_post_teardown.yaml`.

#### Stage the full suite before publish — and stop if it would delete tests

Publishing **replaces** the live suite with the staged set and **deletes any non-staged testcase**
(the static env templates excepted). A test fix that stages only the edited file therefore
silently deletes every passing test. So stage the **entire** current suite first, then publish:

```sh
STG="<output_dir>/aeval/.staging"
rm -f "$STG/eval.yaml" "$STG/testcases/"*.yaml 2>/dev/null || true   # clear leftovers
mkdir -p "$STG/testcases"
cp "<output_dir>/aeval/eval.yaml" "$STG/eval.yaml"
for f in "<output_dir>/aeval/testcases/"*.yaml; do
  base="$(basename "$f")"
  case "$base" in
    000_pre_setup.yaml|zzz_post_teardown.yaml) ;;   # env templates: publish copies these, no-clobber
    *) cp "$f" "$STG/testcases/$base" ;;
  esac
done
# apply your test edits under .staging/, then validate the whole staged set
for f in "$STG/testcases/"*.yaml; do
  python3 skills/agent-evaluation/scripts/validateschema.py "$f"
done
```

**HARD STOP — never publish a suite smaller than the live one.** Count before publishing; if
staged < live you are about to delete passing scenarios — stop and re-stage, do not publish:

```sh
live_n=$(ls "<output_dir>/aeval/testcases/"*.yaml 2>/dev/null | grep -v -E '(000_pre_setup|zzz_post_teardown)\.yaml' | wc -l)
staged_n=$(ls "<output_dir>/aeval/.staging/testcases/"*.yaml 2>/dev/null | wc -l)
if [ "$staged_n" -lt "$live_n" ]; then
  echo "STOP: staged ($staged_n) < live ($live_n) — publishing would delete passing tests" >&2
  exit 1
fi
```

Then finish via [validate-and-report](./validate-and-report.md) — the semantic gate and publish,
preserving the staging discipline and coverage measurement. An **agent-only** fix does not
publish: deploy the agent and re-run the eval.

---

## Before finalizing

Self-check against each item and revise the fix if any fails:

- Change is scoped — no more than ~2 files per fix, no refactoring beyond what the failure(s)
  require
- Every change cites the specific transcript turn, criterion, or source line that justifies it
- No test case was mutated for a scenario where the agent produced no output
- No error is suppressed or swallowed — failure paths surface an explicit outcome
- The agent's own guardrails are intact (read-only stays read-only, domain scope unchanged)
- If a code fix was available, it was preferred over a shared-prompt edit

