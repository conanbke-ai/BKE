# Work Guard 검증 기록

Date: 2026-09-08
Workstream: COORD-GUARD-001
Implementation branch: work/coordination-guard

## 실제 수행 결과

- Python 3.13.5에서 `python -m unittest discover -s tests -p 'test_work_guard.py' -v`: **81 tests PASS**.
- `python -m compileall -q tools`: PASS.
- `python -m tools.work_guard --help`: PASS.
- Python 3.10 문법 AST parsing: 7개 Python 파일 PASS. 3.10 런타임을 별도로 실행한 것은 아니다.
- 실행 기반: 격리된 로컬 FakeGitHub/REST mock; 제품 데이터나 외부 유료 API를 사용하지 않았다.

## 검증 범위

동시 예약 두 요청 중 CAS 저장 하나만 성공, 중복 feature/path/contract, 실제 refs와 예약 슬롯 합계, WIP/validation 한도, readonly 조회, 기존 브랜치 무단 재사용 거절, unknown write 결과 잠금·복구, 작성자/epoch·인계, 범위 외 변경 거절, PR/테스트/review SHA 일치, stale main에서 sync 요구, lead 단일 병합, metadata-only 변경의 테스트 재사용, 손상 JSON/pagination/HTTP 오류·redirect·token 보안, CLI dry-run을 검증했다.

테스트 메서드 이름과 정확한 assertions는 `tests/test_work_guard.py`가 근거다. 81개가 제품 전체 테스트 또는 외부 보안 감사를 의미하지 않는다.

## 실 GitHub stale-SHA 확인

BKE의 이 작업용 브랜치에서 임시 `tests/test_work_guard.py`만 사용했다. 제품 저장소를 건드리지 않았다.

1. 초기 blob `adf6e3d560501ce1916de02ec1d9d9ed71ae145b` 조회.
2. 첫 writer가 해당 SHA로 수정 성공: commit `2789ea0be000d1da4b23b78d65d816996b553872`, 새 blob `dd09690f2df546a021e7976a884db169ad4d57ad`.
3. 두 번째 writer가 초기 SHA로 덮어쓰기 시도: **GitHub HTTP 409**, `does not match`로 거절.
4. 임시 probe 파일은 이 PR에서 전체 실제 회귀 테스트로 교체했다.

이는 실제 provider의 stale-SHA 거절을 확인한 것이고, 두 개의 실계정 worker를 병렬 실행한 end-to-end 시험은 아니다. 실제 동시 두 스레드 경합은 로컬 CAS fixture에서 검증했다.

## 미수행 / 활성화 범위

- standalone urllib의 live GET은 이 실행 환경에서 `API_READ_FAILED`로 종료됐다. 따라서 standalone REST의 전체 실계정 예약→쓰기→병합 E2E는 **NOT_RUN**.
- 연결된 GitHub 도구로 소스 게시와 위 CAS 원리는 확인했다. connector credential을 추출하거나 토큰을 사용자 채팅에 요구하지 않았다.
- 별도 담당자의 독립 코드/보안 리뷰: **NOT_REVIEWED**. 이 기록을 reviewer PASS로 사용하지 않는다.
- 제품 저장소의 managed registry init/adopt, 작성자 지정, 제품 코드/branch/DB/배포 변경: **NOT_RUN**. 다음 제품 통합 checkpoint에 실제 기존 작업을 확인한 후 초기 전환해야 한다.
- GitHub 서버의 raw push/merge 권한 제한이나 automatic chat monitoring은 구현하지 않았다. 협조하는 세션이 도구를 사용해야 보호된다.
- hosted Actions 실행, Render 배포 요청, paid overage/유료 설정 변경 없음. skip marker가 모든 외부 자동화를 차단한다고 보장하지 않는다.

## 검토 후 통합 조건

소스/회귀 diff를 다른 담당자가 검토하고, 실제 권한이 있는 격리 환경에서 connector 또는 standalone adapter의 요청→receipt→복구 흐름을 확인한 뒤 공통 기준본 통합을 결정한다. 현재 사용자 프로젝트의 진행 작업을 즉시 중단·강제 전환하지 않는다.
