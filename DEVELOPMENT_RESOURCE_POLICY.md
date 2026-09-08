# 공통 개발 리소스 효율 정책

이 문서는 `conanbke-ai`의 개발 작업에서 공통으로 적용하는 기준이다. 기능 품질을 낮추지 않되 GitHub Actions, Render, 외부 API/AI, DB 등 사용량·과금형 리소스는 무료 포함량을 우선 보존한다.

## 1. 최상위 원칙

1. 무료 포함량은 "다 써도 되는 기본 자원"이 아니라 월간 개발 예산으로 취급한다.
2. 동일한 검증을 로컬에서 수행할 수 있으면 로컬 실행을 우선한다.
3. hosted CI, staging deploy, 외부 브라우저/크롤링, 유료 API는 로컬로 대체할 수 없는 검증에만 사용한다.
4. 비용·사용량을 늘리는 설정을 자동으로 활성화하지 않는다. 결제수단 등록, paid overage, 유료 플랜 전환, spend limit 상향은 사용자 명시 승인 없이는 하지 않는다.
5. 코드 품질을 무료 사용량 때문에 생략하지 않는다. 대신 `로컬 -> 선택적 hosted 검증 -> staging/release`로 실행 위치를 바꾼다.
6. 테스트와 검증 명령은 가능한 한 프로젝트 자체 스크립트로 제공하고, CI는 그 스크립트를 호출만 하도록 만든다.

## 2. 작업 시작 전 Resource Gate

코드를 수정하기 전에 변경을 다음 중 하나로 분류한다.

- `LOCAL_FAST`: 일반 UI/API/작은 기능 변경. 로컬 syntax/type/unit/contract 중심.
- `LOCAL_RISK`: 계산엔진, 결제, 인증, DB transaction, 게임 state 등 위험도가 높은 변경. 관련 회귀 테스트를 로컬에서 추가 실행.
- `STAGING_REQUIRED`: 실제 PostgreSQL, 세션/cookie, Socket.IO, 외부 네트워크, production build/runtime 등 로컬만으로 충분하지 않은 변경.
- `RELEASE_GATE`: 배포 전 전체 회귀, 콘텐츠 QA, E2E, Golden/Oracle 등.
- `EXTERNAL_VALIDATION`: 외부 사이트 probe/crawl, 대량 비교, AI/API 호출. 기본 수동 실행.

변경 범위를 먼저 분류하고 필요한 최소 검증만 실행한다. 무관한 전체 테스트를 매 commit마다 반복하지 않는다.

## 3. GitHub Actions 규칙

### 기본

- 개발 중 검증은 로컬을 기본으로 한다.
- `push + pull_request` 중복 자동 실행을 만들지 않는다.
- 같은 PR의 이전 실행은 `concurrency.cancel-in-progress`로 취소한다.
- 문서/무관 파일 변경은 `paths`/`paths-ignore`로 제외한다.
- dependency cache를 사용한다.
- CI job은 가능한 한 1개의 fast gate로 유지한다.

### 금지/제한

다음 작업을 모든 commit/PR에 자동 연결하지 않는다.

- Playwright/브라우저 설치가 필요한 전체 E2E
- 외부 사이트 크롤링/DOM probe
- 100건 이상 대량 교차검증
- matrix/shard 병렬 대량 검증
- 전체 Golden/Oracle/장기 시계열/대규모 데이터 QA
- 동일 검증의 여러 workflow 중복 실행

이들은 `workflow_dispatch`, release gate 또는 명시적 opt-in 방식으로 실행한다.

### 무료량 보호 단계

현재 사용량을 확인할 수 있을 때 다음 기준을 적용한다.

- 잔여 50% 이상: Fast CI만 자동 허용 가능.
- 잔여 25~50%: 자동 CI 빈도와 범위를 축소.
- 잔여 10~25%: 필수 PR gate만 유지하고 heavy job은 수동 전환.
- 잔여 10% 미만: hosted 자동 실행 중단, manual/release only.
- 무료량 소진: 로컬 검증 + 필요한 staging 검증으로 전환.

새 workflow를 추가할 때는 trigger, 예상 실행 빈도, 예상 runtime, matrix 개수, 무료량 영향을 먼저 검토한다.

## 4. Render 규칙

- commit/push마다 staging/validation 서비스를 자동 배포하지 않는다.
- 검증용/일회성 서비스는 `autoDeploy`를 기본적으로 끄고 필요할 때 수동 deploy한다.
- production main 배포도 로컬 fast/full gate가 통과한 변경만 대상으로 한다.
- staging은 로컬에서 재현하기 어려운 항목에 집중한다: 실제 DB, HTTP, session/cookie, production env, Socket.IO, mobile/runtime smoke.
- transient validation service를 상시 여러 개 유지하지 않는다. 가능한 한 공용 staging 하나를 재사용한다.
- 빌드 캐시를 사용할 수 있으면 사용하고 불필요한 clear-cache build를 반복하지 않는다.
- Render free instance hours, build pipeline minutes, bandwidth는 workspace 공유 예산으로 취급한다.

## 5. 외부 API / AI / 브라우저 자동화

- 동일 입력은 cache/reuse한다.
- 대량 검증 전 작은 representative sample로 먼저 실패 여부를 확인한다.
- 외부 API/AI 호출이 품질을 실질적으로 높이지 않으면 deterministic/local 로직을 우선한다.
- 외부 사이트 교차검증은 개발 CI가 아니라 별도 validation 작업으로 취급한다.
- 브라우저 설치/다운로드는 로컬 환경에서 재사용하고 hosted runner마다 반복 설치하지 않는 방향을 우선한다.

## 6. DB 테스트

- unit/service/repository/transaction 검증은 로컬 DB 또는 격리된 테스트 DB를 우선한다.
- staging DB는 실제 PostgreSQL 동작 차이를 확인해야 할 때 사용한다.
- production DB를 테스트 데이터 정리/대량 검증 용도로 사용하지 않는다.
- 원본/실데이터는 명시적 요청 없이 수정·삭제하지 않는다.

## 7. 변경 유형별 최소 검증

| 변경 유형 | 기본 검증 |
|---|---|
| UI/CSS | syntax/type + 관련 unit + 필요 시 browser smoke |
| API/service | 관련 unit + contract/integration |
| DB/repository | unit + transaction + 필요 시 staging PostgreSQL |
| 인증/결제/권한 | contract + idempotency/transaction/authorization + staging smoke |
| 계산/규칙 엔진 | unit + invariant + 관련 Golden/Oracle |
| MYSTORI game state | state/reconnect/dropout/permission/scoring 관련 테스트 |
| scenario/content | catalog/spoiler/diversity/content QA |
| release | full gate + staging smoke/E2E |

## 8. 구현 규칙

- 새 기능은 테스트를 로컬에서 재현 가능하게 만든다.
- CI 전용 테스트 로직을 만들지 않고 동일한 project command를 로컬과 CI에서 공유한다.
- hosted service가 실패하거나 quota가 없어도 개발이 멈추지 않도록 local fallback을 유지한다.
- 테스트가 오래 걸리면 삭제하지 말고 fast/full/release profile로 분리한다.
- 외부 dependency가 불안정하면 deterministic fixture/cache와 live validation을 분리한다.
- 로그와 실패 원인을 남겨 불필요한 재실행을 줄인다.

## 9. 개발 보조도구/AI 작업 규칙

ChatGPT/Codex 등 개발 보조도구가 코드를 수정할 때도 이 정책을 따른다.

1. 먼저 현재 저장소와 변경 범위를 확인한다.
2. 필요한 검증 프로필을 결정한다.
3. 로컬/정적 분석으로 가능한 작업을 hosted resource에 넘기지 않는다.
4. hosted CI/deploy/API 호출이 필요하면 무료량 영향과 대체 가능성을 먼저 판단한다.
5. 비용 발생 또는 자동 사용량 증가가 예상되면 사용자 승인 없이 활성화하지 않는다.

## 10. 예외

보안, 결제, 개인정보, 데이터 무결성, 실제 production runtime 등 로컬 검증만으로 충분하지 않은 고위험 변경은 무료 사용량 절약보다 정확한 검증을 우선한다. 다만 이 경우에도 필요한 범위만 실행하고 중복 실행을 피한다.
