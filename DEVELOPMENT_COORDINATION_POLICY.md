# 공통 개발 작업 조정 정책

이 문서는 ChatGPT, Codex 및 다른 개발 보조도구가 여러 대화창/세션에서 같은 저장소를 동시에 다룰 때 중복 구현, 브랜치 난립, 이미 만든 기능의 재개발을 방지하기 위한 공통 규칙이다.

## 1. 작업 시작 전 Preflight는 의무

새 코드 수정 전에 반드시 다음을 먼저 확인한다.

1. 현재 `main`의 실제 구현 상태
2. open PR 목록과 각 PR의 목적
3. 현재 branch 목록에서 동일/유사 목적 branch 존재 여부
4. 최근 commit에서 같은 기능이 이미 구현됐는지
5. `AGENTS.md`, 관련 설계 문서, migration 문서
6. 수정하려는 파일이 다른 open PR에서 이미 변경 중인지

이 확인 없이 새 branch 또는 새 구현을 시작하지 않는다.

## 2. 새 branch 생성은 기본값이 아니다

다음 우선순위를 적용한다.

1. 동일 목적의 기존 open PR/branch가 있으면 그 작업을 이어간다.
2. 기존 branch가 목적은 같지만 기준본이 오래된 경우, 새 branch를 만들기 전에 기존 작업을 재사용/통합할 방법을 먼저 검토한다.
3. main에 이미 구현된 기능이면 새로 개발하지 않고 검수/리팩토링/보완만 한다.
4. 완전히 독립된 신규 기능이고 기존 작업과 충돌하지 않을 때만 새 branch를 만든다.

`v2`, `v3`, `final`, `final2`, `actual`, `real`, `implementation`처럼 같은 목적의 branch를 반복 생성하지 않는다.

## 3. 한 기능 = 하나의 active workstream

같은 기능/화면/도메인에 대해 동시에 여러 active branch를 만들지 않는다.

예:
- 로그인 UI 재구현
- 회원 홈
- 결제/당근
- MYSTORI 인증 persistence
- scenario grading
- TORI 디자인 시스템

각 항목은 원칙적으로 하나의 canonical branch/PR만 active로 둔다.

## 4. 새 작업이 들어오면 먼저 기존 구현을 판정

작업 요청을 받으면 아래 셋 중 하나로 분류한다.

- `ALREADY_DONE`: main 또는 active PR에 이미 구현되어 있음 → 재개발 금지, 검수/보완만
- `IN_PROGRESS`: open PR/branch에서 진행 중 → 해당 workstream을 이어감
- `NEW`: 기존 구현/진행 작업이 없음 → 이때만 신규 구현 가능

판정 근거를 코드/PR/commit에서 확인한다.

## 5. 파일 충돌 방지

새 작업 전 open PR의 changed files를 확인한다.

- 동일 핵심 파일을 다른 active PR이 수정 중이면 별도 branch에서 동시에 수정하지 않는다.
- 반드시 기존 PR에 이어 붙이거나, 선행 PR 병합 후 후속 작업으로 분리한다.
- 병렬 작업은 파일/도메인이 명확히 분리될 때만 허용한다.

## 6. active work registry

각 주요 저장소는 `ACTIVE_WORK.md`를 유지한다.

항목:
- workstream
- canonical branch
- PR
- 상태
- 수정 범위
- 건드리면 안 되는 영역
- 다음 단계

새 작업 시작/종료/병합 시 registry를 갱신한다.

## 7. branch 정리 원칙

브랜치 삭제는 사용자 승인 없이 하지 않는다. 대신 다음을 식별한다.

- merged/obsolete candidate
- same-SHA duplicate branch
- superseded branch
- validation-only branch
- active canonical branch

정리 대상 목록을 먼저 제시하고, 사용자가 승인하면 삭제한다.

## 8. PR 정책

- 하나의 기능에 중복 PR을 열지 않는다.
- 이미 open PR이 있으면 가능하면 기존 PR을 갱신한다.
- 일회성 validation PR은 `validation-only`로 명확히 구분하고 운영 merge 대상과 섞지 않는다.
- draft PR은 미완성/통합 전 상태 표시용으로 사용한다.

## 9. ChatGPT/Codex 작업 규칙

모든 개발 세션은 다음 순서로 움직인다.

`Preflight -> 상태 판정 -> 기존 workstream 재사용 -> 최소 변경 -> 로컬 검증 -> registry 갱신`

절대 다음 순서로 움직이지 않는다.

`요청 받음 -> 새 branch 생성 -> 비슷한 코드 재작성 -> 또 PR 생성`

## 10. 사용자 확인이 필요한 경우

다음 경우에는 구현 전에 사용자에게 선택을 요청한다.

- 서로 다른 두 active PR이 같은 기능을 구현 중인데 어느 쪽을 canonical로 둘지 불명확함
- branch 정리/삭제가 필요한 경우
- 기존 구현을 버리고 재설계해야 하는 경우
- 대규모 rebase/merge로 다른 진행 작업에 영향을 줄 수 있는 경우

## 11. 완료 기준

작업이 끝났다고 판단하려면:

1. canonical branch/PR이 명확해야 한다.
2. 중복 구현을 새로 만들지 않았어야 한다.
3. 관련 local quality gate를 통과해야 한다.
4. `ACTIVE_WORK.md`가 현재 상태를 반영해야 한다.
5. 후속 작업은 기존 branch를 이어갈지, 병합 후 새 작업으로 갈지 명확해야 한다.
