# Cohere Reranker 결정 모델 개선 기록

## 확인한 기존 구조와 문제

- 기존 V1은 LLM 정책 요약 후, 포괄적인 후보 문서 3개를 Cohere Reranker에 전달했다. 따라서 요청당 모델 호출이 2회였고, 원문 관측값·후보 원본 index·반환 순위를 구분해 기록하지 않았다.
- 후보 문서는 정상/관찰/고위험의 선택 조건과 임계값이 겹쳐 수치 경계 또는 누락 데이터의 재현성이 낮았다.
- relevance score는 확률이 아니지만, top-1/top-2 값과 분류·검토 메타데이터가 충분히 분리되어 있지 않았다.

## 변경사항

- V1을 변경하지 않은 baseline으로 보존했다.
- 기본 V2는 새 LLM 호출 없이 task와 고정 순서 관측값의 YAML query를 만든다. false, 0, unknown은 서로 다른 값으로 유지한다.
- V2 후보 문서는 정책 문서에 있는 20초, 분당 3회/4~6회/7회, 실패 1~2회/3회 이상 기준만 쓴다. 후보 ID와 표시 label은 분리돼 기존 approve/manual-review/decline 계약을 유지한다.
- V3는 클래스별 2개 prototype으로 구성하고, 클래스 score는 prototype별 최대 relevance score로 집계한다. 후보 수가 많은 클래스를 우대하지 않는다.
- 결과에는 strategy, model, top1/top2 score, margin, 구조화 관측값, policy validation 결과, reranker 반환 순위와 원본 document index를 추가한다.
- 선택적 정책 검증은 명시된 수치/Boolean 사실만 다룬다. 추천만 반환하며 고객의 승인·반려 상태는 변경하지 않는다.

## 실제 API 평가 (2026-10-20)

모델은 cohere-rerank-pro이고, 9개 synthetic 케이스 중 8개는 정책 문서의 명시 조건으로 라벨링했다. missing_data 1개는 안전상 검토로 분류한 가정이다. 따라서 이 결과는 운영 정확도가 아니라 회귀 비교 기준이다.

| 구성 | 범위 | Accuracy | Macro F1 | HIGH_RISK FN | 평균 지연 | 호출/요청 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| V1 baseline | 정상·주의·위험 대표 3건 | 66.7% | 55.6% | 100.0% | 4.92초 | 2 |
| V2 구조화 rerank | 9건, gate 미적용 | 55.6% | 50.0% | 0.0% | 1.39초 | 1 |
| V3 multi-prototype | 9건, gate 미적용 | 66.7% | 65.7% | 0.0% | 1.41초 | 1 |
| V2 + 정책 검증 + 누락 검토 | 9건 | 100.0% | 100.0% | 0.0% | 1.35초 | 1 |

V3는 raw rerank 기준에서 V2보다 좋았지만, 정책 검증을 적용한 V2보다 개선됐다는 근거는 없다. 따라서 기본 전략은 V2로 유지한다. 100% 결과는 작고 정책에 맞춘 synthetic set의 결과이므로 실제 라벨된 주문 로그로 다시 검증한 뒤에만 threshold를 조정해야 한다.

## 재실행

src.reranker.benchmark.benchmark_strategies(settings)는 V1/V2/V3를 같은 케이스로 평가한다. 정책 계층 효과는 enable_policy_validation=True, enable_uncertainty_detection=True를 명시해 별도로 비교한다.
