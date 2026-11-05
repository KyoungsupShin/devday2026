# Step 3 — Edge Cases: Cross-DP References & Enrichments

### 3a. Detect Cross-DP References [GATE]

*(Run only if schema reveals unresolved FK signals. Skip to 3b if none.)*

Scan `file_name_agg_cds` for cross-DP FK signals from three sources:

**Source A — Annotated FKs:** `@EntityRelationship.reference` blocks with `referencedEntityType`. Check if the short name (part after last `:`) appears in `csn-list-entities` output. If not → unresolved.

**Source B — Composite references:** `compositeReferences` arrays with `referencedEntityType`. Same check.

**Source C — Unannotated FK fields:** Fields that are likely FKs if ALL of:

- Plain scalar type (String, Integer — not Composition or Association)
- Name or label suggests a distinct business object (Cost Center, Supplier, Plant, Company Code)
- That object is not in `csn-list-entities` output
- Value is clearly a code/ID, not descriptive text

Do NOT flag: date fields, amount/quantity fields, free-text descriptions, status codes. Ignore namespaces ending in `.gfn`. Deduplicate by `referencedEntityType`.

Only surface entries where joining the external DP provides a clear, concrete benefit to the user's stated requirement — e.g. resolving a code to a readable label, adding a missing dimension.

**If zero qualifying entries: skip to 3b.**

If qualifying entries found:

> **These columns link to external data that could improve your analytics. I haven't fetched those schemas yet — would you like me to explore them so I can give a definitive answer on what they add?**
>
> | Column in your data | Links to            | Likely benefit      |
> | ------------------- | ------------------- | ------------------- |
> | `<field label>`   | `<business name>` | *[plain English]* |
>
> *Explore, skip, or keep it simple?*

**[GATE - FAST-TRACK EXEMPT] Wait for answer even in Fast Track mode.**

- **Explore:** call `dpca-mcp-server__ums_search_data_products` for each entry. If zero results: *"No matching DP found for [entry] — skip it or try a different search term?"* **[GATE]**. If multiple: show as numbered cards, ask which to use **[GATE]**. Then re-run Steps 2a–3 with expanded `--data-products` (add `{ordId, tenantId}` for each new DP). Update `source_dp_fqdns` in `.ddp_metadata.json`. After fetching, confirm what was found and ask which to include.
- **Skip / keep it simple:** proceed to 3b.

### 3b. Suggest Enrichments [GATE]

*(Run only if associations point at entities already in `csn-list-entities` output **and** those associations provide a clear quality-of-life improvement for the stated requirement. Skip to 3c if none — do not manufacture suggestions.)*

Only suggest if it resolves a code to a readable label, adds a dimension the requirement implies but didn't name, or enables a meaningful aggregation otherwise impossible. If associations exist but none meet this bar, skip silently.

Use these exact commands — do not guess flag names:

**ALWAYS look up the exact flags in [TOOLING-CLI.md](references/TOOLING-CLI.md) before calling any `csn-*` command. Never infer or guess flag names — only use what is documented there.**

If qualifying associations exist:

> **Your schema already includes related data you could add:**
>
> - **`<Business name>`** — *[one line: what it concretely adds]*
>
> *Include any, or keep it simple?*

**[GATE - FAST-TRACK EXEMPT] Wait for answer before writing the view, even in Fast Track mode.**
