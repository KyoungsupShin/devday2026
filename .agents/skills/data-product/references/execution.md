## Invocation Rule

**Do not invoke this skill directly from an end-user request.**

This skill is invoked only from `specification`. Requirement capture and data product search/selection are performed by `intent-analysis` before this skill is ever called.

> **Prerequisite:** Before this skill runs, `intent-analysis` must have completed and written `intent.md` with confirmed ORD ID(s). If `intent.md` does not exist or contains no confirmed ORD ID, stop and run `intent-analysis` first.

| Triggered by | Mode | Steps to execute | Then |
|---|---|---|---|
| `specification` | **Execution Mode** | Steps 1a onwards. Search and selection were completed during `intent-analysis` — use confirmed ORD ID(s) from `intent.md`. | Continue to completion |

### Execution Mode
Activated when called from `specification`. Search and selection have already been completed during `intent-analysis`. Resume from Step 1a using the ORD ID(s) confirmed in `intent.md`.
---

# Data Product Generation Skill — SAP Data Product Generator

Creates a derived data product from existing SAP primary data products via the `jl data-product` CLI.

Execute this workflow in order. One step at a time. Never skip a gate.

---

## Fast Track Mode

- While executing the Data Product Skill in Fast Track Mode, you must do the following:
  - Execute the steps in the specified order
  - Never skip or bypass any [MANDATORY], [GATE], or [MANDATORY GATE] steps or questions
  - Never skip or bypass any steps that require user approval or input
  - Respect any pre-defined rules in this skill
  - If a step specifically mentions'FAST-TRACK EXEMPT', you must not skip it and will have to ask for user approval irrespective of any existing Fast Track Mode rules at all costs

### Language

Apply terminology and path rules from [references/TERMINOLOGY.md](references/TERMINOLOGY.md).

- Name, title, shortDescription, and description are business metadata — write them from the user's perspective, not the implementation's.

---

## Known failure modes

**Read [references/TROUBLESHOOTING.md](references/TROUBLESHOOTING.md) when a CLI call or CDS edit behaves unexpectedly.**

---

## Step 1a — Propose & Approve Properties [GATE]

**Only proceed after input DP confirmation from `intent-analysis` (ORD ID(s) confirmed in `intent.md`).**

Propose:

| Property          | Rule                                                            |
| ----------------- | --------------------------------------------------------------- |
| Technical Name    | CamelCase, 1–70 chars                                          |
| Business Name     | Derived from Technical Name with spaces                         |
| Short Description | 1–255 chars — describe what the data is about and who uses it |
| Description       | Any length — expand on the business purpose                    |
| Responsible       | Defaults to 'customer:vendor:Customer'. Regex Pattern: ^([a-z0-9]+):(vendor):([a-zA-Z0-9._\-]+) |

Ask: "The responsible field will default to customer:vendor:Customer. Would you like to use a different value?"

**[GATE - FAST-TRACK EXEMPT] Wait for explicit user approval even in Fast Track mode.**
**On change:**
- If an asset folder exists under the previous name or specification placeholder (e.g. `assets/<old_folder_name>`), immediately delete it: `rm -rf "<working_directory>/assets/<old_folder_name>"`.
- Update properties, compute the new `folder_name`, and re-propose to the user.

---

## Step 1b — Create Session Folder & Write Metadata [MANDATORY GATE]

**Complete this in full before calling any `jl data-product` tool.**

Execute the deterministic initialization script in a single command:

```bash
node "<skill_dir>/scripts/init_session.js" \
  --name "<approved_name>" \
  --title "<approved_title>" \
  --short-desc "<approved_short_desc>" \
  --desc "<approved_desc>" \
  --source-dps '[{"ordId":"<ord_id1>","version":"<version1>"},{"ordId":"<ord_id2>","version":"<version2>"}]' \
  --responsible "<approved_responsible>" \
  --workspace-dir "<working_directory>" \
  [--solution-id "<solution_id>"] \
  [--overwrite]
```

Where `<skill_dir>` is the path to the data-product skill directory. Pass `--solution-id` if a solution ID/UUID is available in context. Pass `--overwrite` if re-running on an existing session folder.

Store the returned `session_folder` in context. Proceed to Step 2 once all 4 gates pass.

---

## Revisions

If the user requests any mid-flow change (input DP, technical name, business name, namespace, enrichments, filters): read `references/revisions.md` and follow the procedure there before continuing.

---

## Step 2 — Fetch Aggregated CSN, Generate CDS, and Fetch AMS Policy

**Prerequisite check:** confirm `session_folder` ends with `-data-product` and `.ddp_metadata.json` exists inside `<session_folder>/work/`. If either false, complete Step 1b first.

Run `fetch-and-prepare`. No user output during execution.

```bash
jl data-product fetch-and-prepare \
  --data-products '[{"ordId":"<ord_id1>","tenantId":"<tenant_id1>"},{"ordId":"<ord_id2>","tenantId":"<tenant_id2>"}]' \
  --session-dir <session_folder>/work
```

This single command fetches the aggregated CSN, compiles `transformation.cds`,builds `csn_graph and fetched ams policy.

`--data-products` is always a JSON array of `{ordId, tenantId}` pairs, even for a single DP. `ordId` is the `ord_id` field from the search result (major version, e.g. `v1`) — NOT the full versioned `id` field.
See [TOOLING-CLI.md](references/TOOLING-CLI.md) for full reference.

→ **On success (`success: true`):** store `output_path` as `file_name_agg_csn`, `transformation_cds` as `file_name_agg_cds` (will be `<session_folder>/transformation.cds`), `csn_graph_path` for the `csn-*` query tools, and `<session_folder>/work/input-dp-ams-policy.json` as `file_name_ams_policy` (always written — a stub when `ams_policy` is null — so this path is used by Step 5b regardless).

- If `not_available_ids` non-empty: *"The schema for [not_available_ids] is not currently available. Continue with [successful IDs] only, or select a different source data product?"* **[GATE]**

→ **On failure:** nothing was written — do not store any path. (The command stops before compiling if zero data products were fetched or the CSN is empty.)

- All 404: *"Schema for all selected data products is not currently available. Select a different source data product?"* **[GATE]** Re-run the search inline (call `dpca-mcp-server__ums_search_data_products`) or ask the user to provide a different DP ID.
- Domain inactive: follow [TROUBLESHOOTING.md](references/TROUBLESHOOTING.md) → "Step 2: All domain schemas inactive".
- Other errors: show verbatim, ask *"Try a different DP, use only one, or investigate?"* **[GATE]**. "Investigate" means: read [TROUBLESHOOTING.md](references/TROUBLESHOOTING.md) → Step 2 for a matching error pattern, verify the DP ID format is correct, and retry before re-running the search.

## Step 3 — Explore Schema, Detect Enrichments, and Build Cube

Recall transformation requirements from `intent-analysis` context.

### Schema Exploration (run silently — never show output to user)

An entity is relevant if: (a) its name or label contains words from the user's requirement, (b) it holds fields explicitly mentioned in the transformation, or (c) it is a FK join target of a primary relevant entity.

List available entities first:

```bash
jl data-product csn-list-entities --csn-graph-path <csn_graph_path>
```

Call `csn-get-schema` **once**, passing **all** entities you plan to reference in a single `--entity-names '["<fqn1>","<fqn2>",...]'` array — do **not** call it separately per entity. The response is `{ "schemas": [ ... ] }`, one entry per entity. **Skip any `@virtual` field** — it does not exist in the Spark table and breaks at runtime.

Once `csn-get-schema` has returned, resolve all field lookups from that response — do not call `csn-search-fields` for fields already present in the schema. Use `csn-search-fields` only when you need to locate a field whose entity is not yet known.

For each planned join, **verify type compatibility before writing it**: check that the join key types on both sides match (e.g. String to String, Integer to Integer). If they differ — even if the column names look related — **do not write a silent broken join**. Surface it:

> *"[FieldA] on [EntityA] is [TypeA] but [FieldB] on [EntityB] is [TypeB] — they use different identifier systems and won't join meaningfully. Options:*
>
> - *Build from [EntityA] data only, grouped by the code as-is*
> - *Search for a bridging data product that maps [TypeA] → [TypeB]*
> - *Use a different source entity that shares the same identifier system"*
>
> **[GATE - FAST-TRACK EXEMPT] Wait for user choice even in Fast Track mode.**

For each planned `left outer join`: confirm the joined entity's PK from `csn-get-schema` key markers and include it in the SELECT list.

See [TOOLING-CLI.md](references/TOOLING-CLI.md) for the full `csn-*` command reference.

After exploration: state in one sentence which entities you will use and why, then continue.

### 3a & 3b. Cross-DP References & Enrichments [EDGE CASES]

*If schema exploration reveals unresolved FK signals OR qualifying associations: read [references/step-3-enrichments.md](references/step-3-enrichments.md) and follow the instructions there. Otherwise skip to 3c.*

### 3c. WHERE Clause Confirmation [GATE]

If the requirement includes any filter condition:

**First — check for Category 1 SparkMV violations:** if any filter uses `current_date()`, `current_timestamp()`, `now()`, `rand()`, `uuid()`, or `unix_timestamp()` without args — do NOT include it. State: *"The filter `<expression>` uses a non-deterministic function which will cause data product creation to fail. Which source date field should I use instead?"* Resolve before proceeding.

**Then — present confirmed filters as a table:**

| Column            | Business Label          | Filter Value             | Warning |
| ----------------- | ----------------------- | ------------------------ | ------- |
| `<column name>` | `<label from schema>` | `<value or condition>` |         |

**DATE-LITERAL WARNING:** if any filter value is a hardcoded date (YYYY-MM-DD, YYYYMMDD, named month), add a mandatory warning row: "DATE-LITERAL WARNING — hardcoded date will not update automatically." Ask: *"Use a source date column instead, or proceed with this fixed value?"*

Ask: *"Please confirm these filters are correct."* **[GATE - FAST-TRACK EXEMPT] Do not write the WHERE clause until confirmed, even in Fast Track mode.**

### 3d. Write the Cube

**Read [references/CDS-PATTERNS.md](references/CDS-PATTERNS.md) before writing.**

State: *"Proceeding to write the Transformation."* then write the accurate, optimized and best executable CDS SQL for the business question. Write the best query first.

When a metric type is ambiguous (risk indicator, score, flag, index), pick the basis with the most supporting fields available in the source schema — do not ask.

When you `SUM`/`AVG` an amount or quantity that carries a currency or unit-of-measure (its source field has `@Semantics.amount.currencyCode` or `@Semantics.quantity.unitOfMeasure`), project that currency/unit field and add it to the `GROUP BY` — per-currency / per-unit grain — do not ask. Never sum across mixed currencies/units into one number. The user can iterate to pin a single currency/unit (a `WHERE` filter) or add exchange-rate data to convert first, if they want a different shape.

Write it right the first time:

- Every non-aggregated column in `GROUP BY` when any aggregate is present.
- Every joined table earns its place — columns projected or filtered. No "might be useful" joins.
- No flat `LEFT JOIN` to a finer-grained child under `SUM`/`COUNT` — that double-counts. **If you detect a fan-out join (ON matches only part of the key or a non-key column) under an additive aggregate, surface it as a business question before writing:** *"To get correct totals for [X], I need to summarise [Y] first — that's the more accurate approach. Want me to proceed?"* **[GATE - FAST-TRACK EXEMPT] Wait for confirmation before writing, even in Fast Track mode.** On yes: pre-aggregate the child. On no: proceed without the join.

After the SQL is correct, add `@Analytics.dimension : true` to every grouping/dimension column (codes, categories, dates, names, key columns). Apply silently — never ask the user about annotation choices.

One view per workflow; if a prior view exists (identified by the `@EndUserText.label` annotation stamped during a previous iteration's Step 4), replace it in-place — never add a second. If annotation is missing or multiple annotated views are found: stop, state "CDS structure error — fix or rewrite view before continuing", do not call `jl data-product generate-interop`.

**To replace an existing view:** find `@EndUserText.label`, replace the entire block from that annotation line through the closing `}` (or `};`) with the new view body only (no annotations). The annotation is re-stamped at the end of this iteration's Step 4.

Append the new view to the END of `file_name_agg_cds`. See [CDS-PATTERNS.md](references/CDS-PATTERNS.md) for entity syntax, cast rules, SparkMV compatibility rules, alias rules, and JOIN guidance.

**If a schema issue prevents writing the planned view:** either (a) write a reduced view using only entities that work and surface a one-sentence note, OR (b) ask: *"I encountered a schema issue with [entity] — proceed without it, or select a different source data product?"* **[GATE]** Never call `jl data-product generate-interop` without a `define view` appended.

---

## Step 4 — CDS Self-Check [MANDATORY GATE — silent]

Run the (slimmed) self-check from [CDS-PATTERNS.md](references/CDS-PATTERNS.md) internally. **Do not display or output the list, checkmarks, or intermediate results.**

> Structural, syntax, and SparkMV rules are now **enforced automatically** — `jl data-product generate-interop` (Step 5a) compiles the CDS and runs AST assertions, failing with the exact rule and line if the cube is invalid. Step 4 only pre-checks the handful of items the tool cannot judge (file position, alias naming, correlated subqueries, join type-compatibility) **plus the Intent-match group — whether the cube's grain, measures, and relative metrics actually deliver the approved spec. A cube can compile clean and still answer the wrong question; the compiler cannot see this, so the self-check must.**

> **Run the check by citation, not by ticking.** For every assertion marked **[CITE]** in the list, resolve it by quoting the specific cube token(s) that satisfy it (the `key`/`GROUP BY` element, the `source AS alias` pair, the approved-spec line, the `OVER(...)` denominator). If you cannot quote the tokens, it FAILS. If the quoted tokens contradict the promise (declared grain "by County" but the only `key` is `S.Supplier`), that is a FAIL — fix the cube, do not re-tick. A checkmark is satisfiable by a misread; a citation is not.

- **All pass:** state "CDS validated." then proceed to Step 5.
- **Any fail (Step 4 pre-check, OR the automated gate at Step 5):** state which rule failed and what you changed, fix it, re-run.
- **Same failure after 2 attempts:** stop. State what is failing and what was tried. Ask: *"I was unable to satisfy [rule] — would you like to simplify the cube or adjust the transformation?"*

After the Step 4 pre-check, run the three correctness passes from [references/CDS-PATTERNS.md](references/CDS-PATTERNS.md) as silent internal reasoning:

- **Pass 1 — Semantic**: column binding, type sanity, aggregate nesting, NULL semantics
- **Pass 2 — Join minimization**: DROP dead joins, FLAG suspicious ones, re-run to fixpoint
- **Pass 3 — Fan-out reshaping**: detect partial-key joins under aggregates; surface RESHAPE question if found, apply answer

Fix in place after each pass. Re-run Pass 1 after any Pass 2 DROP or Pass 3 reshape.

Stamp `@EndUserText.label` immediately before `define view` — no gap, no other annotations between them:

```cds
@EndUserText.label : '<Human readable label>'
define view <TransformationPurposeCube> as select from ...
```

---

## Step 5 — Create Data Product Definition [MANDATORY GATE]

## Step 5a — Data Product Definition Interop Generation [MANDATORY GATE]

Only call `jl data-product generate-interop` after ALL true:

1. `file_name_agg_cds` was modified in Step 3d
2. The Step 4 pre-check passed

`jl data-product generate-interop` validates the CDS itself (compile + AST assertions) before producing the `.dpd` — if the cube is invalid it returns `{"success":false,"error":"CDS validation failed: ..."}` naming the exact rule/line. Read that, fix the cube, and re-run. **`jl data-product generate-interop` is the ONLY valid way to produce the interop file. Never construct it manually.**

```bash
jl data-product generate-interop \
  --modified-cds <file_name_agg_cds> \
  --agg-csn      <file_name_agg_csn>
```

Store `output_interop_path` from the response.

**If "No transformed entities found":** run `grep -m 1 "^define view" <file_name_agg_cds>` internally. If missing: view was not written — re-run Step 3d. If present: view body is empty — re-run Step 4 before retrying.

**If CDS parse or syntax error:** read the line number. If inside the transformer view (≥ `define view` line): targeted fix only — never rewrite the full cube. If inside source entity definitions (< `define view` line): unresolvable schema issue — ask user to select a different source DP. See [TROUBLESHOOTING.md](references/TROUBLESHOOTING.md) → Step 5.

**Do not re-read `file_name_agg_cds` before fixing it.** You wrote the view in Step 3d, so its content is already in context — edit the view directly using the error's line/rule. Only re-read if the file was modified outside this session.

**If a DPD Validation error occurs**: Read and understand the validation errors. **Do not directly modify the DPD Interop File.** If the validation is failing in the header section, please check the **.ddp_metadata.json** file, make the changes to the fields accordingly, and regenerate the interop. If the validation is failing elsewhere, please only inform the user.

**If a CSN Validation error occurs**: Read and understand the validation errors. **Do not directly modify the DPD Interop File.** Please refer to [CDS-PATTERNS.md](references/CDS-PATTERNS.md) and [TROUBLESHOOTING.md](references/TROUBLESHOOTING.md) to diagnose the issue. Based on the issues identified, make the changes to the CDS file and regenerate the interop.

**If same error recurs after 2 fix attempts:** remove the cube view, state the problem, ask: *"I was unable to resolve this. Simplify the transformation or use different source entities?"*

Proceed directly to Step 5b.

---

## Step 5b — Authorization Management Service Base Policy [MANDATORY GATE]

Run immediately after `generate-interop` succeeds. No user prompt needed — proceed automatically.

### Step 5b-i — Fetch Candidates

```bash
jl data-product fetch-ams-candidates \
  --dpd <output_interop_path> \
  --policy-file <file_name_ams_policy>
```

Use `file_name_ams_policy` stored in Step 2. See [TOOLING-CLI.md](references/TOOLING-CLI.md) for full reference.

**On success:**

- If `recommended`, `alsoRecommended`, and `available` are all empty: state *"No authorization-eligible fields found — AMS policy skipped."* Proceed to Step 6.
- Otherwise: present the results as follows.

---

#### Display format — `source: "input-policy"`

Open with:
> **Authorization Policies in Authorization Management Service** - Title
> "Authorization Policies control who can access data in your data product. Based on your source data products, **N column(s)** were already exposed to authorization policies and have been carried forward:"

Display the `recommended` fields **grouped by source DP business name** (derive the business name from `sourceDP`, e.g. `sap.s4com:dataProduct:SalesOrder:v1` → "Sales Order", `sap.s4com:dataProduct:BillingDocument:v1` → "Billing Document"). Within each group, list each field using a **continuous number** (never reset per group) using the `label` (or `field` if label is absent). Ensure that each field is displayed on a **separate line as part of a numbered list**. If two fields share the same label, disambiguate by appending the field name in parentheses:

**Rendering Note:** Use escaped numbering (1\., 2\.) to maintain continuous count across groups. Place a blank line between each item to ensure each field renders on its own separate line.

```
**<Source DP Business Name>**

1. <label or field>
2. <label or field>

**<Source DP Business Name>**

3. <label or field> (shared with <Other DP Name> — attributed once above)
```

Numbering is continuous across all groups — `recommended` starts at 1, `alsoRecommended` continues from where `recommended` left off. This lets users select by number without ambiguity (e.g. "use 1, 3, 7").

If a field from one source DP duplicates a field already listed under another source DP, show it with a note: *(shared with \<Other DP Name\> — attributed once above)*.

If a source DP's policy fields were not projected into the cube, add a note below that group:
> Note: `<FieldName>` is in the \<Source DP Name\> policy but was not projected into the cube, so it cannot be carried forward.

If `alsoRecommended` is non-empty, follow with:
> "I'm also recommending **N additional column(s)**:"

Display `alsoRecommended` in the same grouped format.

Then always close with:
> *"Should I expose these? Or do you have other columns in mind? There are also **N additional columns** available that can be part of the AMS policy — would you like to see those?"*

Where N = count of dimension-only fields in `available` (exclude any field annotated with `@Aggregation.default` — measures are not meaningful AMS candidates).

---

#### Display format — `source: "derived-dp"`

Open with:
> "No existing Authorization Management Service policy was found in your source data products. Based on your cube, I'm recommending the following dimension fields for authorization:"

Display `recommended` grouped by `outputObject` (same bullet format as above).

Ask:
> *"Should I expose these for authorization? Or do you have other columns in mind?"*

---

#### "Show all columns" response

If the user asks to see all columns or asks what else is available:

State:
> *"Here are all the columns available across your output objects. Let me know which you'd like to expose to authorization policies (e.g. `A1` or `all from A`):"*

Combine ALL candidates (`recommended` + `alsoRecommended` + `available`) into one flat list — **`recommended` fields MUST be included here even if already shown above**. Then **exclude measure fields** (any field annotated with `@Aggregation.default` — SUM, COUNT, NOP — is not a meaningful AMS candidate and must not appear), then group the remaining dimension fields by `outputObject`. Assign a letter prefix (A, B, C…) to each group in the order they appear. Number fields within each group starting at 1. Use business labels (not technical field names) in the list. **Ensure that the list follows the below given format**:

```
**A. <Output Object Business Name>**

 1. <label>
 2. <label>

**B. <Output Object Business Name>**

 1. <label>
 2. <label>

**C. <Output Object Business Name>**

 1. <label>
```

Accept any of these selection formats (alone or comma-separated):
- `A1` — field 1 from group A
- `all from B` — all fields in group B
- `all` — every field across all groups
- `A1, A3, all from B` — mix

---

**[GATE] Wait for explicit selection. Resolve the selection to a flat list of field names. Store as `ams_approved_fields`.**

### Step 5b-ii — Inject Policy

```bash
jl data-product inject-ams-policy \
  --dpd <output_interop_path> \
  --fields '<ams_approved_fields as JSON array>'
```

**On success:** state *"AMS policy injected."* Proceed to Step 6.

**On error:** show error verbatim. Ask: *"Retry with a different field selection?"*
- Yes: return to Step 5b-i display (re-use already-fetched candidates, do not re-call `fetch-ams-candidates`).
- No: state *"AMS policy skipped."* Proceed to Step 6.

---

## Step 6 - Setup of Solution [MANDATORY GATE]

1. **External skill (preferred):** Call the `setup-solution` skill to create the required solution folder structure and files.

### Self-Check (run internally — do not show to user)

Verify: (a) DP folder exists inside `assets/` in filesystem, (b) `asset.yaml` is present inside `assets/<folder_name>/`.

State "Solution structure verified." on pass. On failure: state what is wrong and fix it.

---

## Step 7 - Iterative Refinement Loop [MANDATORY GATE]

Ask: *"Would you like to preview the data, make changes, or is it ready to approve?"*

### SparkMV Gate [check before every CDS change]

**Category 1 — Hard failures (do not proceed):** `current_date`, `current_timestamp`, `now`, `rand`, `uuid`, `unix_timestamp` without args. If change uses any: *"This change uses `<function>` which will cause data product creation to fail. Use a field from the source entity instead."* Do not apply.

**Category 2 — Performance degradation (gate required):** `DISTINCT`, subqueries (`EXISTS`, `NOT EXISTS`, FROM subquery), window functions, `HAVING` clause. If change uses any: *"This change will cause significantly slower data updates. Proceed, or use an alternative?"* **[GATE] Wait for confirmation.** If user declines: propose an incremental-compatible alternative (for `HAVING`: move a row condition to `WHERE`, or apply an aggregate condition downstream instead of in the cube). If none exists: *"No incremental alternative — this will always do a full recompute. Proceed anyway?"* **[GATE]**

### On CDS change request (filter, join, new field, transformation)

1. If change involves entities/fields not yet explored, re-enter the Step 3 exploration sequence first.
2. State in one sentence what changes and why.
3. Apply change — modify existing cube in-place, or append new cube only if user explicitly asked for a separate output port.
4. Write updated cube to `file_name_agg_cds` — modify only the transformer view; never touch entity definitions above it.
5. Re-run Step 4 self-check internally.
6. Run `jl data-product generate-interop --modified-cds <file_name_agg_cds> --agg-csn <file_name_agg_csn>`. Store updated `output_interop_path`. Do not ask the user before calling this — proceed directly. If `ams_approved_fields` is in context, re-run Step 5b in full (fetch-ams-candidates → present updated recommendations → wait for re-approval → inject) — the DPD has changed and the previous field selection may be stale. Clear `ams_approved_fields` from context before re-entering Step 5b so the user is prompted for a fresh selection.
7. Check that `description` and `shortDescription` in `.ddp_metadata.json` still accurately describe what the cube now does. If either has drifted, show current vs. proposed for the changed field(s) and ask *"Update the description to match?"* **[GATE - FAST-TRACK EXEMPT]** — on yes, edit only the drifted field(s) and re-run `generate-interop` once more (do not re-run this check on that regeneration). If both still fit, say nothing.
8. State: "Data product definition updated. Please review." Ask: *"Does this look right, or would you like further changes?"*

### On metadata change (title, description, shortDescription)

Follow the title/description revision procedure in `references/revisions.md`.

### On name change

Follow the Name Change rule above, then return to Step 7.

### Exit only when

User uses an unambiguous approval phrase: "looks good", "approve", "approved", "done", "ship it", or equivalent affirmative. Do not treat "ok", "fine", "sure", or silence as approval.

Once approved: proceed to Step 7b.

## Step 7b — Data Preview [MANDATORY GATE]

Ask the user if they would like to preview the data

You **must** not read the DPD Interop or CDS Files directly as this will use up the context

Execute the following Node Script to retrieve the Target and Transformation sections of the DPD.

Set $DPD_FILE to the path of the .dpd file found in the asset folder

```bash
node -e "const d=JSON.parse(require('node:fs').readFileSync('$DPD_FILE','utf8')); console.log(JSON.stringify({target:d.definition.target,transformation:d.definition.transformation},null,2))"
```

Analyze the retrieved sections and generate **only 5** rows of realistic mock preview data

Display the table in the chat for the user. Fields are ALWAYS columns (headers). Records are ALWAYS rows. Never transpose.

After user approval: *"Data product has been created. Use the deploy option in Joule Studio to deploy."*
