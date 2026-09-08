# TORI Policy Bootstrap

Applies to: TORI_COMMON / MYSTORI / Untori / Nongtori / future development projects

이 문서는 각 ChatGPT/Codex 개발 세션이 공통 정책을 효율적으로 적용하기 위한 **안정적인 진입점**이다. Project Instructions에는 이 문서의 핵심 규칙만 고정해두고, 세부 정책 버전이 바뀔 때마다 Project Instructions를 다시 복붙하지 않는다.

## 1. 공통 정책의 canonical 위치

공통 정책 Source of Truth는 `conanbke-ai/BKE`의 최신 `main`에 둔다.

- `TORI_POLICY_BOOTSTRAP.md` — 상시 적용 core / 정책 적용 방식
- `DEVELOPMENT_COORDINATION_POLICY.md` — 병렬 개발, branch/WIP/lease, merge 운영
- `DEVELOPMENT_RESOURCE_POLICY.md` — GitHub Actions/Render/API/비용형 리소스
- `POLICY_ROUTER.md` — 작업 유형별 필요한 상세 정책 선택
- `SECURITY_STANDARD.md` — Secure SDLC / 보안 기준
- `POLICY_CHANGELOG.md` — 정책 변경의 영향과 적용 시점
- `POLICY_VERSION_MATRIX.md` — 프로젝트별 정책 호환 상태

제품의 실제 구현 상태는 각 제품 저장소의 최신 `main`, `AGENTS.md`, `ACTIVE_WORK.md`, open PR, diff가 우선한다.

## 2. 매 기능마다 정책 전체를 다시 읽지 않는다

개발 세션은 다음을 상시 기억/적용한다.

1. 중복 구현 금지
2. 기존 canonical workstream 재사용
3. branch는 `main` 포함 최대 5개
4. ACTIVE workstream 최대 3개
5. validation branch 최대 1개
6. 동일 기능/핵심 path lease 최대 1개
7. Acceptance Criteria First
8. Contract First
9. 실행하지 않은 테스트를 PASS라고 보고하지 않음
10. server-side authorization / secret·개인정보 보호
11. destructive action은 사용자 승인 필요
12. local-first validation / 비용형 리소스 절약
13. 작업 완료 시 `ACTIVE_WORK.md`/handoff 갱신

세부 정책은 `POLICY_ROUTER.md`가 요구하는 부분만 확인한다.

## 3. Full Preflight와 Delta Preflight

### Full Preflight

다음 경우 수행한다.

- 새 채팅/새 세션의 첫 workstream
- NEW workstream
- canonical branch/PR이 불명확
- HIGH risk 변경
- Integration Window / release
- 다른 workstream과 충돌 가능
- 정책 baseline 이후 MAJOR/EMERGENCY 변경 존재

확인 순서:

`latest main -> README/docs/AGENTS -> ACTIVE_WORK -> open PR -> branch/WIP -> recent commits -> changed files/path lease -> 관련 코드/contract -> security/resource impact`

그 뒤 `ALREADY_DONE / IN_PROGRESS / NEW / BLOCKED`를 판정한다.

### Delta Preflight

같은 세션에서 같은 canonical workstream을 계속 수정하고 이전 Full Preflight 이후 다음이 유지되면 사용한다.

- branch/PR 동일
- lease 동일
- 주요 contract 동일
- 공통 정책 baseline 동일
- 새 충돌 PR 없음

확인:

`main HEAD delta -> ACTIVE_WORK delta -> open PR delta -> branch/WIP -> lease -> contract delta`

변화가 크면 Full Preflight로 승격한다.

## 4. Workstream Policy Baseline

새 workstream을 시작할 때 `ACTIVE_WORK.md`에 가능하면 다음을 기록한다.

`Policy baseline: conanbke-ai/BKE@<commit SHA>`

이 baseline은 해당 workstream이 시작할 때 적용한 공통 정책 스냅샷이다.

### 현재 workstream 중 정책이 변경된 경우

기본적으로 진행 중인 작업을 멈추고 새 정책을 전부 다시 적용하지 않는다.

- PATCH: 현재 작업에 즉시 반영 불필요
- MINOR: 관련 CHANGE_TAG인 경우 다음 자연스러운 검토 시 반영
- MAJOR: 다음 Integration Window 또는 새 workstream부터 반영
- EMERGENCY_SECURITY: 관련 active workstream에 즉시 적용

즉 **현재 진행 중인 작업은 baseline 기준으로 계속 진행하되, 긴급 보안 규칙만 예외적으로 즉시 적용**한다.

## 5. Policy Delta Gate

Integration/merge 시 전체 정책을 재독하지 않는다.

1. workstream의 `Policy baseline` 확인
2. 현재 BKE main과 baseline 사이 `POLICY_CHANGELOG.md` 변경만 확인
3. 해당 workstream의 CHANGE_TAG와 관련된 변경만 적용
4. MAJOR/EMERGENCY 영향이 있으면 필요한 검증 추가
5. baseline을 새 main 기준으로 갱신

## 6. 작업 시작 분류

작업 시작 시 내부적으로 다음을 판정한다.

```text
STATUS: ALREADY_DONE | IN_PROGRESS | NEW | BLOCKED
CHANGE_TAGS: UI, AUTH, DB, ...
RISK: LOW | MEDIUM | HIGH
CANONICAL: branch / PR / main
LEASE: path/domain
POLICY_BASELINE: BKE@SHA
REQUIRED_POLICY: CORE + routed policies
VALIDATION: minimum required checks
```

사용자에게 매번 전체 표를 장황하게 보여줄 필요는 없지만, 새 branch 생성/충돌/HIGH risk이면 판단 근거를 명확히 한다.

## 7. Security 책임 분리

- TORI_COMMON: 보안 정책, threat model, cross-project audit, HIGH-risk 독립 리뷰
- 제품 프로젝트: 실제 제품 보안 코드 구현과 regression test

보안이 공통이라는 이유로 TORI_COMMON에서 제품 기능을 별도 branch로 재구현하지 않는다.

HIGH risk 흐름:

`제품 프로젝트 구현 -> 프로젝트 security regression -> TORI_COMMON/독립 review -> PASS/FIX_REQUIRED/BLOCKED -> merge`

## 8. Project Instructions는 고정 부트로더로 유지

Project Instructions에 정책 version 번호를 박아넣지 않는다.

Project Instructions는 다음만 고정한다.

- 공통 정책 canonical은 `conanbke-ai/BKE`의 이 bootstrap을 시작점으로 함
- 실제 구현 Source of Truth는 해당 제품 GitHub repo
- Preflight / branch-WIP-lease / 중복개발 금지
- Router 기반 상세 정책 선택
- HIGH risk 보안 검토
- 실행하지 않은 테스트 PASS 금지
- destructive action 승인 필요

공통 정책의 PATCH/MINOR 업데이트 때문에 Project Instructions를 다시 복붙하지 않는다.

## 9. 정책 접근 실패 시 fallback

일반 LOW/MEDIUM 작업에서 BKE 공통 정책을 일시적으로 읽지 못해도, Project Instructions + 제품 `AGENTS.md` + `ACTIVE_WORK.md`의 core guardrail을 우선 적용한다.

다만 HIGH risk, release, integration 또는 정책 충돌이 의심되는 작업에서는 canonical 공통 정책 확인 없이 임의 진행하지 않는다.

## 10. 새 프로젝트

향후 새 프로젝트도 동일한 bootstrap을 사용한다.

프로젝트별로 새 공통 정책 사본을 만들기보다:

- 고정 Project Instructions
- repo `AGENTS.md`
- repo `ACTIVE_WORK.md`
- BKE common policy reference

구조를 사용한다.
