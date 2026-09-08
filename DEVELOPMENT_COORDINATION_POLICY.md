# 공통 개발 작업 조정 정책

이 문서는 ChatGPT, Codex 및 다른 개발 보조도구가 여러 대화창/세션에서 같은 저장소를 동시에 다룰 때 중복 구현, 브랜치 난립, 이미 만든 기능의 재개발, 충돌성 병렬 작업을 방지하기 위한 공통 규칙이다.

## 1. 작업 시작 전 Preflight는 의무

새 코드 수정 전에 반드시 다음 순서로 확인한다.

1. 현재 `main`의 실제 구현 상태
2. `ACTIVE_WORK.md`
3. open PR 목록과 각 PR의 목적/changed files
4. 현재 branch 목록과 branch budget
5. 최근 commit에서 같은 기능이 이미 구현됐는지
6. `AGENTS.md`, 관련 설계/migration 문서
7. 수정 예정 파일/경로가 다른 active workstream의 lease 범위와 겹치는지

이 확인 없이 새 branch, 새 PR 또는 새 구현을 시작하지 않는다.

## 2. 새 작업 판정

요청을 받으면 반드시 아래 셋 중 하나로 판정한다.

- `ALREADY_DONE`: main 또는 active PR에 이미 구현됨 → 재개발 금지, 검수/보완/리팩토링만
- `IN_PROGRESS`: 기존 open PR/branch에서 진행 중 → 해당 canonical workstream을 이어감
- `NEW`: 기존 구현/진행 작업이 없음 → 신규 구현 가능

판정은 기억이나 대화 추측이 아니라 실제 코드/PR/commit으로 확인한다.

## 3. Branch Budget — 저장소당 총 5개 이하

원칙적인 hard cap은 `main` 포함 **최대 5개 branch**다.

권장 구성:

- `main`: 1
- active work branch: 최대 3
- validation branch: 최대 1

따라서 동시에 `ACTIVE`인 workstream도 **최대 3개**다.

### 새 branch 생성 조건

아래 조건을 모두 만족해야 한다.

1. 상태 판정이 `NEW`
2. 기존 canonical branch/PR로 흡수할 수 없음
3. 다른 active workstream과 파일/도메인이 독립적임
4. branch slot이 남아 있음
5. Acceptance Criteria가 먼저 정의됨

branch가 이미 5개면 새 branch 생성은 금지한다. 먼저 기존 branch를 `merge / close / superseded / cleanup candidate` 중 하나로 정리한다.

### 예외: production hotfix

실제 운영 장애/보안 문제에 한해 `hotfix/*` 1개를 임시 허용해 총 6개가 될 수 있다. 해결 후 24시간 내 통합/정리하여 다시 5개 이하로 돌아온다.

## 4. 한 기능 = 하나의 active workstream

같은 기능/화면/도메인에 대해 동시에 여러 active branch를 만들지 않는다.

동일 목적의 다음 이름 반복은 금지한다.

- `v2`, `v3`
- `final`, `final2`
- `actual`, `real`, `implementation`, `new`

예: `feat/auth-home`, `feat/auth-home-v2`, `feat/auth-home-final`을 만들지 않고 canonical branch 하나를 계속 사용한다.

권장 이름:

- `work/<domain>-<scope>`
- `validation/<purpose>`
- `hotfix/<incident>`

기준 상태 보존은 `backup/*` branch 대신 Git tag를 우선한다.

## 5. Workstream Lease / Path Lock

여러 대화창이 같은 저장소를 동시에 수정할 수 있으므로 active workstream은 `ACTIVE_WORK.md`에 lease를 남긴다.

최소 기록 항목:

- workstream
- canonical branch / PR
- 상태
- lease owner/session 설명
- 수정 예정 경로 또는 핵심 파일
- 시작일/마지막 활동일
- Acceptance Criteria / 다음 단계

규칙:

1. 같은 핵심 파일/경로에는 동시에 active lease를 2개 두지 않는다.
2. 다른 세션이 lease 중인 경로를 발견하면 별도 branch에서 수정하지 않는다.
3. 기존 workstream에 합류하거나 선행 작업 통합 후 진행한다.
4. 작업 종료/중단/merge 시 lease를 즉시 해제한다.
5. 도메인이 독립적이고 수정 경로도 겹치지 않을 때만 병렬 작업을 허용한다.

## 6. WIP 제한

저장소당 동시에 진행 중인 `ACTIVE` workstream은 최대 3개다.

3개가 차 있으면 새 기능을 시작하기보다 기존 작업을 다음 중 하나로 먼저 이동한다.

- `MERGED_BASELINE`
- `READY_TO_MERGE`
- `PAUSED`
- `BLOCKED`
- `SUPERSEDED`
- `CLEANUP_CANDIDATE`

WIP 제한은 branch 수와 별개로 적용한다. branch 5개 미만이어도 active workstream이 3개면 새 기능을 벌리지 않는다.

## 7. Acceptance Criteria 선작성

규모가 있는 기능은 구현 전에 완료 조건을 3~10개 수준으로 먼저 정의한다.

Acceptance Criteria에는 필요한 경우 다음을 포함한다.

- 정상 사용자 flow
- 실패/오류 flow
- 권한 경계
- 모바일/반응형
- loading/empty/error
- 데이터 보존/transaction
- 기존 기능 호환성
- 성능/비용 영향

구현 도중 새로운 요구가 생기면 기존 scope에 필수인지 판단하고, 무관한 확장은 별도 backlog로 남긴다.

## 8. Definition of Done — 코드 작성만으로 완료 아님

작업은 다음이 충족되어야 `DONE` 또는 `MERGED_BASELINE`으로 본다.

1. 기능 구현 완료
2. 관련 최소 regression/unit/integration test 수행
3. 오류/loading/empty 등 필요한 비정상 상태 검토
4. UI면 desktop/mobile 및 keyboard/focus 영향 검토
5. API/인증이면 authorization/개인정보/실패 응답 검토
6. DB면 transaction/idempotency/rollback 또는 migration 전략 검토
7. 기존 계약/호환성 회귀 없음
8. `ACTIVE_WORK.md`와 필요한 문서 갱신
9. 불필요한 hosted CI/Render/API 비용을 만들지 않음
10. merge 후 branch lifecycle이 명확함

## 9. PR 범위 규칙

- 하나의 PR은 설명 가능한 하나의 목적을 갖는다.
- UI 재설계 + DB schema + 결제 + 무관한 리팩토링을 한 PR에 섞지 않는다.
- 단, 하나의 기능을 안전하게 동작시키기 위해 반드시 함께 바뀌어야 하는 변경은 인위적으로 쪼개지 않는다.
- 이미 open PR이 있으면 새 PR보다 기존 PR 갱신을 우선한다.
- validation PR은 `validation-only`로 명확히 구분하며 운영 merge 대상과 섞지 않는다.

## 10. Integration Window

main이 다른 대화창에서 계속 움직이는 동안 rebase/merge를 반복하지 않는다.

통합 시점에는 짧은 Integration Window를 잡는다.

1. 같은 영역 신규 변경 잠시 중지
2. 최신 main 1회 동기화
3. 충돌 해결
4. local quality gate
5. 필요 시 staging smoke
6. merge
7. `ACTIVE_WORK.md` 갱신
8. merged/obsolete branch 정리 후보화

## 11. Stale Work / Branch TTL

- 7일 이상 활동 없음 → 상태/필요성 검토
- 14일 이상 활동 없음 → 유지 이유가 없으면 `CLEANUP_CANDIDATE`
- 장기 migration은 `LONG_RUNNING`으로 명시하고 유지 이유/다음 checkpoint를 적는다.
- merged branch는 다음 Integration Window에서 정리 후보가 된다.

브랜치 삭제 자체는 사용자 승인 없이 수행하지 않는다.

## 12. 버그 수정 규칙

가능하면 버그를 고치기 전에 재현 테스트를 만든다.

`재현 실패 확인 -> 수정 -> 동일 테스트 PASS`

단순 문구/명백한 사소한 UI 오타처럼 테스트 비용이 더 큰 경우는 예외로 할 수 있으나, 재발 가능성이 있는 버그는 regression test를 남긴다.

## 13. 리팩토링 규칙

- 이미 구현된 코드를 복제해서 새 기능을 만들지 않는다.
- 동일 조건문 3곳 이상, 동일 DB query 2곳 이상, 거대 Service/JS/CSS가 계속 증가하면 리팩토링 신호로 본다.
- 현재 기능과 무관한 전체 리팩토링을 작업 중간에 벌리지 않는다.
- 변경 범위와 직접 연결된 레거시만 점진적으로 정리한다.

## 14. 레거시 삭제 Gate

`안 쓰는 것 같음`만으로 삭제하지 않는다.

삭제 전 최소 조건:

1. 코드 검색상 참조 0 또는 명확한 대체 경로 확인
2. 관련 local test/smoke PASS
3. 기능/API/권한 계약 대체 확인
4. 필요한 경우 desktop/mobile/runtime 검수

대량 삭제/데이터 삭제/branch 삭제는 사용자 승인 대상이다.

## 15. DB / Migration 규칙

- production/staging schema를 수동 변경하지 않고 migration을 코드로 남긴다.
- destructive migration은 가능하면 `add -> migrate -> switch -> remove` 순서로 한다.
- transaction, idempotency, rollback 가능성을 검토한다.
- production 데이터나 외부 원본 데이터를 테스트용으로 수정/삭제하지 않는다.
- 테스트 데이터는 명확한 `test_` 식별자를 사용한다.

## 16. Dependency / Secrets 규칙

새 dependency 추가 전 기존 dependency/표준 API로 해결 가능한지 확인한다.

- 단순 UI 효과 하나를 위해 무거운 package를 추가하지 않는다.
- 새 package의 용도와 유지 필요성을 설명할 수 있어야 한다.
- API key, DB password, token, webhook secret은 코드/PR/로그에 넣지 않는다.
- `.env.example`에는 키 이름/예시 형태만 두고 실제 secret은 환경변수로 관리한다.

## 17. 외부 API / AI / 비용형 리소스

상세 기준은 `DEVELOPMENT_RESOURCE_POLICY.md`를 따른다.

추가 원칙:

- cache/reuse 가능한 결과는 재호출하지 않는다.
- 대량 작업 전 작은 representative sample로 먼저 실패 여부를 확인한다.
- hosted CI/Render/외부 API를 개발의 기본 실행 환경으로 사용하지 않는다.
- 비용 증가 설정은 사용자 명시 승인 없이 활성화하지 않는다.

## 18. Observability 규칙

운영/비동기/외부 연동 기능은 가능한 범위에서 다음을 남긴다.

- request/job correlation id
- 실패 단계
- 안정적인 error code/category
- 외부 dependency 상태

개인정보, 인증정보, secret은 로그에 남기지 않는다.

## 19. Destructive Action 승인 규칙

다음은 사용자 명시 승인 없이 수행하지 않는다.

- branch/tag 대량 삭제
- production/staging 실제 데이터 삭제
- destructive migration 실행
- Render service/DB 삭제
- rollback으로 다른 세션의 작업을 되돌리는 행위
- paid plan/overage/spend limit 상향
- 대량 파일 삭제

## 20. 사용자 확인이 필요한 충돌 상황

다음 경우 구현을 밀어붙이지 않는다.

- 서로 다른 active PR이 같은 기능을 구현 중이며 canonical 선택이 불명확함
- 같은 핵심 파일에 서로 다른 lease가 잡혀 있음
- 기존 구현을 버리고 재설계해야 함
- 대규모 rebase/merge가 다른 진행 작업을 덮을 수 있음
- branch budget/WIP limit을 초과해야 하는데 hotfix가 아님

## 21. AI 개발 세션 표준 실행 순서

모든 ChatGPT/Codex 세션은 다음 순서를 따른다.

`Preflight -> ALREADY_DONE/IN_PROGRESS/NEW -> branch/WIP slot 확인 -> lease 확인/획득 -> Acceptance Criteria -> 최소 구현 -> local risk-based validation -> DoD 확인 -> registry 갱신 -> Integration Window/cleanup`

절대 다음 방식으로 움직이지 않는다.

`요청 -> 새 branch -> 비슷한 코드 재작성 -> 새 PR -> 또 v2/final branch`

## 22. 정책 자체의 레거시 방지

각 저장소의 `AGENTS.md`에는 필수 실행 순서, branch/WIP limit, 금지사항과 프로젝트별 검증 명령만 간결하게 둔다. 상세 설명은 공통 정책/프로젝트 설계 문서에서 관리한다.

정책이 서로 충돌하면 우선순위는 다음과 같다.

1. 사용자 최신 명시 지시
2. 저장소의 현재 안전/데이터/보안 제약
3. `ACTIVE_WORK.md`의 현재 lease/canonical workstream
4. 공통 coordination/resource policy
5. 개별 오래된 문서
