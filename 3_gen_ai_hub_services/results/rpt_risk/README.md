# SAP RPT Holdout Results

`03_rpt_risk_classification.ipynb`의 평가 결과 CSV 저장 버튼은 이 폴더에 timestamp가 포함된 holdout 예측 CSV를 만듭니다. CLI `rpt-evaluate`와 노트북 모두 교육용 데이터에 대한 읽기 전용 SAP RPT 예측만 수행합니다.

저장 파일에는 사람 검토용 예측·정답·평가 기준이 포함될 수 있지만, 원본 customer ID와 비밀값은 포함하지 않습니다. 이 폴더에는 교육용 fixture에서 생성된 결과만 보관하고, 실제 고객 데이터·식별자·비밀값이 포함된 결과는 저장하거나 커밋하지 마세요.
