---
name: data-product
description: "Intent-based development asset. SAP data product generation skill. Activates for: generate data product, create data product, build data product, data product from entities, data product from SAP, derived data product, generate DPD interop, publish data product, activate data product, preview data product, agent to analyse data products, agent to explore data products, agent using data product, agent that queries data product, create agent for data product, agent answers questions about data product, data product consumption, consume data product, use data product, data product as data source. MANDATORY: Do NOT generate code, create asset folders, or run Step 1a until intent.md, product-requirements-document.md, and specification/ are generated and approved. When invoked from an end-user request, execute intent-analysis, write intent.md, and transition to product-requirements-document."
license: MIT
metadata:
  version: 1.0.0
  author: sap-joule-studio
---

# SAP Data Product Generation Skill

This skill participates in the Intent-Based Development (IBD) lifecycle across 4 mandatory phases:

## Lifecycle Phases & Execution Order

### Phase 1 — Intent Analysis (When invoked from user request)
- Read [intent-analysis](./references/intent-analysis.md).
- Run SAP Reference Business Architecture mapping and Data Product search.
- Select and confirm the source data product with the user.
- **MANDATORY**: Write `intent.md` directly at `<working_directory>/intent.md`. (NEVER create an `intent/` folder).
- **MANDATORY HARD STOP**: Ask user to proceed to PRD, then invoke the `product-requirements-document` skill.
- **STRICTLY FORBIDDEN**: Under NO circumstances should you propose properties (Step 1a) or execute code/folder creation in Phase 1.

### Phase 2 — PRD Generation (`product-requirements-document` skill)
- The `product-requirements-document` skill reads `intent.md` and generates `product-requirements-document.md`.
- Requires user confirmation before moving to specification.

### Phase 3 — Specification (`specification` skill)
- The `specification` skill reads `product-requirements-document.md` and generates the `specification/` folder containing `specification.md` and the per-asset spec checklist.
- Prepares the solution and signals execution via `execute specification/<asset-name>/specification.md`.

### Phase 4 — Execution (ONLY when invoked from `specification`)
- Read [execution](./references/execution.md).
- **PREREQUISITE GATE**: Verify `intent.md`, `product-requirements-document.md`, and `specification/` all exist.
- Read [setup-solution](./references/setup-solution.md) for solution registration rules.
- Execute Steps 0 through 7b to generate the data product asset in `assets/<asset-name>/`.
