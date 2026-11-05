# Revisions — User changes their mind at any point

Any field or decision can be revised at any time. Apply the path below and return to the step you were interrupted from.

### Change input DP (after selection in `intent-analysis`)

1. Re-run search — call `dpca-mcp-server__ums_search_data_products` with new terms, display results, and wait for confirmation **[GATE]**.
2. Update `source_dp_fqdns` array in `<session_folder>/work/.ddp_metadata.json` with the new versioned FQDN (`<id>.<minor>.<patch>`).
3. Re-run Steps 2–6.

### Change Technical Name
- **During Step 1a (before Step 1b):**
  If an asset folder was pre-created in `assets/<old_folder_name>` (e.g. from specification setup `mkdir -p`), delete it: `rm -rf "<working_directory>/assets/<old_folder_name>"`. Re-propose properties with the new name.
- **After Step 1b (session folder already populated):**
  Follow the Name Change rule below.

### Change Business Name / title (at any point)

1. Update `header.title` in `<session_folder>/work/.ddp_metadata.json`.
2. If Step 5 ran: re-run `jl data-product generate-interop`. *"Data product definition updated."*

### Change responsible (at any point)

Validate the new value matches: `^([a-z0-9]+):(vendor):([a-zA-Z0-9._\-]+)` — e.g. `customer:vendor:Customer`. Reject and ask for a valid value if it does not match.

1. Targeted edit to `header.responsible` in `<session_folder>/work/.ddp_metadata.json`.
2. If Step 5 ran: re-run `jl data-product generate-interop`. *"Data product definition updated."*

### Change shortDescription / description (at any point)

1. Targeted edit to `header.shortDescription` or `header.description` in `<session_folder>/work/.ddp_metadata.json`.
2. If Step 5 ran: re-run `jl data-product generate-interop`. *"Data product definition updated."*

### Change namespace (at any point after Step 1b)

1. Verify the new namespace conforms to the format `c.bdc.<base36>` (or authorized customer prefix).
2. Update `applicationNamespace` in both top-level `"applicationNamespace"` and nested `"header.applicationNamespace"` inside `<session_folder>/work/.ddp_metadata.json`.
3. If Step 5 ran: re-run `jl data-product generate-interop`. *"Data product definition updated with new namespace."*

### Add enrichment / change source DPs (after schema was fetched)

1. Call `dpca-mcp-server__ums_search_data_products` for the new DP.
2. Re-run `jl data-product fetch-and-prepare` with expanded `--data-products` (add `{ordId, tenantId}` for each new DP, using `id` and `tenant_uuid` from search result). This re-fetches, recompiles `transformation.cds`, and rebuilds `csn_graph.json` in one call.
3. Update `source_dp_fqdns` array in `<session_folder>/work/.ddp_metadata.json` — append the new versioned FQDN (`<id>.<minor>.<patch>` from version) to the array.
4. Re-run Steps 4–5b.

### Change filters / transformation (after view written)

Follow the refinement loop in Step 7.

---

## Rule: Name Change After Folder Created

Triggered when the user changes the Technical Name after Step 1b has run (i.e. the session folder already exists).

1. Compute new kebab-case folder name: insert a dash before each uppercase letter that follows a lowercase letter, lowercase everything, append `-data-product` (e.g. `SalesOrderStatus` → `sales-order-status-data-product`).
2. Check collision in `<working_directory>/assets/<new_folder_name>`.
3. Propose updated names to the user **[GATE]**.
4. Rename session folder inside `assets/`:
   ```bash
   mv "<working_directory>/assets/<old_folder_name>" "<working_directory>/assets/<new_folder_name>"
   ```
5. Rename specification folder if present:
   ```bash
   mv "<working_directory>/specification/<old_folder_name>" "<working_directory>/specification/<new_folder_name>"
   ```
6. Update `session_folder` in context to `<working_directory>/assets/<new_folder_name>`.
7. Update metadata fields in `<session_folder>/work/.ddp_metadata.json`:
   - `derived_dp_name` = `<new_technical_name>`
   - `header.name` = `<new_technical_name>`
   - `header.title` = `<new_title>`
8. Verify pre-flight criteria (Gate 1–4) still hold.
9. If Step 5 ran: re-run `jl data-product generate-interop`.
10. Return to the step that triggered this rule.
