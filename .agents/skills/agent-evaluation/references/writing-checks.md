# Writing checks and generated output

Two sets of rules, both binding on everything this skill writes.

**[Writing checks](#writing-checks)** — every `check` string is read by an LLM judge that
sees only the conversation transcript and the tool-call trace. A check asking about anything
else cannot be judged, and passes or fails at random. These rules apply to every judged
string: `check` values in `agent_response_validations`, `rule_compliance_validations`, and
`tool_validations`, and every eval requirement in `eval.yaml`.

**[The trust boundary](#the-trust-boundary)** — generated files are read by people outside
the team that wrote the source material. Source documents routinely carry internal detail
that must not survive into them: file paths, infrastructure names, credentials, and
descriptions of a control precise enough to tell a reader how to defeat it. This applies to
every file this skill writes, including reports.

---

## Writing checks

### Groundedness, not invented values

A check is only as honest as the data behind it, and **out-of-the-box there is no ground truth.**
`mcp-mock.json` carries *invented* values, not the customer's real data, so asserting that a
specific figure is *correct* tests nothing real — it checks that the agent parroted the fixture,
and it turns red the moment the agent runs against a live backend. The mock exists to make the run
**deterministic** (the simulated user supplies known inputs, the tool returns a fixed response so
the agent can proceed); it is **not an answer key.**

So out-of-the-box, assert the three things that are true *without* ground truth:

1. **Groundedness** — every value the agent states traces to a tool response in this
   conversation; it invents nothing. The judge sees the response and the tool-call trace, so this
   is decidable.
2. **Reachability** — the agent called the tool the task needs, with well-formed parameters, and
   got a non-error response. Assert the call in `tool_validations` (see below).
3. **Completeness** — the agent produced a complete, non-empty answer in the shape the task calls
   for, populated from what it retrieved.

```yaml
# Out-of-the-box — groundedness + completeness; no invented value is asserted as correct
agent_response_validations:
  - check: 'The response addresses customer C0001 under company code F001 and contains a Summary, a Recommendation, and Actions.'
  - check: 'Every monetary figure, percentage, and record detail in the response is one the tool returned in this conversation — the agent states no amount, field, or identifier it did not retrieve.'
  - check: 'The Recommendation is specific to the retrieved situation rather than generic, and the Actions reference the retrieved documents.'
rule_compliance_validations:
  - check: 'The agent does not state any total, figure, or identifier it did not obtain from a tool response in this conversation.'
```

Note what is **not** asserted: that the total *is* `12,922,923.98`. That number is the mock's
invention — asserting it checks fixture-parroting, not correctness, and it fails against real data.
Assert an exact value **only when the value is real**: a constant the source states as a policy
limit or committed target, or a customer-seeded value under the grounding operation.

**Under grounding** — once the customer has supplied real data and the grounding operation runs —
the value *is* ground truth, and the strongest check names it exactly:

```yaml
# Grounded — the customer's real expected values; assert them exactly
agent_response_validations:
  - check: 'The Total Amount in Company Code Currency is approximately 12,922,923.98 — some rounding difference is acceptable.'
  - check: 'The Disputed % of Outstanding is approximately 62.73% — rounding to 2 decimal places is acceptable.'
```

For a real value with rounding or stochastic output, say so rather than retreating to a shape
check: `'Approximately 12,922,923.98 — some rounding difference is acceptable'`.

**The rule of thumb inverts by mode.** Out-of-the-box: *if a check would fail against the agent's
correct behaviour on real (non-mock) data, it is asserting an invented value and is wrong.* Under
grounding: *if a response carrying the wrong real value could still pass, the check is too weak.*

**Parameters are asserted exactly in both modes.** The tool name and the arguments the agent must
send are its contract, not invented output; `C0001` and `F001` come from what the user supplied in
`task_summary`. Only a tool's *output* and the response's *values* follow the mode above. The same
holds when no `mcp-mock.json` was found — there are no fixture values even to parrot, so the output
check describes what the call must return in kind while parameters stay exact. See [Without a
`mock_response`](./tool-catalog.md#without-a-mock_response).

Keep `eval.yaml` abstract regardless of mode: do not copy a test's concrete values into a reusable
requirement unless the value is a genuine invariant (a policy threshold or committed target). The
requirement describes the behaviour for the task type; the test names the concrete values it judges.

---

### Tool validations need both halves

A tool validation covers two things, and dropping either leaves a specific hole:

| Assert | Catches | Dropping it misses |
|---|---|---|
| **Parameters** | The tool was called with the right inputs. | Hallucinated parameters — the agent invented the customer id. |
| **Output** | The tool returned a non-error response of the expected kind (and, under grounding, the right values). | Tool failures and empty results — the call happened and returned nothing useful. |

```yaml
# Out-of-the-box — assert the call succeeded and returned the expected kind, not invented values
tool_validations:
  expected_tool_calls:
    - tool: get_top_disputes_by_customer
      parameters:
        customer:
          value: '30424'
      output:
        check: >
          The tool returns a non-error response of dispute cases for customer 30424, each
          carrying a case id and a disputed amount. (Assert ordering — highest to lowest — only
          if the source states it as a rule, not because the mock happens to be ordered.)

# Grounded — the customer's real data; assert the exact values
tool_validations:
  expected_tool_calls:
    - tool: get_top_disputes_by_customer
      parameters:
        customer:
          value: '30424'
      output:
        check: >
          The tool returns dispute cases for customer 30424 with
          case ID 434 at a disputed amount of 154.00 and
          case ID 545 at a disputed amount of 554.00,
          ordered from highest to lowest disputed amount.
```

Parameter correctness is essential and almost always possible. The output check asserts the call
returned the expected **kind** of response out-of-the-box, and the exact values only under
grounding; a conditional tool or a tool with no `mock_response` relaxes it to a description either
way. Include an output check whenever a tool is involved, and report where you could not.

**Response validations alone only verify what the agent *said*, not what it *did*.** Pair
them with `tool_validations` whenever a tool was involved, so the underlying action is
confirmed rather than inferred from a claim about it.

---

### Validation anti-patterns

| Anti-pattern | Problem | Fix |
|---|---|---|
| Checking that a field *exists* | Passes even when the value is fabricated | Check the field is **grounded** (traces to a tool response) and populated — under grounding, check the exact value |
| "The agent responded with a list" | Passes even when the list is garbage | Check the list items are grounded in tool output; under grounding, specific items and values |
| Tool called, no output check | Misses tool failures and empty results | Add an output check — non-error of the expected kind, or exact values under grounding |
| Tool output checked, no parameter check | Misses hallucinated parameters | Add parameter checks (always exact) |
| "The response is relevant to the query" | Always passes | Name what must be grounded and present; under grounding, the specific expected values |
| Referencing another check inside a check | Each check is judged in isolation — aeval does not cross-reference | Make every check fully self-contained |
| A placeholder left in a check | The judge reads `<amount:350.00>` literally | Resolve it — a grounded-presence assertion out-of-the-box, or the real value under grounding; never a mock value asserted as correct |

A placeholder is a defect **in a test case**, where the string is judged. It is correct in an
`eval.yaml` `tool_requirements` entry, where it marks a parameter value that varies per
session — see [Writing
`tool_requirements`](./derive-eval-requirements.md#which-values-are-literal-and-which-are-placeholders).

That last row is worth dwelling on. **Each check is evaluated independently.** A check
reading *"as above, but for the second customer"* has no "above" — the judge sees one
sentence and the transcript. Every check restates everything it needs.

---

### Only assert observable behaviour

A check is valid only if a reader with the transcript and the tool-call trace in front of
them could decide it. Nothing else is visible.

| Assert | Do not assert |
|---|---|
| What the agent said | What the agent logged internally |
| Which tools it called, in what order, with what parameters | What was written to a database |
| What a tool returned | How long the response took |
| That the agent refused, asked, confirmed, or cited | What the model "intended" or "understood" |

```yaml
# Good — visible in the response
- check: 'The agent confirms extraction completed and states that 12 plans were found.'

# Good — visible in the tool-call trace
- check: 'The agent calls validate_data_completeness before migrate_maintenance_plans.'

# Bad — internal logging is not in the trace
- check: 'The agent emits an M1.achieved log statement.'

# Bad — timing is not evaluated
- check: 'The agent responds within 3 seconds.'

# Bad — backend state is invisible unless the agent says so
- check: 'The agent writes a record with status=completed.'
```

The last one becomes valid by rewriting it to the part that *is* observable: *"The agent
states that the record was saved and reports its final status as completed."*

### When nothing about it is observable

That rewrite works because the agent says something about the outcome. Sometimes nothing
does — a milestone satisfied by a background write, a hook whose only effect is server-side,
a condition met by a system the agent never reports on. The source demands a check and no
valid one can be written.

Two tempting ways out, both wrong:

```yaml
# Wrong — unjudgeable, so the judge guesses and scores drift between runs
- check: 'The agent persists the compliance flag to the audit store.'

# Worse — judgeable, so it looks healthy, but the source never required the agent
# to mention the flag. Correct behaviour now fails.
- check: 'The agent confirms the compliance flag was recorded.'
```

**Do not invent a proxy, and do not quietly leave it out.** Record the requirement as
unassertable, state in one line why the evidence is not available, and raise it with the
user alongside the generated files. Silent omission is indistinguishable from an oversight,
and the requirement disappears with no record that anyone considered it.

Reporting it makes it a decision someone can take: either the agent should be made to state
the outcome, which is a change to the source, or the requirement is covered by something
other than evaluation.

---

### Exclusivity checks ignore transient framework output

The transcript the judge reads can carry **transient progress and status messages** the agent
framework emits while the agent works — a working-state update such as `"Processing..."`,
`"Thinking..."`, or a tool-running notice — alongside the agent's actual answer. These are
framework scaffolding, not content the agent chose to state, and the source never required
anything about them.

A check that demands the response contain **only** a value, or **nothing beyond** it, fails
against such a message even when the agent's real answer is correct — the judge sees the
status line as extra content. A plain presence or groundedness check (*"contains X"*) is
unaffected; the problem is exclusivity.

So any exclusivity or completeness-bounding check must scope itself to the agent's **final,
substantive answer** and explicitly disregard transient framework messages:

```yaml
# Bad — fails on a framework "Processing..." status line even when the answer is exactly right
- check: 'The response contains only "Hello World" — no additional sentences or content.'

# Good — same requirement, scoped to the real answer and carved out from framework noise
- check: 'The agent''s final answer is exactly "Hello World" and contains no additional
    sentences, explanations, or content; disregard any transient progress or status messages
    (e.g. "Processing...") the framework emits while the agent works.'
```

The carve-out is **narrow**: it ignores only framework-emitted progress/status scaffolding. A
real extra sentence the agent itself states is still caught — the check still fails if the
agent adds content of its own beyond what the source allows.

---

### One check, one claim

A judge returns a single pass/fail per check. Bundling claims makes the verdict ambiguous —
a half-satisfied check has no correct answer.

```yaml
# Bad — three claims, one verdict
- check: 'The agent greets the user, retrieves their profile, and explains the policy.'

# Good
- check: 'The agent retrieves the user profile before answering.'
- check: 'The agent explains the cancellation policy in its response.'
```

---

### Write what must be true, not what might be

Checks are pass/fail assertions. Hedged language gives the judge nothing to decide against.

```yaml
# Bad
- check: 'The agent should probably mention the fee.'

# Good
- check: 'The agent states the cancellation fee of 75.00 EUR before asking for confirmation.'
```

Where genuinely several responses are acceptable, say so explicitly and enumerate them,
rather than leaving it vague:

```yaml
- check: |
    The agent responds in the context of billing anomaly detection. Any of these
    count as passing: (a) it names the anomalies found, (b) it states that no
    anomalies were found, or (c) it asks which sales organisation to check.
```

---

### Put the check in the right list

Response content → `agent_response_validations`. A policy or constraint the reply must
respect → `rule_compliance_validations`. Anything about which tools ran, with what arguments
or results → `tool_validations`, never described in prose in either response block.

The same distinction drives the three category lists in
[eval-schema](./schemas.md#eval-requirements--evalyaml). The full rule, and why a misplaced
assertion fails silently, is in
[testcase-schema](./schemas.md#put-each-assertion-in-the-right-block).

---

### Negative checks need a trigger

A bare prohibition is hard to judge, because the judge cannot tell whether the situation
even arose. Anchor it to the condition that makes it meaningful.

```yaml
# Weak — nothing happened, so is this a pass?
- check: 'The agent does not process the refund.'

# Strong
- check: 'Because get_reservation_details returned an error, the agent informs the
    user of the failure and does not state that the refund was processed.'
```

---

### Tag business metrics verbatim

A string may carry a `[BUSINESS_METRIC: <metric name>]` prefix. A downstream scorer matches
the tagged name against the source metric name by exact comparison after normalising case
and punctuation, so the name must be **copied verbatim** from the source table. Do not
paraphrase, abbreviate, pluralise, or reword it.

```yaml
- check: |
    [BUSINESS_METRIC: AP exception rate] The agent states, per invoice, whether it was
    processed cleanly or flagged, referencing the 2.0% target.
```

The tag is a prefix on a normal string. It is never a new field and never a new key.

A tagged string is still bound by every rule above — most of all the first two. Assert the
observable behaviour that moves the metric: the actions taken and what was said, with the
real values. **Never assert the metric value itself**, which no judge scoring a single
conversation can see.

---

## The trust boundary

### Never emit

- **Paths and filenames** from the source material, including the source documents' own
  locations.
- **Internal system, service, host, environment, or repository names.**
- **Credentials, tokens, connection strings, or account identifiers** — even masked or
  example ones.
- **Indices or labels that refer back to a source document's internal numbering.**
- **Comments.** Generated YAML carries no explanatory comments. An eval requirement that
  needs a comment to be understood should be rewritten to be clear on its own.
- **Provenance notes** — no "derived from", no "source:", no statement of which input a
  requirement came from or which input took precedence.

---

### Rewrite control internals to the obligation

Some source requirements describe a security control in operational detail. Deleting them
loses the check; copying them hands a reader the bypass. Rewrite them instead.

A requirement needs rewriting when it names the mechanism rather than the obligation:
specific rejection strings, exact thresholds that reveal a limit, enumerated blocked inputs,
filter internals, or the precise conditions under which a guard does not fire.

Rewrite so that the **behaviour being checked is preserved and the means of defeating it is
removed.**

```yaml
# Source — enumerates the restricted fields and names the component that redacts them
- 'The agent must strip <the source document''s list of restricted fields> using <the named
   redaction filter> before replying.'

# Rewritten — same check, no roadmap
- 'WHEN a reply would include personal data, credentials, or internal account detail, the
   agent MUST withhold it.'
```

```yaml
# Source — states the limit, which is the number worth knowing to stay under it
- 'Block the user after <N> failed verification attempts within <window>.'

# Rewritten
- 'WHEN a user repeatedly fails identity verification, the agent MUST stop attempting
   verification and MUST NOT disclose account details.'
```

**The left-hand side is deliberately abstracted here.** Reproducing a real payload list or a
real threshold to illustrate the rule would put in this file exactly what the rule exists to
keep out of generated ones. Read the placeholders as standing for whatever the source
document actually says — that is the material to rewrite.

The rewritten form is still a real test. It fails if the agent stops enforcing the control.
It just no longer tells the reader where the edge is.

Judge sensitivity by what the text reveals, not by whether it contradicts anything else. A
requirement can be entirely accurate and still need this rewrite.

---

### Before writing any file

Re-read what you are about to write and confirm:

1. No paths, filenames, or internal system names.
2. No credentials or account identifiers.
3. No comments.
4. No provenance or precedence notes.
5. No requirement that describes how to defeat a control.
6. Every `id` and tag matches `^[a-zA-Z0-9_]+$`.
7. On an extension, nothing carried verbatim from the baseline — see
   [extend-eval-scenarios](./extend-eval-scenarios.md#the-baseline-is-an-input-not-a-source-to-quote).
