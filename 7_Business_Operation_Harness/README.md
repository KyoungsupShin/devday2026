# 7. Business Operation Harness — Cross-Team Deep Agent Chat

Business Operations와 Customer Operations의 LLM agent가 team-to-team handoff를 대화 화면에서 수행하는 실습입니다. 모든 agent 메시지는 설정된 AI Core/Gen AI Hub 모델 호출로 생성됩니다.

```text
사용자
  → Business Ops Lead → Inventory Specialist
  → Business Ops Lead ── team_handoff ──→ Customer Ops Lead → Service Coordinator
  ← Business Ops Lead ← cross_team_commitment ← Customer Ops Lead
  → 사용자
```

## 실행

JupyterLab에서 [01_cross_team_deepagent_chat.ipynb](notebooks/01_cross_team_deepagent_chat.ipynb)를 위에서 아래로 실행하세요. 루트 `.env`에 AI Core 인증 정보와 `LLM_MODEL`을 설정한 뒤, UI에서 요청을 보내면 team/agent 이름, 메시지 type, thread ID가 포함된 LLM chat transcript와 전체 trace가 표시됩니다.

```bash
python3 -m unittest discover -s 7_Business_Operation_Harness/tests -v
```

## 범위와 안전 경계

- 합성 fixture와 rule-engine 판단은 사용하지 않습니다. 각 agent는 사용자 요청과 이전 agent의 LLM 메시지를 문맥으로 받아 응답을 생성합니다.
- `src/cross_team_chat.py`의 `TeamMessage`는 remote Deep Agent/A2A transport로 교체할 때 유지할 interface contract입니다. `thread_id`, 송·수신 team/agent, `kind`, `content`를 보존해야 합니다.
- 모델은 외부 시스템에 연결되지 않습니다. 검증되지 않은 재고·고객·정책·일정은 미확인으로 표시하도록 prompt에 명시했습니다.

## 구성

| 경로 | 역할 |
| --- | --- |
| `src/cross_team_chat.py` | LLM team agent interface와 cross-team handoff runtime |
| `notebooks/01_cross_team_deepagent_chat.ipynb` | LLM Chat UI, trace, team interface 실습 |
| `tests/test_cross_team_chat.py` | LLM prompt와 team interface contract 검증 |
