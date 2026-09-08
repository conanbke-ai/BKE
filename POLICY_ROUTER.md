# TORI Policy Router

Protocol: stable-1
Owner: TORI_COMMON

이 파일은 규칙의 두 번째 사본이 아니라 조회 목차다. 세션·캐시·변경 적용 방식은 `TORI_POLICY_BOOTSTRAP.md`를 따른다. SHA와 읽은 범위가 동일하고 컨텍스트에 남아 있으면 재독하지 않는다.

## 실행형 조정 도구 위치 — 2026-09-08

Work Guard 구현은 [BKE PR #2](https://github.com/conanbke-ai/BKE/pull/2), `work/coordination-guard`의 `tools/work_guard/`에 있다. 사용·인계·복구는 해당 branch의 `docs/WORK_GUARD.md`, 실제 검증 범위는 `docs/WORK_GUARD_VALIDATION.md`를 읽는다. 같은 도구를 제품마다 새로 구현하지 않는다.

현재 상태는 구현/로컬 81 tests PASS, 독립 검토·실 adapter 전체 확인·제품별 초기 전환 대기다. PR이 main에 들어오기 전 이미 전체 적용되었다고 가정하지 않는다. 기존 제품 작업은 그대로 유지하고, 검토 후 다음 정상 checkpoint에서 기존 작성자를 확인하여 init/HOLD/adopt한다. 새 Project Instructions 복사나 정책팩 업로드를 요구하지 않는다. 코드 수정자는 도구의 실제 실행과 CAS 성공을 확인해야 하며 plan만으로 예약됐다고 주장하지 않는다.

## 판단

`STATUS / CHANGE_TAGS / RISK / CANONICAL / OWNER-LEASE / POLICY_BASELINE / VALIDATION`

태그는 파일명 대신 실제 동작·정보 흐름을 기준으로 붙인다. 로그인 화면의 색상만 바꾸는 작업은 UI/LOW일 수 있지만 token 저장·cookie·복구·API 요청 처리가 바뀌면 AUTH/SESSION 등의 보안 태그를 추가한다. 보안 문서의 오탈자는 DOCS일 수 있다. 불확실한 영향은 필요한 코드만 더 읽어 판단한다.

## 공통 규칙

중복 구현 금지, branch 5/WIP 3/validation 1, 단일 작성자 lease, Acceptance Criteria, Contract First, 실행 근거 없는 PASS 금지, 비밀정보 보호, 서버 인가, 파괴적 작업 승인, local-first는 항상 적용한다.

## 라우팅

| 실제 변경 | 상세 문서·절 | 검증 방향 |
|---|---|---|
| DOCS / POLICY | 이 파일, bootstrap, changelog | 링크·기존 규칙·버전/적용 시점 일관성 |
| UI / UX / ACCESSIBILITY | 제품 UI docs, TORI_UI_SYSTEM_STANDARD.md | 관련 화면·입력·focus·모바일·reduced-motion; raw HTML이면 SEC-05 추가 |
| API / SERVICE / DOMAIN / REPOSITORY | 제품 architecture/contract, DEVELOPMENT_COORDINATION_POLICY.md | unit·consumer·에러 회귀; 사용자 자원이면 SEC-02/04 |
| AUTH / AUTHZ / ACCOUNT_RECOVERY / SESSION | SECURITY_STANDARD.md SEC-01/02/03/07/10 | cross-user·만료·재사용·회수·CSRF 등 관련 negative tests |
| ADMIN | SEC-02/07/10/12 | 권한 상승 거부·민감 작업 감사 |
| PAYMENT / REFUND / WALLET / LEDGER / WEBHOOK | SEC-08, 제품 가격·원장 계약 | 금액·순서·경합·중복·재시도·환급·서명 |
| PRIVACY / PII / MATCHING | SEC-02/09/10, 제품 동의·차단·보존 계약 | 접근 범위·민감정보 노출·export/delete 영향 |
| DB / MIGRATION | SEC-13, 제품 migration docs | forward/호환·rollback/restore·lock·transaction |
| STATE / SOCKET / SCENARIO | SEC-02/04/07/14, 제품 state/event/content docs | 역할별 payload·reconnect·revocation·version pinning |
| FILE_UPLOAD | SEC-02/04/05/06/07 | 크기·형식·압축해제·경로·저장/다운로드 인가 |
| EXTERNAL_API / AI_PROVIDER | SEC-04/06/09/10/15, 제품 Adapter 계약 | timeout·응답검증·retry/replay·PII·도구 권한 |
| SENSOR / WEATHER / IMAGE / DATA_PIPELINE / MODEL | 제품 schema/Adapter/Strategy, SEC-04/09/14 | 단위·시간·출처·결측·원본/가공·모델 검증 |
| DEPENDENCY / CI / RENDER | SEC-11/10, DEVELOPMENT_RESOURCE_POLICY.md | lockfile·권한·secret·trigger·추가 비용/배포 영향 |
| RELEASE / INTEGRATION | bootstrap §6/8, SEC-16, 제품 Release Gate | 현재 통합 후보 SHA 테스트·리뷰·rollback |
| SECURITY / HOTFIX | 관련 SEC 절, SEC-16, bootstrap §5 | 실제 위험 범위 차단·원인·회귀·예외 기록 |

LOW/MEDIUM은 보안 면제라는 의미가 아니다. 인증/인가/결제/민감정보/관리자/신뢰 경계/파괴적 DB 변경의 동작이 바뀌면 HIGH로 취급하고 관련 보안 리뷰를 연결한다. 단순 태그 추가 때문에 무관한 저장소 전체 Preflight를 반복하지 않는다.

## 책임 분기

정책·공통 감사·PR 보안 리뷰 → TORI_COMMON.
실제 제품 코드·테스트 → 해당 제품 canonical workstream.
외부 리뷰 결과는 원래 PR에 전달하고 새 branch나 중복 구현을 만들지 않는다.

## 읽기 예산

첫 시작에는 bootstrap/router와 필요한 정책 절만 읽는다. 후속 수정에는 제품 상태 delta만 확인한다. 병합/인계 때 baseline 이후 관련 changelog를 확인한다. 외부 도구 접근이 실패하면 bootstrap의 범위 제한 fallback을 적용하고 최신 확인을 한 것처럼 말하지 않는다.
