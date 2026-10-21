"""Shared, labeled examples for the order-risk reranker demo.

These are educational examples, not production fraud, AML, or STR rules.
They are input fixtures only: the reranker still receives each case as raw text.
"""
from __future__ import annotations

from typing import Final


ORDER_RISK_DEMO_CASES: Final[tuple[dict[str, str], ...]] = (
    {
        "name": "정상 · 기본 주문",
        "case": "인증된 고객이 주문 간격 60초 이상을 지키며 1분에 1회 주문을 시도했다. 중복, 실패, 한도 초과는 없다.",
        "expected": "approve",
        "signal_group": "normal_flow",
    },
    {
        "name": "정상 · 안정적 반복 구매",
        "case": "기존 고객이 동일한 기기와 배송지에서 30초 이상 간격으로 1분에 3회 이하 주문했다. 결제수단과 수취인은 기존 이력과 같고 실패나 중복은 없다.",
        "expected": "approve",
        "signal_group": "normal_flow",
    },
    {
        "name": "관찰 · 빈번한 주문",
        "case": "인증된 고객이 1분 동안 5회 주문을 시도했다. 결제와 인증은 성공했지만 평소보다 주문 빈도가 높아 추가 확인이 필요하다.",
        "expected": "manual-review",
        "signal_group": "velocity",
    },
    {
        "name": "관찰 · 기기·배송지 연계",
        "case": "서로 다른 두 계정이 같은 기기와 배송지를 사용해 주문했다. 결제 실패나 자동화 정황은 아직 확인되지 않았다.",
        "expected": "manual-review",
        "signal_group": "account_device_delivery_linkage",
    },
    {
        "name": "관찰 · 결제수단 변경",
        "case": "인증된 고객이 주문 중 결제수단을 두 번 변경했고 결제 실패가 한 번 발생했다. 주문은 한 계정과 한 배송지에서 이루어졌다.",
        "expected": "manual-review",
        "signal_group": "payment_irregularity",
    },
    {
        "name": "관찰 · 수취인·연락처 변경",
        "case": "한 계정이 짧은 시간에 배송지는 유지한 채 수취인과 연락처를 여러 번 바꾸어 주문했다. 실패와 한도 초과는 확인되지 않았다.",
        "expected": "manual-review",
        "signal_group": "recipient_contact_anomaly",
    },
    {
        "name": "관찰 · 빈도·간격 불일치",
        "case": "주문 간격은 60초 이상이라고 기록됐지만 같은 1분에 수백 회 주문을 시도했다고 보고됐다. 인증과 결제 실패는 없다.",
        "expected": "manual-review",
        "signal_group": "behavior_inconsistency",
    },
    {
        "name": "고위험 · 한도 회피",
        "case": "한 계정이 1분 동안 7회 주문을 시도했다. 동일 상품을 여러 건으로 나누어 구매했고 상품별 구매 한도에 가까운 수량이 누적됐다.",
        "expected": "decline",
        "signal_group": "limit_evasion",
    },
    {
        "name": "고위험 · 다계정 연계",
        "case": "같은 기기, 네트워크, 배송지와 연락처를 3개 계정이 공유해 30초 안에 반복 주문했다. 계정마다 결제수단을 바꾸었고 인증 실패가 총 5회 발생했다.",
        "expected": "decline",
        "signal_group": "multi_account_linkage",
    },
    {
        "name": "고위험 · 결제 실패 누적",
        "case": "한 계정이 짧은 시간에 결제수단을 5번 바꾸며 주문을 반복했고 결제와 인증 실패가 총 4회 누적됐다.",
        "expected": "decline",
        "signal_group": "payment_failure_churn",
    },
    {
        "name": "고위험 · 자동화 초고빈도",
        "case": "자동화 스크립트로 의심되는 동일 패턴의 주문이 한 계정에서 1분에 수십 회 발생했고, 짧은 간격으로 같은 상품을 반복 요청했다.",
        "expected": "decline",
        "signal_group": "automation_velocity",
    },
    {
        "name": "고위험 · 수취인 네트워크 악용",
        "case": "여러 계정이 같은 수취인 연락처와 배송지를 공유하면서 서로 다른 결제수단으로 고가 상품을 분할 주문했다. 구매 한도를 피하려는 정황이 있다.",
        "expected": "decline",
        "signal_group": "recipient_delivery_network_abuse",
    },
)
