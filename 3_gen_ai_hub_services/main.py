"""CLI entry points for Orchestration, grounding, and SAP RPT core workflows."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.orchestration.lesson_support.config import load_settings
from src.grounding.lab_core import run_help_grounded_query, run_vector_grounded_query
from src.orchestration.lab_core import (
    run_orchestration,
)
from src.rpt_risk.lab_core import (
    list_saved_rpt_holdout_runs,
    load_saved_rpt_holdout_run,
    persist_rpt_holdout_snapshot,
    predict_saved_rpt_holdout_row,
    run_rpt_risk_evaluation,
)
from src.rpt_risk.lesson_support.config import load_settings as load_rpt_settings
from src.rpt_decision.lab_core import run_rpt_decision


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    orchestration = commands.add_parser("orchestration", help="01: run prompt templating")
    orchestration.add_argument("query")
    grounding = commands.add_parser("grounding", help="02: ask SAP Help grounding")
    grounding.add_argument("query")
    vector_grounding = commands.add_parser("grounding-vector", help="02: ask a Custom Repository")
    vector_grounding.add_argument("--repository-id", required=True)
    vector_grounding.add_argument("query")
    commands.add_parser("rpt-evaluate", help="03: evaluate the educational credit-risk dataset with SAP RPT")
    commands.add_parser("rpt-save-holdout", help="03: run and persist one holdout snapshot to BTP Object Storage and AI Core Artifact")
    commands.add_parser("rpt-list-holdout", help="03: list persisted RPT holdout artifacts")
    rpt_predict_saved = commands.add_parser("rpt-predict-saved", help="03: predict one row from a persisted holdout snapshot")
    rpt_predict_saved.add_argument("artifact_id")
    rpt_predict_saved.add_argument("record_id")
    rpt_decision = commands.add_parser("rpt-decision", help="04: call the read-only SAP RPT Decision API")
    rpt_decision.add_argument("state")
    args = parser.parse_args()
    settings = load_settings()

    if args.command == "orchestration":
        print(run_orchestration(args.query, settings))
    elif args.command == "grounding":
        print(run_help_grounded_query(args.query, settings))
    elif args.command == "grounding-vector":
        print(run_vector_grounded_query(args.query, settings, repository_id=args.repository_id))
    elif args.command == "rpt-evaluate":
        print(json.dumps(run_rpt_risk_evaluation(load_rpt_settings()), ensure_ascii=False, indent=2))
    elif args.command == "rpt-save-holdout":
        rpt_settings = load_rpt_settings()
        evaluation = run_rpt_risk_evaluation(rpt_settings)
        print(json.dumps(persist_rpt_holdout_snapshot(evaluation, rpt_settings), ensure_ascii=False, indent=2))
    elif args.command == "rpt-list-holdout":
        print(json.dumps(list_saved_rpt_holdout_runs(load_rpt_settings()), ensure_ascii=False, indent=2))
    elif args.command == "rpt-predict-saved":
        rpt_settings = load_rpt_settings()
        snapshot = load_saved_rpt_holdout_run(args.artifact_id, rpt_settings)
        print(json.dumps(
            predict_saved_rpt_holdout_row(snapshot, args.record_id, rpt_settings),
            ensure_ascii=False, indent=2,
        ))
    elif args.command == "rpt-decision":
        import os

        print(json.dumps(
            run_rpt_decision(args.state, os.getenv("SAP_RPT_API_KEY", "")), ensure_ascii=False, indent=2
        ))


if __name__ == "__main__":
    main()
