# HANA CSV snapshots

These CSV files are the fixed, read-only ERP-style input for the F&B A2A
notebook Tools. The Tools never connect to SAP HANA and never modify these
files. Every included row is a local snapshot record.

- equipment_master.csv: equipment master-data snapshot
- maintenance_work_order.csv: maintenance work-order snapshot
- equipment_bom.csv: equipment-to-material relationship snapshot
- material_mdm.csv: material master-data snapshot
- material_stock.csv: material stock snapshot
- purchase_source.csv: purchase source-list snapshot; its lead time and price
  are historical reference values, not a current quote or contract.
- purchase_quote.csv: supplier quote snapshot for the request.
- supplier_master.csv: supplier qualification and supply-risk snapshot.
- material_planning_parameter.csv: planning and replenishment-parameter snapshot.
- opex_budget.csv: annual OPEX snapshot, including the recorded shortfall.
- cost_center_master.csv: Cost Center master-data snapshot.
- approval_matrix.csv: approval-policy snapshot for the material.
- budget_transfer_request.csv: budget-transfer request status snapshot.
- erp_change_request.csv: ERP change-request status snapshot.
- product_bom.csv: product-to-component relationship and quantity basis for the business case.
- sales_forecast.csv: monthly product volume and net-sales plan used for the business case.
- exchange_rate_scenario.csv: monthly FX inputs for the favorable, baseline, and downside scenarios.
- material_price_snapshot.csv: monthly material-price inputs for those scenarios.
- product_cost_assumption.csv: monthly non-FX variable-cost and fixed-manufacturing-cost assumptions.
- erp_data_mapping.csv: required data fields and validation-scope snapshot for ERP readiness.
- ehs_evidence.csv: worker-safety, environmental, chemical-handling, and work-permit snapshot.
- hr_workforce_evidence.csv: workforce, qualification, learning, and attendance-control snapshot.
- general_affairs_evidence.csv: site-service, non-production asset, and access-support snapshot.
- process_evidence.csv: process-parameter, performance, and change-validation snapshot.
- rnd_evidence.csv: product development, specification, scale-up, and technology-transfer snapshot.
- production_evidence.csv: production-execution, line-operation, and traceability snapshot.
- quality_evidence.csv: quality-system, testing, and release-readiness snapshot.

To use an approved HANA extract, replace file contents while preserving headers;
the Tool reports the file path and the hana_csv_snapshot source boundary.

The profitability calculation combines these four cost inputs with
the BOM and sales plan. It is read-only and does not represent actual FX, COGS,
BEP, profitability, approval, or operational decision data.
