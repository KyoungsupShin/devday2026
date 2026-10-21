# HANA CSV snapshots

These CSV files are the fixed, read-only ERP-style input for the F&B A2A
notebook Tools. The Tools never connect to SAP HANA and never modify these
files. Every included row is a local snapshot record.

The 39 CSV files are grouped by responsibility rather than execution order:

- **Assets and operations:** `equipment_master`, `equipment_bom`,
  `maintenance_work_order`, `production_plan`, `production_evidence`,
  `process_evidence`, `quality_evidence`, and `quality_release_status`.
- **Materials and procurement:** `material_mdm`, `material_stock`,
  `material_requirement`, `material_planning_parameter`,
  `material_intake_request`, `material_purchase_budget`,
  `open_purchase_schedule`, `purchase_source`, `purchase_quote`,
  `purchase_requisition`, and `supplier_master`. Purchase-source lead times and
  prices are historical references, not current quotes or contracts.
- **Finance, approval, and ERP change:** `opex_budget`, `cost_center_master`,
  `cost_center_change_request`, `budget_commitment`,
  `budget_transfer_request`, `approval_matrix`, `bom_change_request`,
  `erp_change_request`, and `erp_data_mapping`.
- **Business planning and profitability:** `business_context`, `product_master`,
  `product_bom`, `sales_forecast`, `exchange_rate_scenario`,
  `material_price_snapshot`, and `product_cost_assumption`.
- **Assurance and supporting teams:** `ehs_evidence`, `hr_workforce_evidence`,
  `general_affairs_evidence`, and `rnd_evidence`.

To use an approved HANA extract, replace file contents while preserving headers;
the Tool reports the file path and the `hana_csv_snapshot` source boundary.

The profitability calculation combines these four cost inputs with
the BOM and sales plan. It is read-only and does not represent actual FX, COGS,
BEP, profitability, approval, or operational decision data.
