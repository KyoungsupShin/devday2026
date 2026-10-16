"""CLI entry points for every read-only Business Issue core scenario."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "shared"), str(ROOT / "5_harness"), str(Path(__file__).resolve().parent / "src")]

from business_issue import solve_business_issue
from kyc_issue import solve_kyc_issue
from receivables_ra_issue import solve_receivables_ra_issue
from seizure_aml_multiagent import run_seizure_aml_multiagent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=["replenishment", "kyc", "receivables", "seizure-aml"])
    scenario = parser.parse_args().scenario
    functions = {
        "replenishment": solve_business_issue,
        "kyc": solve_kyc_issue,
        "receivables": solve_receivables_ra_issue,
        "seizure-aml": run_seizure_aml_multiagent,
    }
    print(json.dumps(functions[scenario](), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
