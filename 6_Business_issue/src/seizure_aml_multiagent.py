"""Safe, observable mock of a financial seizure-and-AML multi-agent workflow.

The module deliberately works only with synthetic local fixtures.  It demonstrates
parallel evidence collection, graph-derived signals, dynamic AML delegation and
replanning.  It never establishes legal validity, freezes assets, files an AML
report, or modifies an external financial system.
"""
from __future__ import annotations

import importlib.util
import json
import re
from html import escape
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from business_issue import MODULE_ROOT, _load_harness, route_request

DEFAULT_CASE_PATH = MODULE_ROOT / "fixtures" / "seizure_aml_case.json"


def load_seizure_aml_case(path: Path | str = DEFAULT_CASE_PATH) -> dict[str, Any]:
    """Load only the synthetic financial-case fixture used in this hands-on."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _document_agent(case: dict[str, Any]) -> dict[str, Any]:
    """Extract a narrow fact packet from mock OCR text; no legal conclusion."""
    document_path = MODULE_ROOT / "fixtures" / case["document_file"]
    text = document_path.read_text(encoding="utf-8")

    def extract(pattern: str) -> str | None:
        match = re.search(pattern, text)
        return match.group(1).strip() if match else None

    account_scope = extract(r"압류 대상 계좌:\s*(.+)")
    annex_status = extract(r"첨부 별지:\s*(.+)")
    return {
        "agent": "document",
        "document_reference": case["document_file"],
        "case_number": extract(r"사건번호:\s*(.+)"),
        "customer_id": extract(r"채무자 고객 식별번호:\s*(.+)"),
        "claimed_amount_krw": int((extract(r"압류 청구금액:\s*KRW\s*([0-9,]+)") or "0").replace(",", "")),
        "effective_date": extract(r"발효일:\s*(.+)"),
        "account_scope_text": account_scope,
        "annex_missing": annex_status == "미첨부",
        "limitation": "Mock OCR extraction only. Legal validity, authority and scope must be verified by an authorized reviewer.",
    }


def _kyc_agent(case: dict[str, Any]) -> dict[str, Any]:
    """Return a read-only KYC evidence packet without exposing real personal data."""
    kyc = case["kyc"]
    return {
        "agent": "kyc",
        "customer_id": case["customer"]["customer_id"],
        "identity_status": kyc["identity_status"],
        "ubo_status": kyc["ultimate_beneficial_owner_status"],
        "sanctions_screening": kyc["sanctions_screening"],
        "pep_screening": kyc["pep_screening"],
        "last_review_date": kyc["last_review_date"],
        "limitation": "KYC snapshot is point-in-time evidence and is not an onboarding or sanctions decision.",
    }


def _ledger_agent(case: dict[str, Any]) -> dict[str, Any]:
    """Collect accounts and ledger rows as a read-only evidence packet."""
    accounts = case["accounts"]
    return {
        "agent": "ledger",
        "customer_id": case["customer"]["customer_id"],
        "accounts": accounts,
        "transactions": case["ledger"],
        "available_balance_krw": sum(account["available_balance_krw"] for account in accounts),
        "limitation": "Ledger snapshot excludes pending, blocked and off-platform balances.",
    }


def _compliance_agent(case: dict[str, Any]) -> dict[str, Any]:
    """Return policy controls, never a legal conclusion or an execution instruction."""
    return {
        "agent": "compliance",
        "controls": [
            "Confirm issuing authority, effective date and complete asset scope before any restriction.",
            "Preserve source references and reviewer rationale for every material conclusion.",
            "Escalate unusual transaction patterns to AML review; do not label activity suspicious without review.",
        ],
        "human_approval_required_for_asset_restriction": case["policy"]["human_approval_required_for_asset_restriction"],
        "limitation": "This control packet is not legal advice and does not determine enforceability.",
    }


def _graph_agent(ledger: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    """Create a compact transaction graph and identify rapid pass-through candidates."""
    account_ids = {account["account_id"] for account in ledger["accounts"]}
    transactions = ledger["transactions"]
    edges = [
        {
            "from": transaction["from_account"],
            "to": transaction["to_account"],
            "amount_krw": transaction["amount_krw"],
            "transaction_id": transaction["transaction_id"],
        }
        for transaction in transactions
    ]
    nodes = sorted({edge["from"] for edge in edges} | {edge["to"] for edge in edges})
    window_minutes = case["policy"]["rapid_pass_through_window_minutes"]
    rapid_events = []
    inbound = [transaction for transaction in transactions if transaction["to_account"] in account_ids]
    outbound = [transaction for transaction in transactions if transaction["from_account"] in account_ids]
    for received in inbound:
        received_at = datetime.fromisoformat(received["timestamp"])
        for sent in outbound:
            sent_at = datetime.fromisoformat(sent["timestamp"])
            elapsed_minutes = (sent_at - received_at).total_seconds() / 60
            if 0 <= elapsed_minutes <= window_minutes and sent["amount_krw"] >= received["amount_krw"] * 0.9:
                rapid_events.append(
                    {
                        "inbound_transaction": received["transaction_id"],
                        "outbound_transaction": sent["transaction_id"],
                        "elapsed_minutes": round(elapsed_minutes),
                        "beneficiary": sent["to_account"],
                    }
                )
    return {
        "agent": "graph",
        "nodes": nodes,
        "edges": edges,
        "rapid_pass_through_events": rapid_events,
        "limitation": "Graph relationships show transfer paths only; they do not prove ownership, intent or illegality.",
    }


def _aml_agent(graph: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    """Review rule-based AML signals after Coordinator dynamically delegates it."""
    rapid_events = graph["rapid_pass_through_events"]
    threshold = case["policy"]["rapid_pass_through_minimum_count"]
    flagged = len(rapid_events) >= threshold
    return {
        "agent": "aml",
        "assessment": "review_required" if flagged else "no_rule_trigger",
        "signals": ["repeated_rapid_pass_through"] if flagged else [],
        "supporting_events": rapid_events,
        "limitation": "Rule trigger is not a suspicious-activity determination and does not create a filing obligation.",
    }


def _run_timed(agent: str, function: Callable[..., dict[str, Any]], *args: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    started = perf_counter()
    packet = function(*args)
    duration_ms = max(1, round((perf_counter() - started) * 1000))
    event = {
        "agent": agent,
        "event": "completed",
        "status": "success",
        "duration_ms": duration_ms,
        "evidence_keys": sorted(packet.keys()),
    }
    return packet, event


def _report_agent(artifacts: dict[str, Any]) -> str:
    """Produce an evidence-linked report draft, explicitly reserving human decisions."""
    document = artifacts["document"]
    ledger = artifacts["ledger"]
    graph = artifacts["graph"]
    aml = artifacts.get("aml")
    aml_line = (
        f"AML rule review was delegated after {len(graph['rapid_pass_through_events'])} rapid pass-through candidate(s); status: {aml['assessment']}."
        if aml else "No AML rule review was delegated."
    )
    return (
        f"# 압류 검토 보고서 초안 — {document['case_number']}\n\n"
        f"- **문서 추출**: 고객 {document['customer_id']}, 청구금액 {document['claimed_amount_krw']:,}원, 발효일 {document['effective_date']}.\n"
        f"- **문서 한계**: 계좌 별지가 미첨부되어 계좌 범위가 완결되지 않았습니다.\n"
        f"- **KYC**: 신원·UBO 검증 및 제재/PEP 스크리닝은 fixture 기준 clear입니다.\n"
        f"- **원장**: 조회된 가용잔액은 {ledger['available_balance_krw']:,}원입니다.\n"
        f"- **자금 흐름**: {aml_line}\n"
        "- **담당자 확인 필요**: 발령기관·효력·전체 계좌범위·적용 가능 자산을 법무/컴플라이언스가 확인해야 합니다.\n\n"
        "이 초안은 압류 집행, 자산 동결 또는 AML 신고 결정을 지시하지 않습니다. 승인된 담당자가 근거를 검토한 뒤 별도 권한 도구에서 처리해야 합니다."
    )


def integration_readiness() -> dict[str, bool]:
    """Report optional production-integration packages without loading external services."""
    return {
        package: importlib.util.find_spec(package) is not None
        for package in ("deepagents", "langgraph", "networkx", "pyvis")
    }


def run_seizure_aml_multiagent(case: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a deterministic, observable, read-only multi-agent demonstration."""
    case = case or load_seizure_aml_case()
    default_prompt, _, _ = _load_harness()
    trace: list[dict[str, Any]] = [
        {
            "agent": "coordinator",
            "event": "plan_created",
            "status": "success",
            "parallel_agents": ["document", "kyc", "ledger", "compliance"],
        }
    ]

    tasks = {
        "document": (_document_agent, case),
        "kyc": (_kyc_agent, case),
        "ledger": (_ledger_agent, case),
        "compliance": (_compliance_agent, case),
    }
    artifacts: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=len(tasks), thread_name_prefix="financial-agent") as executor:
        futures = {name: executor.submit(_run_timed, name, function, argument) for name, (function, argument) in tasks.items()}
        for name in tasks:
            packet, event = futures[name].result()
            artifacts[name] = packet
            trace.append(event)

    graph, graph_event = _run_timed("graph", _graph_agent, artifacts["ledger"], case)
    artifacts["graph"] = graph
    trace.append(graph_event)

    if artifacts["document"]["annex_missing"]:
        trace.append(
            {
                "agent": "coordinator",
                "event": "replanned",
                "status": "needs_human_review",
                "reason": "The account annex is missing; account mapping is evidence only until legal scope is confirmed.",
            }
        )
    if len(graph["rapid_pass_through_events"]) >= case["policy"]["rapid_pass_through_minimum_count"]:
        trace.append(
            {
                "agent": "coordinator",
                "event": "delegated",
                "status": "success",
                "delegate": "aml",
                "reason": "Repeated rapid pass-through pattern reached the configured review threshold.",
            }
        )
        aml, aml_event = _run_timed("aml", _aml_agent, graph, case)
        artifacts["aml"] = aml
        trace.append(aml_event)

    report = _report_agent(artifacts)
    trace.append({
        "agent": "report",
        "event": "draft_generated",
        "status": "success",
        "evidence_agents": sorted(artifacts.keys()),
    })
    return {
        "case_id": case["case_id"],
        "route": route_request(case["request"]),
        "deep_orchestrator_prompt_loaded": bool(default_prompt("deep_orchestrator")),
        "artifacts": artifacts,
        "trace": trace,
        "report_draft": report,
        "action": "legal_and_compliance_approval_required",
        "asset_restriction_performed": False,
        "aml_report_filed": False,
    }


def pyvis_html(graph: dict[str, Any]) -> str | None:
    """Return optional inline PyVis HTML; no file is written and no network is called."""
    if importlib.util.find_spec("pyvis") is None:
        return None
    from pyvis.network import Network

    network = Network(height="420px", width="100%", directed=True, notebook=False)
    for node in graph["nodes"]:
        color = "#d32f2f" if node.startswith("DEMO-AC") else "#1976d2"
        network.add_node(node, label=node, color=color)
    for edge in graph["edges"]:
        network.add_edge(edge["from"], edge["to"], label=f"{edge['amount_krw']:,} KRW")
    return network.generate_html(notebook=False)


def _graph_html_for_ui(graph: dict[str, Any]) -> str:
    """Return a PyVis graph when available, otherwise a local read-only graph summary."""
    interactive = pyvis_html(graph)
    if interactive is not None:
        return interactive
    edges = "".join(
        f"<li><code>{escape(edge['from'])}</code> → <code>{escape(edge['to'])}</code> "
        f"({edge['amount_krw']:,} KRW)</li>"
        for edge in graph["edges"]
    )
    return (
        "<div style='padding:12px;border:1px solid #d0d7de;border-radius:8px'>"
        "<strong>자금 흐름 그래프 요약</strong>"
        "<p>PyVis를 설치하면 이 위치에 인터랙티브 그래프가 표시됩니다.</p>"
        f"<ul>{edges}</ul></div>"
    )


def _ui_evidence_summary(artifacts: dict[str, Any]) -> dict[str, Any]:
    """Limit the UI evidence panel to decision-relevant, non-raw fields."""
    document = artifacts["document"]
    ledger = artifacts["ledger"]
    graph = artifacts["graph"]
    summary: dict[str, Any] = {
        "document": {
            "case_number": document["case_number"],
            "customer_id": document["customer_id"],
            "claimed_amount_krw": document["claimed_amount_krw"],
            "annex_missing": document["annex_missing"],
        },
        "kyc": {
            key: artifacts["kyc"][key]
            for key in ("identity_status", "ubo_status", "sanctions_screening", "pep_screening")
        },
        "ledger": {
            "available_balance_krw": ledger["available_balance_krw"],
            "account_count": len(ledger["accounts"]),
            "transaction_count": len(ledger["transactions"]),
        },
        "graph": {
            "node_count": len(graph["nodes"]),
            "edge_count": len(graph["edges"]),
            "rapid_pass_through_candidates": len(graph["rapid_pass_through_events"]),
        },
    }
    if "aml" in artifacts:
        summary["aml"] = {
            "assessment": artifacts["aml"]["assessment"],
            "signals": artifacts["aml"]["signals"],
        }
    return summary


def build_financial_multiagent_ui():
    """Build a local Jupyter Gradio UI for the synthetic multi-agent demo.

    The callback streams trace rows as presentation events. It is deliberately
    read-only: neither user text nor generated results can initiate an asset
    restriction, report filing, or external-system call.
    """
    try:
        import gradio as gr
    except ImportError as error:
        raise RuntimeError("Gradio가 없습니다. requirements.txt를 설치하세요.") from error

    initial_case = load_seizure_aml_case()

    def run_from_ui(request: str):
        case = load_seizure_aml_case()
        if request.strip():
            case["request"] = request.strip()
        result = run_seizure_aml_multiagent(case)
        shown_trace: list[dict[str, Any]] = []
        evidence = _ui_evidence_summary(result["artifacts"])
        controls = {
            "approval_state": result["action"],
            "asset_restriction_performed": result["asset_restriction_performed"],
            "aml_report_filed": result["aml_report_filed"],
        }
        for event in result["trace"]:
            shown_trace.append(event)
            status = f"### {event['agent']} · {event['event']}\n상태: `{event['status']}`"
            yield (
                status,
                shown_trace,
                evidence,
                _graph_html_for_ui(result["artifacts"]["graph"]),
                result["report_draft"],
                controls,
            )

    with gr.Blocks(title="Financial Multi-Agent Harness") as app:
        gr.Markdown(
            "# 금융 압류·AML Multi-Agent Harness\n"
            "합성 데이터만 사용하는 읽기 전용 실습입니다. 문서 적법성, 자산 제한, AML 신고는 "
            "자동으로 결정하거나 실행하지 않습니다."
        )
        request = gr.Textbox(
            label="업무 요청",
            value=initial_case["request"],
            lines=3,
        )
        run = gr.Button("Multi-Agent 분석 실행", variant="primary")
        with gr.Row():
            live_status = gr.Markdown("실행 대기 중")
            approval = gr.JSON(label="승인·실행 통제")
        with gr.Row():
            trace = gr.JSON(label="Agent 실행 Trace (병렬·재계획·위임)")
            evidence = gr.JSON(label="의사결정 근거 요약")
        graph = gr.HTML(label="자금 흐름 그래프")
        report = gr.Markdown("보고서 초안은 실행 후 표시됩니다.")
        gr.Markdown(
            "**안전 경계:** 이 UI는 mock fixture와 로컬 계산만 사용합니다. `승인·실행 통제`가 "
            "승인 필요 상태인 동안 자산 동결·계정 변경·대외 신고는 수행되지 않습니다."
        )
        run.click(
            run_from_ui,
            inputs=request,
            outputs=[live_status, trace, evidence, graph, report, approval],
        )
    return app
