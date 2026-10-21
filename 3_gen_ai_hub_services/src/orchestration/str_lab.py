"""Synthetic STR-draft case used by the orchestration learning lab.

The sample is intentionally fictional and contains no real customer or account
data. It produces an internal-review prompt, never a filing-ready report.
"""
from __future__ import annotations

from datetime import datetime
import json
from typing import Any, Mapping


SYNTHETIC_STR_CASE: dict[str, Any] = {
    "case_id": "STR-TRAIN-2026-001",
    "customer": {
        "customer_reference": "CUST-0427",
        "risk_rating": "medium",
        "profile": "국내 온라인 유통업 개인사업자 (교육용 가명)",
    },
    "review_period": "2026-09-14 ~ 2026-09-16",
    "transactions": [
        {
            "timestamp": "2026-09-14T09:12:00+09:00",
            "type": "입금",
            "amount_krw": 9800000,
            "counterparty": "외부계좌-***-1842",
            "note": "평소 거래 규모보다 큰 일회성 입금",
        },
        {
            "timestamp": "2026-09-14T09:19:00+09:00",
            "type": "출금",
            "amount_krw": 3100000,
            "counterparty": "수취계좌-***-7711",
            "note": "입금 후 7분 이내 분할 이체",
        },
        {
            "timestamp": "2026-09-14T09:23:00+09:00",
            "type": "출금",
            "amount_krw": 3200000,
            "counterparty": "수취계좌-***-5520",
            "note": "입금 후 11분 이내 분할 이체",
        },
        {
            "timestamp": "2026-09-14T09:28:00+09:00",
            "type": "출금",
            "amount_krw": 3300000,
            "counterparty": "수취계좌-***-9034",
            "note": "입금 후 16분 이내 잔액 대부분 이체",
        },
    ],
    "observed_risk_indicators": [
        "단기간 고액 입금 후 다수 계좌로 분할 이체",
        "최근 90일 평균 일일 입출금액보다 약 8배 큰 거래 규모",
        "거래 목적 및 상대방 관계를 뒷받침하는 증빙이 현재 사례 데이터에 없음",
    ],
    "known_limitations": [
        "본 사례의 계좌·고객·거래처 식별자는 모두 가명 또는 마스킹 값임",
        "제공된 사실만 사용하며 범죄 사실·자금 출처·의도를 단정할 수 없음",
    ],
}


# Raw, masked result sets shown in the UI before an Orchestration turns them into a draft.
SYNTHETIC_STR_DATABASE_RESULT: dict[str, Any] = {
    "case_id": "STR-TRAIN-2026-001",
    "query_timestamp": "2026-09-16T10:00:00+09:00",
    "customer_master": [
        {
            "customer_id": "CUST-0427",
            "customer_type": "INDIVIDUAL_BUSINESS",
            "customer_name_masked": "김*준",
            "business_type": "온라인 유통업",
            "risk_grade": "MEDIUM",
            "onboarded_at": "2023-04-18",
            "kyc_last_verified_at": "2026-03-02",
        }
    ],
    "account_master": [
        {
            "account_no_masked": "110-***-0427",
            "customer_id": "CUST-0427",
            "account_status": "ACTIVE",
            "opened_at": "2023-04-18",
            "currency": "KRW",
        }
    ],
    "ledger_transactions": [
        {
            "transaction_id": "TXN-20260914-000812",
            "transaction_at": "2026-09-14T09:12:00+09:00",
            "account_no_masked": "110-***-0427",
            "direction": "CREDIT",
            "amount_krw": 9800000,
            "balance_after_krw": 9834500,
            "counterparty_account_masked": "***-***-1842",
            "counterparty_bank_code": "004",
            "transaction_channel": "MOBILE",
        },
        {
            "transaction_id": "TXN-20260914-000847",
            "transaction_at": "2026-09-14T09:19:00+09:00",
            "account_no_masked": "110-***-0427",
            "direction": "DEBIT",
            "amount_krw": 3100000,
            "balance_after_krw": 6734500,
            "counterparty_account_masked": "***-***-7711",
            "counterparty_bank_code": "020",
            "transaction_channel": "MOBILE",
        },
        {
            "transaction_id": "TXN-20260914-000861",
            "transaction_at": "2026-09-14T09:23:00+09:00",
            "account_no_masked": "110-***-0427",
            "direction": "DEBIT",
            "amount_krw": 3200000,
            "balance_after_krw": 3534500,
            "counterparty_account_masked": "***-***-5520",
            "counterparty_bank_code": "081",
            "transaction_channel": "MOBILE",
        },
        {
            "transaction_id": "TXN-20260914-000889",
            "transaction_at": "2026-09-14T09:28:00+09:00",
            "account_no_masked": "110-***-0427",
            "direction": "DEBIT",
            "amount_krw": 3300000,
            "balance_after_krw": 234500,
            "counterparty_account_masked": "***-***-9034",
            "counterparty_bank_code": "088",
            "transaction_channel": "MOBILE",
        },
    ],
    "customer_transaction_summary": [
        {
            "customer_id": "CUST-0427",
            "period_days": 90,
            "avg_daily_credit_krw": 1210000,
            "avg_daily_debit_krw": 1180000,
            "max_single_credit_krw": 2400000,
            "transaction_count": 86,
        }
    ],
    "supporting_documents": [],
    "data_limitations": [
        "모든 식별자는 교육용 가명 또는 마스킹 값입니다.",
        "상대방 실소유자 정보와 거래 목적 증빙은 본 조회 결과에 포함되지 않습니다.",
    ],
}


def _validated_ledger_transactions(result: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    case_id = result.get("case_id")
    transactions = result.get("ledger_transactions")
    if not isinstance(case_id, str) or not case_id.strip():
        raise ValueError("DB 조회 결과에는 case_id가 필요합니다.")
    if not isinstance(transactions, list) or not transactions:
        raise ValueError("DB 조회 결과에는 한 건 이상의 ledger_transactions가 필요합니다.")
    required = {"transaction_at", "direction", "amount_krw", "counterparty_account_masked"}
    if any(not isinstance(item, Mapping) or not required.issubset(item) for item in transactions):
        raise ValueError("각 원장 거래에는 시간, 방향, 금액, 마스킹 상대 계좌가 필요합니다.")
    if any(item["direction"] not in {"CREDIT", "DEBIT"} for item in transactions):
        raise ValueError("원장 거래 direction은 CREDIT 또는 DEBIT이어야 합니다.")
    if any(not isinstance(item["amount_krw"], (int, float)) or isinstance(item["amount_krw"], bool) for item in transactions):
        raise ValueError("원장 거래 amount_krw는 숫자여야 합니다.")
    try:
        [datetime.fromisoformat(str(item["transaction_at"])) for item in transactions]
    except ValueError as error:
        raise ValueError("원장 거래 transaction_at은 ISO 날짜/시간이어야 합니다.") from error
    return transactions


def build_str_database_input(result: Mapping[str, Any]) -> str:
    """Validate and serialize masked database result sets for an Orchestration."""
    _validated_ledger_transactions(result)
    return json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)


def summarize_str_database_result(result: Mapping[str, Any]) -> dict[str, Any]:
    """Return a fact-only summary of the raw ledger result for review."""
    transactions = _validated_ledger_transactions(result)
    credits = [item for item in transactions if item["direction"] == "CREDIT"]
    debits = [item for item in transactions if item["direction"] == "DEBIT"]
    timestamps = [datetime.fromisoformat(str(item["transaction_at"])) for item in transactions]
    return {
        "case_id": result["case_id"],
        "ledger_transaction_count": len(transactions),
        "total_credit_krw": sum(item["amount_krw"] for item in credits),
        "total_debit_krw": sum(item["amount_krw"] for item in debits),
        "masked_debit_counterparty_count": len(
            {item["counterparty_account_masked"] for item in debits}
        ),
        "time_window_minutes": round(
            (max(timestamps) - min(timestamps)).total_seconds() / 60, 1
        ),
        "timeline": [
            f"{item['transaction_at']} | {item['direction']} | {item['amount_krw']:,} KRW | {item['counterparty_account_masked']}"
            for item in transactions
        ],
    }


def build_str_draft_request(case: Mapping[str, Any]) -> str:
    """Return a fact-bound, human-review-only request for a saved orchestration."""
    case_id = case.get("case_id")
    transactions = case.get("transactions")
    indicators = case.get("observed_risk_indicators")
    limitations = case.get("known_limitations")
    if not isinstance(case_id, str) or not case_id.strip():
        raise ValueError("STR 사례에는 case_id가 필요합니다.")
    if not isinstance(transactions, list) or not transactions:
        raise ValueError("STR 사례에는 한 건 이상의 거래가 필요합니다.")
    if not isinstance(indicators, list) or not indicators:
        raise ValueError("STR 사례에는 관찰된 위험 징후가 필요합니다.")
    if not isinstance(limitations, list) or not limitations:
        raise ValueError("STR 사례에는 사실 판단의 한계가 필요합니다.")

    facts = json.dumps(case, ensure_ascii=False, indent=2, sort_keys=True)
    return f"""다음은 가명·마스킹된 교육용 거래 사례입니다. 내부 컴플라이언스 검토용 STR 초안만 작성하세요.

필수 원칙:
1. 제공된 사실과 관찰된 위험 징후만 사용하고, 범죄·자금 출처·의도를 단정하거나 새 사실을 만들지 마세요.
2. '확인된 거래 사실', '의심 사유', '추가 확인 필요 사항'을 구분하세요.
3. 계좌·고객 식별자는 제공된 마스킹 표기를 유지하세요.
4. 최종 결과의 첫 문장에 '자동 생성된 내부 검토용 초안이며, 신고 여부와 내용은 담당자가 검토·결정해야 합니다.'를 포함하세요.
5. 출력 구조는 사건 개요, 거래 사실, 의심 사유, 추가 확인 필요 사항, 담당자 검토 의견 순서로 작성하세요.

[사례 데이터]
{facts}
""".strip()
