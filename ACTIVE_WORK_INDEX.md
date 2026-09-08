# Cross-Project Active Work Index

새 ChatGPT/Codex 세션은 개발 시작 전에 각 저장소의 `ACTIVE_WORK.md`와 open PR을 확인한다. 이 파일은 프로젝트 간 빠른 진입용 인덱스다.

## Untori

- 로그인 우선 홈·게스트 UX: PR #16 `feat/auth-first-home-actual`
- 명리 신강·용신 정책 v2: PR #18 `feature/myeongri-policy-v2`
- TORI UI Design System v1: PR #19 `ui/tori-design-system-v1`
- Forceteller PR #15, #17: validation-only, 운영 기능 개발 branch로 사용 금지

주의: 로그인/홈 UI는 PR #16과 PR #19의 변경 범위가 겹칠 수 있으므로 새 branch 생성 금지. changed files 비교 후 canonical 통합 경로를 결정한다.

## MYSTORI

- TORI UI Design System v1: PR #37 `ui/tori-design-system-v1`

새 presentation/UI 작업은 별도 branch를 만들기보다 PR #37을 먼저 검토한다.

## Nongtori

- TORI UI System v1: PR #1 `ui/tori-design-system-v1`

초기 구현 단계이므로 UI foundation을 다시 설계하는 별도 branch를 만들지 않는다.

## 공통 규칙

상세 규칙은 `DEVELOPMENT_COORDINATION_POLICY.md`를 따른다.

`Preflight -> ALREADY_DONE/IN_PROGRESS/NEW 판정 -> 기존 workstream 재사용 -> 최소 변경 -> 로컬 검증 -> ACTIVE_WORK 갱신`
