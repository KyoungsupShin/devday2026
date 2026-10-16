# 3. Gen AI Hub Services

AI Core Orchestration 계열 기능을 분리해 확인합니다. 모든 노트북은 루트 `.env`를 읽습니다.

| 노트북 | 주제 |
| --- | --- |
| `01_orchestration.ipynb` | prompt templating, 콘텐츠 필터, 데이터 마스킹 |
| `02_grounding.ipynb` | 문서 grounding 질의 |
| `03_my_documents.ipynb` | 개인/공유 저장소 질의 |
| `04_memory_chatbot.ipynb` | 대화 history 전달 |

Grounding 저장소 ID가 필요한 노트북은 `GROUNDING_REPOSITORY_ID`를 `.env`에 설정해야 합니다.
