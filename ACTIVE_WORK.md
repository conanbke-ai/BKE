# BKE Active Work

## COORD-GUARD-001

- Status: ACTIVE
- Owner/session: tori-coord-guard-20260908
- Classification: NEW — main에는 협업 정책만 있으며 실행형 예약 도구가 없다.
- Canonical branch: work/coordination-guard (예약, 아직 생성 전)
- Scope: tools/work_guard/**, tests/test_work_guard.py, docs/WORK_GUARD.md, DEVELOPMENT_TEAM_OPERATING_POLICY.md의 진입 안내, 이 ACTIVE_WORK.md
- Do not touch: Test/**, Algorism/**, 제품 저장소의 코드/ACTIVE_WORK/브랜치, 배포·결제 설정
- Baseline: 8d764e7b909eba00ce1485b23a3eccacea2b8501
- Branch budget at start: 원격 2/5, 이번 작업 예약 포함 3/5
- Acceptance: 동시 예약 CAS, 경로/계약 중복 및 실제 브랜치 슬롯 검사, 단일 작성자·인계 epoch, 오래된 snapshot/리뷰 거부, merge guard, 기존 문서 보존, 로컬 회귀 테스트
- Validation: Python 표준 라이브러리 unittest 및 오프라인/가짜 GitHub adapter 통합 검사. 제품 DB/hosted CI/Render는 사용하지 않는다.
- Rollout: 제품의 진행 작업을 강제 인계하지 않는다. 제품별 초기 전환은 다음 checkpoint에 실제 기존 작업을 검토한 담당 세션이 수행한다.
