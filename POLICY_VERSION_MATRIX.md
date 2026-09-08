# TORI Policy Delivery Matrix

Owner: TORI_COMMON
Protocol: stable-1
Checked: 2026-09-08

## 게시 경로

TORI_COMMON은 관리 주체이고 `conanbke-ai/BKE`는 승인 정책 게시처다. bootstrap/router/security/changelog는 같은 게시 commit에서 읽는다. 정책을 실제 채택한 SHA는 각 workstream/PR에 기록하며, 이 표의 target 문자열만 보고 읽었다고 판단하지 않는다.

| 문서 | 역할 |
|---|---|
| DEVELOPMENT_TEAM_OPERATING_POLICY.md | 기존 AGENTS 호환 진입점과 팀 운영 상세 |
| TORI_POLICY_BOOTSTRAP.md | 세션/캐시/적용 시점/충돌 처리 |
| POLICY_ROUTER.md | 변경별 필요한 절 선택 |
| DEVELOPMENT_COORDINATION_POLICY.md | 협업·branch·WIP·통합 상세 |
| DEVELOPMENT_RESOURCE_POLICY.md | 비용·무료량 |
| SECURITY_STANDARD.md | 보안 구현·리뷰 기준 |
| POLICY_CHANGELOG.md | 변경 범위·시점·관련 행동 |

## 확인된 연결과 미확인 수신

| 프로젝트 | 저장소 AGENTS 연결 | 확인한 AGENTS blob SHA | 실제 세션 baseline 수신 | ChatGPT 설정/업로드 |
|---|---|---|---|---|
| Untori | EXISTING_REFERENCE_VERIFIED → BKE 팀 운영 문서 | 30811c3b05dc4cfdd3d0b9ae815685f83054335b | PENDING_ACK | NOT_INSPECTED |
| MYSTORI | EXISTING_REFERENCE_VERIFIED → BKE 팀 운영 문서 | 50fb384c197c3b7b8f2282a4b142fdb1c9283431 | PENDING_ACK | NOT_INSPECTED |
| Nongtori | EXISTING_REFERENCE_VERIFIED → BKE 팀 운영 문서 | e0138214e429146f6a2b3a0cd29f8dd366a57649 | PENDING_ACK | NOT_INSPECTED |
| 향후 프로젝트 | 최초 AGENTS 설정에서 동일 진입점 연결 | 미정 | NOT_ONBOARDED | NOT_INSPECTED |

위 확인은 제품 코드·보안·배포의 감사 결과가 아니다. 세 제품의 AGENTS/ACTIVE_WORK/branch를 이 정책 배포에서 덮어쓰지 않는다. 다른 채팅의 실행 상태는 추정하지 않는다.

## 수신 확인

실제 담당 세션이 다음 checkpoint에 조회했을 때만 기존 ACTIVE_WORK 또는 PR handoff에 다음을 남긴다.

`POLICY_ACK: BKE@<실제 조회 commit>; tags=<범위>; workstream=<id>; owner=<세션>; result=<ADOPTED|DEFERRED|BLOCKED>`

이 문구 자체를 매번 사용자가 복붙할 필요는 없다. 개발 담당 세션이 작업 기록에 작성한다. 중앙 표는 정책 배포/감사 시 그 근거를 확인하여 갱신하며 매 commit마다 쓰지 않는다.

- EXISTING_REFERENCE_VERIFIED: AGENTS의 참조 경로를 읽어 확인함.
- PENDING_ACK: 진행 중/다음 세션이 새 정책을 읽었는지 아직 확인하지 못함.
- ADOPTED: 실제 조회 SHA와 적용 범위에 대한 근거 있음.
- DEFERRED: 일반 정책 변경을 다음 지정 checkpoint로 미룸.
- BLOCKED: 접근/정책 충돌/필수 보안 gate를 해결해야 함.

참조 경로가 있다는 이유로 모든 대화창이 자동 업데이트되었다고 표시하지 않는다. Project-only/default memory 여부를 도구 권한이나 정책 전달 완료 증거로 쓰지 않는다.
