# Universal Development Team Operating Policy

> 고정 정책 진입점 — 2026-09-08
>
> 기존 제품 `AGENTS.md`의 이 문서 참조를 그대로 사용한다. 세션 시작·정책 캐시·진행 중 작업의 적용 시점은 [TORI_POLICY_BOOTSTRAP.md](TORI_POLICY_BOOTSTRAP.md), 작업별 상세 조회는 [POLICY_ROUTER.md](POLICY_ROUTER.md)를 먼저 확인한다. 전체 본문을 매 요청마다 재독하지 않는다.
>
> 보안 상세는 [SECURITY_STANDARD.md](SECURITY_STANDARD.md), 기준 이후 변경은 [POLICY_CHANGELOG.md](POLICY_CHANGELOG.md), 연결/수신 확인은 [POLICY_VERSION_MATRIX.md](POLICY_VERSION_MATRIX.md)를 사용한다. 기존 더 엄격한 제품·보안 규칙은 유지한다.
>
> 아래 본문의 Preflight는 최신 상태 확인 의무이지 매번 전체 저장소·정책 재탐색 의무가 아니다. 같은 branch 재사용도 동시 쓰기 허용이 아니다. PR close/상태 변경만으로 branch 슬롯이 비지 않는다. 진행 중 작업은 일반 정책 변경 때문에 중단하지 않으며, 필요한 보안 gate와 실제 SHA 기반 검증은 생략하지 않는다.
>
> Project 파일/설정이나 실행 중인 다른 대화창이 자동 변경되는 것은 아니다. 다음 정상 checkpoint에서 기존 참조를 읽을 때 적용한다. 새 ZIP 재업로드나 Project Instructions 재복사는 이번 배포의 요구사항이 아니다.

이 문서는 운토리, MYSTORI, 농토리 및 이후 생성되는 모든 개발 프로젝트에 공통 적용하는 팀 운영 정책이다. 여러 ChatGPT 대화창, Codex, 기타 개발 에이전트를 각각 독립된 팀원으로 간주하고, 동일 저장소를 병렬 작업할 때 중복 개발·브랜치 난립·충돌·회귀를 방지하는 것이 목적이다.

## 1. 역할 모델

- `main`: 통합 완료된 유일한 기준본(Source of Truth)
- `ACTIVE_WORK.md`: 현재 작업 배정표 및 lease registry
- open PR: 아직 main에 들어오지 않은 실제 변경 단위
- branch: 작업용 임시 선로이며 보관소가 아니다
- 각 대화창/에이전트: 독립 팀원으로 간주한다
- 통합 담당 세션: Integration Lead 역할을 맡아 병합 순서와 충돌을 조정한다

대화 기억보다 저장소 상태가 우선한다. 코드, PR, commit, registry가 서로 다르면 최신 실행 코드와 실제 diff를 근거로 판단하고 문서를 수정한다.

## 2. 모든 작업의 필수 Preflight

코드를 수정하기 전에 반드시 다음 순서로 확인한다.

`main -> ACTIVE_WORK.md -> open PR -> branch budget -> recent commits -> changed files -> dependency/contract -> ALREADY_DONE / IN_PROGRESS / NEW`

이 확인 없이 새 branch, 새 PR, 새 구현을 시작하지 않는다.

### 상태 판정

- `ALREADY_DONE`: main 또는 active PR에 구현됨. 재개발 금지, 검수/보완만 허용
- `IN_PROGRESS`: 기존 canonical workstream이 있음. 해당 branch/PR을 이어감
- `NEW`: 기존 구현/진행 작업이 없음. 이때만 신규 workstream 허용
- `BLOCKED`: 선행 작업, contract 결정, 통합 대기 등으로 지금 수정하면 안 됨

## 3. Branch Budget / WIP Limit

### 저장소당 기본 한도

- 전체 branch: `main` 포함 최대 **5개**
- 동시에 ACTIVE인 workstream: 최대 **3개**
- validation branch: 동시 최대 **1개**
- 같은 기능/화면/도메인: active workstream 최대 **1개**
- 같은 핵심 파일/경로: active lease 최대 **1개**

한도에 도달하면 새 작업을 벌이지 않는다. 기존 작업을 merge, close, supersede, cleanup 중 하나로 정리한 뒤 슬롯을 확보한다.

### 금지되는 branch 패턴

동일 목적에 대해 다음 식의 반복 branch 생성을 금지한다.

- `*-v2`, `*-v3`
- `*-final`, `*-final2`
- `*-actual`, `*-real`, `*-implementation`, `*-new`

같은 목적이면 기존 canonical branch를 계속 사용한다.

### Snapshot

`backup/*` branch를 기본적으로 만들지 않는다. 의미 있는 기준 상태 보존이 필요하면 Git tag를 우선한다.

## 4. Workstream Lease / Path Lock

작업을 시작할 때 `ACTIVE_WORK.md`에 다음을 기록한다.

- workstream 이름
- canonical branch / PR
- 상태
- 담당 범위
- 수정 예정 핵심 경로
- 시작일 / 최근 활동일
- Acceptance Criteria
- 선행/후행 dependency
- merge 순서 또는 blocker

같은 핵심 파일/경로에 두 개의 ACTIVE lease를 두지 않는다.

다른 세션이 lease 중인 경로를 수정해야 한다면:

1. 기존 workstream에 합류하거나
2. 선행 PR 병합을 기다리거나
3. 파일/도메인 경계를 명확히 분리한 뒤 registry에 기록한다.

## 5. 작업 배정과 의존성

병렬 개발은 "서로 독립"일 때만 허용한다.

### 병렬 허용 예

- UI 화면 A vs 독립 backend utility
- scenario content vs unrelated admin analytics
- 서로 다른 repository/module이며 contract가 고정된 작업

### 병렬 금지 예

- 같은 auth flow를 두 세션에서 각각 구현
- 한 세션이 API response schema를 바꾸는 동안 다른 세션이 그 schema 기반 UI를 별도 가정으로 구현
- DB migration과 repository 변경을 서로 다른 branch에서 독립 설계
- 같은 CSS/theme/app shell을 여러 branch에서 동시에 수정

의존 작업은 `A -> B -> C` 순서를 registry에 적고 선행 변경이 안정화되기 전에 후행 branch를 불필요하게 만들지 않는다.

## 6. Acceptance Criteria First

작은 typo 수정 외의 작업은 구현 전에 완료 기준을 작성한다.

최소 포함:

- 사용자 관점 기대 동작
- 보존해야 할 기존 contract
- 정상/실패/empty/loading 상태
- 권한/데이터 노출 경계
- 필요한 테스트 수준
- 모바일/브라우저 영향이 있으면 대상 범위

구현 중 요구가 커지면 원래 Acceptance Criteria 밖의 항목은 자동으로 추가하지 않는다. 필요한 경우 후속 workstream으로 분리한다.

## 7. Contract First 정책

다른 팀원이 소비하는 interface를 바꿀 때는 구현보다 contract를 먼저 고정한다.

대상:

- API request/response
- DB schema / migration
- event / Socket.IO payload
- state machine transition
- repository interface
- shared type/schema
- auth/permission policy
- payment/idempotency contract

Contract 변경 시 영향받는 open PR과 call site를 먼저 찾는다. silent breaking change를 금지한다.

가능하면 backward-compatible migration을 사용한다.

`add -> migrate/dual-read -> switch -> remove`

## 8. Merge Queue / Integration Window

main이 계속 움직이는 동안 각 branch가 무한 rebase를 반복하지 않는다.

통합 시점에는 Integration Lead가 다음 순서로 처리한다.

1. 새 변경 잠시 동결
2. open PR dependency와 merge 순서 확인
3. 가장 기반이 되는 PR부터 최신 main 동기화
4. 관련 local quality gate 실행
5. merge
6. 다음 PR을 새 main 기준으로 동기화
7. 충돌 시 기능 contract를 우선해 수동 해결
8. merge 후 `ACTIVE_WORK.md` 상태 갱신
9. merged/obsolete branch를 cleanup 후보로 분류
10. 다음 개발 슬롯 개방

같은 영역을 수정하는 PR은 동시에 merge하지 않는다.

## 9. PR 정책

- 원칙: `1 PR = 하나의 설명 가능한 목적`
- 같은 기능에 중복 PR 금지
- PR 본문에는 목적, 범위, 보존 contract, 검증 방법, known risk를 적는다
- 다른 active PR에 dependency가 있으면 명시한다
- 대규모 unrelated refactor를 기능 PR에 끼워 넣지 않는다
- review feedback은 가능하면 기존 PR에서 수정하고 `final2` branch를 만들지 않는다

PR이 너무 커져 review가 어려워지면 기능 contract가 깨지지 않는 경계에서만 분리한다.

## 10. Definition of Done

"코드 작성 완료"는 DONE이 아니다.

DONE 조건:

1. Acceptance Criteria 충족
2. 관련 test/regression/smoke 통과
3. 정상뿐 아니라 loading/empty/error/failure 검토
4. 권한/개인정보/데이터 경계 검토
5. UI면 desktop/mobile/focus/hit area/reduced-motion 검토
6. DB면 migration/transaction/idempotency/rollback 검토
7. API/event/schema 변경이면 consumer 영향 확인
8. 로그/관측 가능성 필요한 영역 확인
9. 문서와 `ACTIVE_WORK.md` 갱신
10. merge/cleanup 다음 상태 명확화

## 11. Testing Ownership

각 workstream 담당 세션이 자기 변경의 최소 검증 책임을 진다.

- 일반 변경: 관련 fast/unit/static 검증
- 위험 변경: 관련 contract/integration/regression 추가
- release/integration: 전체 gate 또는 필요한 staging smoke

다른 세션이 나중에 알아서 검증할 것이라고 가정하고 미검증 코드를 넘기지 않는다.

단, GitHub Actions/Render/외부 API 무료 사용량 정책을 따라 로컬 검증을 우선한다.

## 12. Handoff 정책

한 세션이 작업을 끝내지 못하고 다른 세션으로 넘길 때는 다음 정보를 남긴다.

- 현재 branch/PR/SHA
- 구현 완료 범위
- 미완료 항목
- 수정한 주요 파일
- 테스트한 것 / 테스트하지 못한 것
- known issue
- 다음 정확한 작업
- 절대 건드리면 안 되는 영역

"거의 다 됨" 같은 모호한 handoff는 금지한다.

## 13. Commit 정책

- commit은 의미 있는 변경 단위로 만든다
- 메시지는 `feat/fix/refactor/test/docs/chore` + 목적을 명확히 한다
- 서로 무관한 변경을 한 commit에 섞지 않는다
- formatter 때문에 전체 파일이 불필요하게 재작성되는 일을 피한다
- 생성물/대용량 binary를 무분별하게 commit하지 않는다

## 14. 리팩토링 / 레거시 정책

- 이미 있는 기능을 새로 작성하기 전에 기존 구현 확장 가능성을 먼저 본다
- 변경과 직접 연결된 레거시는 점진적으로 정리한다
- 무관한 전체 구조 개편을 기능 작업에 섞지 않는다
- 삭제는 `참조 0 + 대체 구현 확인 + 관련 검증 PASS` 후에만 한다
- deprecated bridge에는 제거 조건 또는 후속 workstream을 남긴다

리팩토링 신호 예:

- 같은 조건문 3곳 이상
- 같은 DB query 2곳 이상
- 하나의 Service/JS/CSS가 계속 비대해짐
- 동일 비즈니스 규칙이 여러 layer에서 중복됨

## 15. Dependency 정책

새 package/library 추가 전에 확인한다.

1. 기존 dependency로 가능한가
2. 표준 라이브러리로 가능한가
3. 유지보수 상태/라이선스/보안 문제는 없는가
4. bundle/build/runtime 비용이 과하지 않은가

작은 UI 효과 하나를 위해 무거운 dependency를 추가하지 않는다.

## 16. Data / DB Safety

- production 데이터로 테스트하지 않는다
- 테스트 데이터는 명확히 식별하고 격리한다
- 원본 Google Sheets/외부 원본은 명시적 요청 없이는 read-only
- destructive migration은 사용자 승인 없이 실행하지 않는다
- schema 변경은 migration 코드로 남긴다
- production 수동 schema patch를 기본 방식으로 사용하지 않는다

## 17. Secrets / Security

- secret, API key, token, password를 source/PR/log에 기록하지 않는다
- `.env.example`에는 변수명과 안전한 예시만 둔다
- authorization은 UI 숨김이 아니라 server-side 정책으로 보장한다
- 개인정보/민감정보는 로그에 남기지 않는다
- 새 endpoint는 authentication/authorization/rate limit 필요성을 검토한다

## 18. Observability

운영에 영향을 주는 기능은 실패 원인을 추적할 수 있어야 한다.

가능한 경우 다음을 사용한다.

- request/job id
- 단계별 error code
- 외부 dependency 상태
- retry 여부
- duration

민감 데이터는 기록하지 않는다.

## 19. Feature Flag / Safe Migration

인증, 결제, 게임 state, DB, 대규모 UI shell처럼 영향 범위가 큰 변경은 필요하면 feature flag/new route/compatibility adapter로 점진 전환한다.

검증 완료 후 old path를 제거한다. 새/구 구조를 영구히 둘 다 유지하지 않는다.

## 20. Stale Work 정책

- 7일 이상 활동 없음: 상태 재검토
- 14일 이상 활동 없음: `LONG_RUNNING` 사유가 없으면 cleanup/close 후보
- blocker가 있으면 `BLOCKED`와 원인을 기록

오래된 branch 이름만 보고 다시 개발하지 않는다.

## 21. Hotfix 정책

production 장애 또는 보안 문제만 branch budget 예외를 허용한다.

- `hotfix/*` 최대 1개 임시 허용
- 범위 최소화
- 수정 후 관련 regression test 추가
- main 반영 즉시 일반 branch budget으로 복귀

## 22. 승인 없이 하면 안 되는 작업

다음은 사용자 명시 승인 전 실행하지 않는다.

- branch/tag 대량 삭제
- production/staging 실제 데이터 삭제
- destructive DB migration
- Render service/DB 삭제
- 다른 active workstream을 강제로 reset/revert
- 대규모 force push
- paid overage/유료 플랜/spend limit 상향
- 보안/결제 정책을 약화시키는 변경

## 23. 새 프로젝트 기본 Bootstrap

앞으로 새 개발 프로젝트를 만들면 초기에 다음을 둔다.

- `AGENTS.md`: 필수 실행 순서와 프로젝트별 검증 명령
- `ACTIVE_WORK.md`: branch budget + lease registry
- architecture/design 기준 문서
- local fast test command
- `.env.example`
- migration/DB 정책이 필요한 경우 migration 체계

프로젝트가 작더라도 branch budget과 workstream lease 규칙은 처음부터 적용한다.

## 24. 팀원 작업 시작 체크리스트

각 대화창/에이전트는 개발 시작 전 스스로 다음을 확인한다.

1. 이 기능은 이미 있는가?
2. 다른 세션이 지금 수정 중인가?
3. 기존 branch/PR을 이어갈 수 있는가?
4. branch slot과 WIP slot이 남아 있는가?
5. 내가 수정할 경로의 lease가 비어 있는가?
6. Acceptance Criteria는 무엇인가?
7. 어떤 contract를 절대 깨면 안 되는가?
8. 선행 PR이 있는가?
9. 최소 검증은 무엇인가?
10. 완료 후 merge/cleanup/handoff는 어떻게 할 것인가?

이 10개에 답할 수 없으면 바로 코딩하지 않는다.