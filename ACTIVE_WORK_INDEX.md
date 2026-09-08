# Cross-Project Active Work Index

새 ChatGPT/Codex 세션은 개발 시작 전에 각 저장소의 `ACTIVE_WORK.md`, open PR, branch 목록을 확인한다. 이 파일은 프로젝트 간 빠른 진입용 인덱스이며, 실제 최신 상태는 각 저장소의 코드/PR/`ACTIVE_WORK.md`가 우선한다.

## 공통 운영 한도

- Branch budget: `main` 포함 최대 **5개**
- Active workstream: 최대 **3개**
- Validation branch: 동시 최대 **1개**
- 같은 기능/화면/핵심 경로: active lease 최대 **1개**
- branch가 5개면 새 branch 생성 금지. 기존 작업을 먼저 merge/close/supersede/cleanup한다.
- `v2/v3/final/final2/actual/real/implementation/new` 식의 동일 목적 branch 증식 금지
- merged snapshot 보존은 `backup/*` branch보다 Git tag 우선

## Untori

- 현재 다른 개발 세션에서 branch 통합/정리가 진행 중인 저장소다.
- 통합이 끝나기 전에는 새 branch 생성이나 기존 active branch 재설계를 시작하지 않는다.
- 새 세션은 반드시 Untori의 최신 `ACTIVE_WORK.md`, open PR, branch 목록을 다시 읽고 현재 canonical workstream을 확인한다.
- 이전 인덱스의 PR/branch 정보는 통합 과정에서 바뀔 수 있으므로 이 파일만 보고 수정하지 않는다.

상태: `INTEGRATION_LOCK`

## MYSTORI

- TORI UI Design System v1: PR #37 `ui/tori-design-system-v1`
- UI branch는 main과 병렬 변경이 있어 통합 전 최신 main 동기화가 필요할 수 있다.
- 새 presentation/UI 작업은 별도 branch를 만들지 말고 PR #37을 canonical workstream으로 본다.
- main이 계속 이동하는 동안 반복 rebase/merge하지 않고 Integration Window에서 한 번에 통합한다.

상태: `ACTIVE / INTEGRATION_PENDING`

## Nongtori

- TORI UI System v1: PR #1은 main에 병합되어 baseline이 되었다.
- 동일 foundation을 새 branch에서 다시 구현하지 않는다.
- 실제 앱 기능이 시작될 때만 `ACTIVE_WORK.md`에서 NEW 판정 + branch slot + lease 확인 후 새 workstream을 만든다.
- 병합된 `ui/tori-design-system-v1` branch는 사용자 승인 후 cleanup 대상이다.

상태: `MERGED_BASELINE`

## 세션 시작 표준

`main -> ACTIVE_WORK -> open PR -> branches/budget -> recent commits -> changed files/lease -> ALREADY_DONE/IN_PROGRESS/NEW -> Acceptance Criteria -> 구현`

상세 규칙은 `DEVELOPMENT_COORDINATION_POLICY.md`와 `DEVELOPMENT_RESOURCE_POLICY.md`를 따른다.
