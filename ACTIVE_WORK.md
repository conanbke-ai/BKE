# BKE Active Work

## COORD-GUARD-001

- Status: INTEGRATION_PENDING / 독립 검토 및 실제 adapter 확인 대기
- Owner/session: tori-coord-guard-20260908 (구현 종료, 자동 백그라운드 쓰기 없음)
- Classification: IN_PROGRESS — 실행형 도구 구현 및 로컬 검증 완료, main 통합·제품 활성화는 별도
- Canonical branch / PR: work/coordination-guard / BKE PR #2
- Code HEAD: cff82b41fae3fc47fbb405ab6c9baf0f96ef3d65
- Scope: tools/__init__.py, tools/work_guard/**, tests/test_work_guard.py, docs/WORK_GUARD.md, docs/WORK_GUARD_VALIDATION.md, POLICY_ROUTER.md의 도구 위치 안내, 이 ACTIVE_WORK.md
- Do not touch: Test/**, Algorism/**, 제품 저장소의 코드/ACTIVE_WORK/브랜치, 배포·결제 설정
- Policy baseline: 8d764e7b909eba00ce1485b23a3eccacea2b8501
- Implementation base: 6e865a9bec54f464415c2d74ac35cf0925311fdc
- Branch budget: 시작 원격 2/5에서 work/coordination-guard 1개만 추가. 새 작업 생성 전에 실제 refs를 다시 확인한다.
- Completed: CAS 예약, feature/path/contract 충돌, refs+예약 슬롯 및 WIP, 단일 작성자·인계 epoch, 검증된 write/sync 복구, HEAD/base 연결 증거, lead 단일 merge, legacy 본문 보존
- Validation: Python 3.13.5 unittest 81 PASS; compileall/CLI help/3.10 문법 검사 PASS. 실 GitHub 작업 branch에서 이전 blob SHA 재사용 HTTP 409 거절 확인. 임시 probe는 실제 테스트로 대체 완료.
- Not tested: standalone REST 전체 실계정 E2E(API_READ_FAILED), 별도 담당자 독립 리뷰(NOT_REVIEWED), 제품별 init/adopt/활성화
- Rollout: BKE PR #2 검토 후 공통 baseline 통합. 제품의 다음 안전한 checkpoint에서 기존 작업·작성자·실제 refs/PR을 확인하고 init/HOLD/adopt. 현재 진행 작업 강제 인계 금지.
- Next: 동일 PR #2의 코드·테스트·docs/WORK_GUARD_VALIDATION.md를 검토한다. 같은 도구를 새 branch에서 재구현하지 않는다.
- Scope ownership: 위 구현 경로는 PR #2 canonical. 다른 작성자는 인계 기록과 최신 HEAD 확인 후 이어간다. 읽기/리뷰는 가능.
- Resource: 제품 DB/hosted Actions 실행/Render 배포 요청/유료 설정 변경 없음. 자동화 전체 비실행을 보장하는 감사는 아님.
