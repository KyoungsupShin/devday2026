# 3. Gen AI Hub Services

AI Core Orchestration 계열 기능을 분리해 확인합니다. 모든 노트북은 루트 `.env`를 읽습니다.

노트북별 코어는 아래처럼 분리되어 있으며, 각 노트북은 해당 `lab_core.py`만 import합니다.

```text
src/
├── orchestration/lab_core.py
├── grounding/lab_core.py
├── documents/lab_core.py
└── memory/lab_core.py
```

| 노트북 | 주제 |
| --- | --- |
| `01_orchestration.ipynb` | prompt templating, 콘텐츠 필터, 데이터 마스킹 |
| `02_grounding.ipynb` | 문서 grounding 질의 |
| `03_my_documents.ipynb` | 개인/공유 저장소 질의 |
| `04_memory_chatbot.ipynb` | 대화 history 전달 |

Grounding 저장소 ID가 필요한 노트북은 `GROUNDING_REPOSITORY_ID`를 `.env`에 설정해야 합니다.

`03_my_documents.ipynb`에는 선택한 vector 저장소의 UTF-8 `.txt`/`.md` 문서를 업로드하고,
목록에서 document ID를 골라 삭제하는 관리 UI도 포함되어 있습니다. 삭제는 되돌릴 수 없습니다.
