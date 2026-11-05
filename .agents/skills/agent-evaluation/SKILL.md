---
name: agent-evaluation
description: 'Generates aeval evaluation assets from a PRD — `eval.yaml`, dynamic-conversation test cases, and `config.yaml` — for an agent or agent extension, and fixes failing eval results. Use this skill when the user wants to evaluate an agent, generate eval test cases, create aeval tests, set up agent evaluation, update the evaluation after extending an agent, or fix a failing eval scenario or eval run. For failing runs, start from a thin trigger (`executionId`, `solutionId`, `semanticVersion`) and use the sanctioned MCP tools: `get_results` for the run header, `conversation_id`, and skipped scenarios; and `get_traces` for whole-run evidence stored on disk.'
metadata:
  version: 1.0.0
  author: sap-joule-studio
---

## How a run works

1. **Read [writing-checks](./references/writing-checks.md) and
   [schemas](./references/schemas.md).** They govern every operation. No file below repeats
   the instruction — assume both are loaded.
2. **Read the operation file** matching the request and follow it. Each names the further
   references it needs.
3. **Resolve `output_dir` once** (see [Paths](#paths)). Generation writes as it goes into a
   scorer-invisible `{output_dir}/aeval/.staging/` directory — never the whole suite held in
   memory and written at the end. Each test case is written one at a time, and the whole
   staged set is validated for structure in one validation phase before publish. On re-invocation, an existing `.staging/` whose stored PRD hash still matches is
   **resumed**, not restarted.
4. **Finish with [validate-and-report](./references/validate-and-report.md).** It runs the
   semantic checks over the complete staged suite, then **publishes** — moving the validated
   files into `aeval/` and copying the static templates. **The live `aeval/` is untouched
   until publish**, and several validation checks change staged files first.

**The structural validator ships inside this skill** at `scripts/validateschema.py`, run with
`python3`. The references invoke it as `python3 skills/agent-evaluation/scripts/validateschema.py <path>`
(workspace-root-relative, the convention other skills use). If the skill is mounted under a
different root, resolve the path relative to this skill directory — the script is always at
`scripts/validateschema.py` beside this file. It depends only on `pyyaml`; do not copy it into
the asset or `.staging/`, and do not reimplement it.

**The static env-management templates ship beside it** at `templates/000_pre_setup.yaml`,
`templates/zzz_post_teardown.yaml`, and `templates/config.yaml` (i.e.
`skills/agent-evaluation/templates/`, resolved the same way). They are copied into `aeval/`
by the publish script — never generate their contents by hand.

**Publishing is a script too:** `python3 skills/agent-evaluation/scripts/publish.py <output_dir>`
moves the staged suite into the live `aeval/`, copies the templates, deletes stale cases, and
removes `.staging/` — in one deterministic step. Do not perform the publish by hand; the
multi-step version drops the tail (templates, cleanup) on a small model.

**Reading the tool catalog is a script too:** `python3 skills/agent-evaluation/scripts/extract-tool-catalog.py <mcp-mock.json>`
prints the catalog with every `mock_response` reduced to a type skeleton (field names and types, no
values), so invented mock values never enter your context. **Never read `mcp-mock.json` raw** — see
[tool-catalog](./references/tool-catalog.md#2-read-the-tools--through-the-redaction-script-never-raw).
Depends only on the stdlib.

```
agent      PRD ───────────────┬──► eval.yaml           the eval requirements
                              └──► testcases/<id>.yaml the scenarios
           mcp-mock.json ──────►   tools, schemas, response field names (via extract script) — used by both

extension  PRD + intent ──────┬──► eval.yaml           reconciled with the base requirements
           base test suite ───┴──► testcases/<id>.yaml reconciled with the carried behaviour
           extension.yaml ─────►   tools granted, and when to call them — always read
           mcp-mock.json ──────►   descriptions and response field names (via extract script), when one exists
           translation.json ───►   descriptions when it does not — no mock responses

both                      ──────►  config.yaml         runtime parameters — derived from nothing
```

## The invariants

These hold across every operation. The operation files say how to satisfy them.

**Both artifacts come straight from the PRD.** Neither derives from the other. The eval
requirements say *what must be true*; the test cases say *what situation to put the agent
in*. Write the tests from the source, not from the eval requirements — an eval requirement
is a one-line rule, and the persona, identifiers, and edge cases a scenario needs do not
survive that abstraction.

**Eval requirements and tests must reach parity.** Every eval requirement is covered by at
least one test, and every test covers at least one eval requirement. Totality in both
directions, not a one-to-one mapping. Fix every orphan before writing, usually by adding the
missing eval requirement.

**Every source requirement reaches both artifacts.** Parity is between the two generated
files; this is about the document they came from. Every requirement, acceptance criterion,
milestone condition, and qualifying business metric in the PRD produces **at least one eval
requirement** and is exercised by **at least one test case**. The only exemption is a
requirement with no observable form, recorded as unassertable with a reason. Silence is never
an exemption — an uncovered requirement produces no failing test, only a smaller suite that
passes.

**The budget is per category, and gated by the registry.** Each of the three eval-requirement
categories is **capped at 10, with no fixed floor**, and the suite holds **at most 15 test
cases.** Generate only what the source states and the **enabled** dimensions require (resolved in
[generate step 2b](./references/generate-eval-scenarios.md#2b-resolve-which-dimensions-this-run-may-generate));
**never pad toward a count, and never generate a disabled dimension** (safety, security, and —
without customer grounding — business outcome). Count the eval requirements per category, never as
a total: a file that checks what the agent *says* in detail and barely checks what it *does* has a
hole no total reveals.

A category that is light because its dimensions are disabled is correct, not thin.
[Where the entries come from](./references/derive-eval-requirements.md#where-the-entries-come-from)
lists the recurring obligation types each category carries — but only the in-scope rows are mined.
**Never invent an entry to reach a count**: a requirement the source never stated is one the tests
must then satisfy, and the agent is marked down for behaviour nobody asked of it.

**Coverage is bought with checks, not with files.** The budget counts entries, not
assertions. A test case carries as many checks as its scenario supports, so covering one more
requirement is nearly always another check inside an existing scenario rather than another
file. With 15 or more eval requirements and at most 15 tests, most tests carry several
checks — that is the design, not a compromise. Reach for a new test case only when the
*situation* is genuinely different — a different journey, a different failure, a different
adversarial setup. See [the test case
budget](./references/design-test-cases.md#the-budget) and [the eval requirement
budget](./references/derive-eval-requirements.md#the-budget).

**Test cases are dynamic conversations.** One `dynamic_conversation` step each, driven by an
LLM-simulated user. The scenario lives in `user_agent.task_summary`; the assertions live in
the three validation blocks.

**Never generate prompt-injection or role-play/jailbreak tests.** These are out of scope for
this skill — do not write any test, eval requirement, or check about resisting prompt
injection, "ignore your previous instructions" attacks, or role-play/persona-override
("pretend you are…", developer-mode, jailbreak) manipulation. They are handled by a separate
platform guardrail layer, not by the agent's evaluation. This exclusion is **narrow**: it
removes only adversarial input-manipulation. It does **not** touch legitimate safety —
confirmation before a consequential or state-changing action, and refusal to disclose
personal data, credentials, or internal account detail — nor any `security` test about
privilege, permission, or tenant boundaries. Those stay. A `TRAP:` scenario built on ordinary
business pressure (a user insisting an approval already happened, inventing authority,
pushing to skip a verification step) is still in scope; only injection and role-play framings
are excluded.

**Checks name values, not shapes.** A check that a field is *present* passes against a
response carrying the wrong customer and the wrong amount.

**`mcp-mock.json` is optional, and preferred wherever it exists.** Look for it on either
operation. It carries each tool's name, description, `input_schema`, and deterministic
`mock_response`. **It is not an answer key**: out-of-the-box, assert that the values the agent
states are *grounded* in tool output, never that they equal an invented mock value (see
[writing-checks](./references/writing-checks.md#groundedness-not-invented-values)). To keep those
invented values out of your context entirely, **you never read `mcp-mock.json` raw** — the generator
reads it through `scripts/extract-tool-catalog.py`, which strips every `mock_response` to a type
skeleton (field names and types, no values). You get the tool names, descriptions, `input_schema`
(the source of the simulated user's identifiers), and response field names; the aeval runtime reads
the full file for its deterministic responses. When it is
absent, fall back to what the operation supports: the MCP translation files for an extension, a
`@tool` scan for an agent. Either way a tool's **output** assertion describes what the call must
return in kind rather than naming a value; parameters are still asserted exactly. See
[tool-catalog](./references/tool-catalog.md#which-source-applies).

**On an extension, `extension.yaml` is read either way.** It states which tools the extended
agent may call and when it must call them, and no other source answers either question. A
`mcp-mock.json` supplements it; it never replaces it.

**Take the tool source as it stands and stop.** It is the authority on the agent's tools. Do
not open the agent's source to cross-check it, confirm it, or supplement it, and do not read
it "for context" on how a tool behaves. Reading code becomes a tool source **only** in the
agent flow, when no `mcp-mock.json` is found anywhere, via the fallback in
[tool-catalog](./references/tool-catalog.md#fallback-no-mcp-mockjson) — never on an
extension, which does not contain the agent's code to scan.

**Read only the files the operation names.** The inputs are the source document, the tool
source, and — for an extension — the baseline requirements, the base test suite, and the
extension artifacts. Nothing else. Do not walk the agent's implementation, its tests, its
prompts, its dependencies, its notebooks, or its configuration looking for extra signal. It
costs a large amount of context for no gain, and it reliably produces tests asserting
implementation behaviour the source document never asked for, which
[validate-and-report](./references/validate-and-report.md) will then delete.

**A base test suite is read through an index, never whole.** It is the one named input large
enough to exhaust the context on its own. Take `id`, `tags`, and `description` across the
suite, cluster by behaviour, and open in full only what survives triage — see
[extend-eval-scenarios](./references/extend-eval-scenarios.md#3-triage-the-base-test-cases).

**`config.yaml` is outside all of this.** Runtime parameters only. No eval requirements, no
coverage, nothing derived from the source. **Its values are always the defaults** — never
ask the user for them.

**Never ask the user for the test case count or the runtime parameters.** Both have defaults
and both are applied silently. The only questions ever worth asking are the ones that
genuinely block the run: an ambiguous request, or an `output_dir` that nothing determines.

## Files

**Always read**

[writing-checks, how to phrase any judged string, and what must never appear in generated output](./references/writing-checks.md)

**Schemas** — read before writing anything

[schemas, the shape of eval.yaml and the test case files, plus the mandatory tag set](./references/schemas.md)

**Operations — read the one matching the request**

| Request | Read |
|---|---|
| Evaluate an agent, create its test cases, validate before release, monitor it live | [generate-eval-scenarios](./references/generate-eval-scenarios.md) |
| Generate or update the evaluation for an agent extension | [extend-eval-scenarios](./references/extend-eval-scenarios.md) |
| Fix a specific failing eval scenario | [fix-failing-scenario](./references/fix-failing-scenario.md) |
| Fix an entire failing eval run | [fix-eval-run](./references/fix-eval-run.md) |
| Ground an existing eval suite in the customer's real data — business outcomes, exact values, forbidden operations | [ground-eval-scenarios](./references/ground-eval-scenarios.md) |

If the request is ambiguous, ask before doing any work.

**Called by the operations, not invoked directly**

[derive-eval-requirements, turns the source document into the three categorised requirement lists](./references/derive-eval-requirements.md)
[design-test-cases, the user journeys and the three test groups](./references/design-test-cases.md)
[tool-catalog, resolves the tools — mcp-mock.json for an agent, extension.yaml and the translation files for an extension](./references/tool-catalog.md)
[validate-and-report, the checklist, coverage measurement, and report — the semantic gate, then publish](./references/validate-and-report.md)

---

## Paths

**`output_dir` is always the agent's asset folder — `<solution-root>/assets/<asset-name>/`.**
Everything this skill writes goes under it, so `aeval/` lands at
`assets/<asset-name>/aeval/` and nowhere else.

Never derive it from the source document's parent directory, and never write relative to the
current working directory. The PRD is written as `product-requirements-document.md` at the
**solution root**, a sibling of `assets/` — so its parent is the solution root, and taking it
as `output_dir` puts `aeval/` beside `assets/` instead of inside it.

That failure is silent and total. The downstream scorer reads `assets/*/aeval/eval.yaml`; an
`aeval/` folder anywhere else is invisible to it, and it reports zero business-outcome
coverage with the rationale that the skill never ran. The files exist, the run looks healthy,
and nothing scores.

### Resolve it in two steps

**1. Find the solution root.** The folder holding `solution.yaml`. Failing that, the folder
holding `assets/` alongside `product-requirements-document.md`, `intent.md`, or
`specification/`. Given any path inside the solution, walk up until you find it.

**2. Find the agent's asset folder under `assets/`.** Take the first that resolves:

| Rule | |
|---|---|
| The folder whose `asset.yaml` declares `type: agent` or `type: agent-extension` | The normal case. Sibling assets of `type: mcp-server`, `n8n-workflow`, or `data-product` are never the target. |
| The folder containing `mcp-mock.json` | The tool catalog sits at the agent's asset root, so it identifies the folder directly. |
| The asset the source document or the specification names | Use when several agent assets exist. |
| The only folder under `assets/` | Use when there is exactly one. |

`output_dir` is `<solution-root>/assets/<that folder>/`. If no step resolves it — no
`assets/` folder, or several agent assets and nothing choosing between them — **ask rather
than guessing, and never fall back to the solution root.**

Do not create an asset folder to have somewhere to write. If `assets/` holds no agent asset,
the agent has not been scaffolded yet and the evaluation has nothing to describe; say so.

```
<solution-root>/
  product-requirements-document.md   the source — read, never written
  solution.yaml
  aeval-base/                        base agent's assets, extensions only — read, never written
  assets/
    <asset-name>/                    ← output_dir
      asset.yaml
      mcp-mock.json                  the tool catalog — read, never written
      aeval/
        .staging/                    scorer-invisible; this run writes here until publish
          progress.json              the one manifest — PRD hash, mapping, plan, written ids
          eval.yaml                  staged eval requirements
          testcases/<id>.yaml        each case, written one at a time, batch-validated
        eval.yaml                    the eval requirements    — published from .staging
        testcases/
          000_pre_setup.yaml         env management template  — cp -n from templates/
          <id>.yaml                  one file per test case   — published from .staging
          zzz_post_teardown.yaml     env management template  — cp -n from templates/
        config.yaml                  runtime parameters       — cp -n from templates/
```

`aeval-base/` is the exception that stays at the solution root: it is the base agent's
shipped baseline, not part of this asset. It is read and never written.

Create `aeval/.staging/` and `aeval/.staging/testcases/` before writing into them; the live
`aeval/` and `aeval/testcases/` are created at publish.

Do not confuse `eval.yaml` with `config.yaml` — same directory, unrelated contents, and
neither reader fails loudly when given the other's.

**An `aeval/` folder at the solution root is the old layout.** Read it as the baseline if the
asset folder has none, write the result to `assets/<asset-name>/aeval/`, and say in the
report that the location moved. Never write to the old location, and never leave the run
having written to both.

**Locating `mcp-mock.json`.** Search `{output_dir}/mcp-mock.json` first — that is where it
belongs. Then `<solution-root>/assets/*/mcp-mock.json`, then anywhere under the solution root
excluding paths containing a `.claude/` segment. **Stop at the first hit and use that file as
is.** If none is found, follow the fallback in
[tool-catalog](./references/tool-catalog.md) — never continue with an empty catalog silently.

**Who writes what.** Generation writes as it goes, into `{output_dir}/aeval/.staging/`.
`derive-eval-requirements` and `tool-catalog` return their results to the caller; the
operation writes the frozen eval requirements to `.staging/eval.yaml` and each test case to
`.staging/testcases/<id>.yaml` one at a time, then running one `validateschema.py` validation phase over the whole staged set, and
amending the staged `eval.yaml` as scenarios surface what the source implied.
[validate-and-report](./references/validate-and-report.md) runs the semantic checks over the
staged set and then **publishes** — copying `eval.yaml`, moving the test cases, and copying
`config.yaml` and the env templates from `templates/` into the live `aeval/` once every check
has passed.

Requirements are settled before the tests are designed because the order matters — tests
written first would only mirror themselves. Staging is what lets a run that stops early be
**resumed** rather than lost: the live `aeval/` is never touched until publish, so an
interrupted run leaves resumable `.staging/` and the previous published suite intact, never an
unvalidated `eval.yaml` that a later run would find and trust.
