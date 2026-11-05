# Data Product Generation Guidelines

Technical constraints and patterns for building SAP Derived Data Products. Follow these throughout specification execution.

## Tech Stack

- SAP Data Product Store (DPS)
- CDS (Core Data Services) transformation views
- SAP Data Product Generation workflow (`data-product` skill)

## Scope

**Derived Data Products only** — builds analytical products from existing primary data products via CDS transformation. Does not create primary data products or replicate raw data.

## Behavior Rules and Key Constraints

- **Never reuse identifiers, names, or values verbatim from examples** in this file or the `data-product` skill.
- All file tool paths (`write_file`, `read_file`, `list_files`, `delete_file`) are relative to the solution root — never pass absolute paths to file tools.
- `pwd` is the only command that uses absolute paths, solely for resolving MCP tool arguments.
- Never ask for information already in context
- Respond with the minimum needed: [GATE] questions, tool errors, one-sentence step status. No narration.
- Never surface technical internals to the user — pipeline mechanics, MV/refresh modes, system annotations, internal column names, CDS rules. Apply them silently. Explain only if the user explicitly asks.
- Only run shell commands for CLI tool calls or to create/move files — never to display info
- Never run `ls`, `find`, or `pwd` to discover paths or verify folder existence — all paths are derived from `working_directory` and `session_folder` already in context.
- Never re-invoke this skill mid-run — if already executing, continue from the current step using context already in the conversation. Do not call Skill(data-product) again.
- Never overwrite the entire `transformation.cds` — always make surgical edits that target only the cube view section

## Hard Rules

- Each step executes **at most once** unless explicitly re-requested (except Step 7: iterative refinement allowed)
- **Never revert to a completed step**
- Be concise — lead with the result, no explanatory padding
- Check for validation rules
- **Only JL CLI** should be used to call the remote MCP Tools mentioned in the steps

## Workflow

The full data product creation follows the `data-product` skill (Steps 1a–7b). When invoked from `specification`, search and selection have already been completed during `intent-analysis` — then resume from Step 1a. Key integration points:

- **Step 1a** — Propose and approve properties (`name`, `title`, `shortDescription`, `description`)
- **Step 1b** — Run `init_session.js` to create session folder in `assets/<folder-name>/work`, compute Base36 namespace, and write `.ddp_metadata.json`
- **Step 2** — Fetch CSN, compile to CDS, and build the CSN graph in one call (`jl data-product fetch-and-prepare`)
- **Step 3** — Explore schema, detect enrichments, build analytical cube view
- **Step 4** — CDS self-check (slimmed pre-check + 3 correctness passes — silent; structural/syntax/SparkMV rules auto-enforced by the CLI at Step 5)
- **Step 5** — Generate interop definition (`jl data-product generate-interop`)
- **Step 6** — Setup solution: invoke `setup-solution` skill
- **Step 7** — Iterative refinement loop — exit only on explicit user approval
- **Step 7b** — Data preview (extract the DPD `target`/`transformation` sections and generate mock preview)

## Mandatory Gates (cannot skip)

| Gate | Step |
|------|------|
| Properties approval | 1a |
| Session folder + metadata | 1b |
| Input DP confirmation (CSN fetch) | 2a |
| CDS self-check | 4 |
| Interop definition created | 5 |
| Setup Solution | 6 |
| Refinement approval | 7 |
| Data preview | 7b |

## Terminology

- Use **"Objects"** (not "Artifacts", "Entities", or "Tables")
- Use **"Columns"** for Relational Dataset semantic usage; use **"Attributes"** for Dimension, Fact, Text, Hierarchy
- Use **"Business Name"** instead of "Title"; **"Technical Name"** instead of "Name"
- Use **"create"** (not "generate") when creating a data product or object
- Do not use emojis
