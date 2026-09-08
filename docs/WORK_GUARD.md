# TORI Work Guard — 다중 대화 작업 예약 도구

Version: 1.0.0 / 2026-09-08
Owner: TORI_COMMON
Implementation: `tools/work_guard/` (Python 3.10+ 표준 라이브러리만 사용)

## 목적과 적용 범위

대화 수가 아니라 **동시에 쓰는 작업**을 제한한다. 프로젝트마다 구현 2개를 기본으로, 최대 3개와 validation 1개까지 허용한다. 원격 브랜치의 상한은 main 포함 5개다. 리뷰·설계·읽기에는 작업 브랜치가 필요 없다.

규칙은 각 제품의 `main:ACTIVE_WORK.md` 끝에 붙는 managed JSON과 실제 GitHub refs/PR을 함께 읽어 검사한다. 기존 Markdown 본문은 byte 단위로 보존한다. JSON은 예약의 정식 상태이고 기존 본문은 전환 전 기록/계약이다. 기존 본문이 다른 세션에 의해 변경되면 조용히 무시하지 않고 lead의 `reconcile` 전까지 신규 변경을 거절한다.

**새 Project Instructions 복사나 제품 코드 전체 재작성은 필요 없다.** BKE의 기존 정책 진입점에서 이 도구를 찾는다. 그러나 파일을 게시했다고 실행 중인 다른 대화가 자동으로 멈추거나 도구를 실행하는 것은 아니다. 제품별 담당 세션이 다음 checkpoint에 inventory를 검토하고 전환한다. 현재 진행 작업의 소유자를 추정하여 강제 등록하지 않는다.

## 구현한 보호 장치

- `feature` 키, 브랜치, 파일/디렉터리, 공유 contract 범위의 중복 예약 거절.
- 같은 registry blob SHA를 읽은 두 예약은 CAS 저장에서 한 개만 성공. 실패한 요청은 자동 재시도하지 않는다.
- 실제 브랜치 + 아직 생성 전인 예약 슬롯을 합산. READY/BLOCKED/HANDOFF 등 미완료 작업도 WIP에 포함.
- 기존 브랜치는 무단 재사용하지 않고 reviewed import → HOLD → 명시적인 이전 작성자 종료 → adopt.
- 파일은 exact path 또는 terminal `/**`만 허용. 경로 탈출·임의 glob·root wildcard 신규 예약 거절. 경합 검사에서는 Windows 호환을 위해 대소문자 차이를 보수적으로 취급.
- 동일 브랜치의 작성자는 한 명. 인계 시 epoch를 증가시켜 이전 작성자의 오래된 요청을 거절.
- `begin-write → 실제 한 커밋 → finish-write` 동안 쓰기 중 상태를 유지. SHA, 단일 부모, 전체 변경 경로와 rename의 이전 경로도 확인.
- main 변경으로 branch가 뒤처지면 `sync`에서 예약 상태를 유지한 채 pinned main을 병합하고 부모 SHA를 확인. 검증 결과는 다시 제출.
- test/security review는 작업 HEAD + main의 코드 fingerprint에 연결. registry만 갱신되었다고 기존 제품 테스트를 전부 무효화하지 않는다.
- PR merge-base의 코드가 현재 main 코드와 다른 경우 `BRANCH_NEEDS_SYNC`. 오래된 브랜치에서 테스트만 다시 표시해 통합하지 못함.
- HIGH risk는 다른 reviewer 세션의 PASS 기록이 필요. SELF_REVIEW, 미실행/실패 테스트, 다른 SHA 증거, draft/mergeable 미확인 PR을 차단.
- merge는 등록한 lead만 시작. 저장소별 integration lock 하나, 예상 PR HEAD, 실제 merge commit 부모와 main 포함 여부 검증.
- crash/timeout/응답 유실 시 자동 unlock/재시도하지 않음. 실제 결과를 확인한 finish/abort로 복구.
- registry가 손상·과도한 크기·미지원 schema이거나 PR/branch pagination이 불완전하면 fail-closed.

## 중요한 한계

이것은 **협조하는 개발 세션 사이의 실행형 guard**다. 같은 GitHub 계정/토큰으로 raw push, Contents API, branch 생성, merge를 직접 실행하는 우회 경로까지 GitHub 서버 ACL로 막지는 않는다. actor/session 문자열도 사람의 인증이 아니라 협업 식별자다. 모든 쓰기를 별도 신뢰 서비스로 강제하는 권한 구조는 이번에 도입하지 않았다.

서로 다른 feature 키와 누락된 경로/contract로 같은 기능을 요청한 경우까지 AI 의미론으로 자동 검출하지 않는다. 개발 세션의 실제 코드 검색, 목적 정규화와 경로/contract 신고가 선행되어야 한다. 브랜치만 보고 feature가 미구현이라고 판단하지 않는다.

registry 저장과 제품 branch ref/PR merge는 단일 분산 transaction이 아니다. in-flight 상태는 협조 세션의 인계·중복 효과를 막으며, 외부 우회 쓰기는 부모/HEAD/범위 검사에서 탐지한다. GitHub PR merge API는 expected head만 받으므로 bypass 사용자가 main을 동시에 변경하는 모든 순간을 사전에 차단할 수 없다. 예상 밖 base는 finish에서 검증 실패로 남기고 이미 병합됐는데 성공/rollback 완료라고 거짓 보고하지 않는다.

`tests`는 실행된 테스트의 **증거 제출**이지 테스트 실행기나 암호학적 인증이 아니다. 실제 명령·결과·보고서를 읽은 담당자가 기록해야 한다. 다른 AI 대화의 review도 외부 보안 전문가 인증과 같지 않다.

현재 구현은 `main` 기준 저장소, text add/update, merge-commit 방식만 지원한다. 파일 삭제/rename 실행, branch 삭제, force/reset, 자동 hotfix 상한 해제, raw 배포, security exception 자동 승인, 비밀정보 조회는 제공하지 않는다. fork PR, API의 파일 수 상한, 미확정 mergeability 등은 안전하게 중단한다. 필요한 파괴적 작업은 별도 승인 절차다.

## 실행

BKE checkout 루트에서 실행한다. 별도 pip 설치·서버·GitHub Actions·Render가 필요 없다.

```bash
python -m unittest discover -s tests -p 'test_work_guard.py' -v
python -m tools.work_guard --help
python -m tools.work_guard inspect --repo conanbke-ai/Mystori_Project > snapshot.json
python -m tools.work_guard plan --snapshot snapshot.json --request request.json
python -m tools.work_guard apply --repo conanbke-ai/Mystori_Project --request request.json --yes
```

직접 REST 모드는 개발 환경의 `GH_TOKEN` 또는 `GITHUB_TOKEN`을 사용한다. private repo 읽기와 명시적으로 승인한 쓰기에는 최소 Contents/Pull requests 권한을 사용한다. 토큰을 채팅·파일·CLI 인수에 넣지 않는다. `--yes`는 그 요청의 효과를 승인하는 것이지 계정 전체 변경 승인이 아니다. credential 자동 추출이나 추가 결제를 요구하지 않는다.

`inspect`/`plan`/`check`는 예약을 저장하지 않는다. `apply`만 변경한다. raw `plan` 결과의 connector_write가 성공하기 전에는 브랜치/코드를 수정하면 안 된다.

## 연결된 GitHub 도구만 있는 대화

로컬 REST 인증이 없어도 offline 엔진을 사용할 수 있다. GitHub connector로 fresh snapshot을 모아 JSON으로 저장하고 `plan`을 실행한다. 출력 `connector_write`를 기존 `GitHub.update_file`에 넘긴다. SHA가 null인 최초 파일 생성만 `create_file`을 쓴다. 409/422 충돌 시 최신 SHA만 바꿔 덮어쓰지 말고 새 상태에서 충돌 목적부터 판단한다.

저장 응답과 새 registry의 request receipt/소유자/epoch를 확인한 다음에만 다음 효과를 실행한다. code write는 `begin-write` 예약 저장 → fresh `check` → tree/commit + non-force ref → actual diff proof → `finish-write` 저장 순서다. 정책 문서만 읽고 직접 우회 write를 하지 않는다.

offline snapshot은 도구가 실제 읽은 자료여야 한다. 수동 JSON은 출처를 암호학적으로 증명하지 않으므로 없는 내용을 만들어 넣어 PASS를 얻지 않는다. Python 실행 자체가 불가능한 세션은 읽기·리뷰로 제한하거나 실제 도구를 실행할 수 있는 담당자에게 인계한다. 사용자가 정책을 재복사하는 방식으로 해결하지 않는다.

### Snapshot 형식

`inspect` 출력의 `snapshot` 객체를 그대로 사용할 수 있다.

- `repo`: owner/repo
- `main_head`: 정확한 main commit SHA
- `base_code`: root tree에서 ACTIVE_WORK.md 항목만 제외한 `{path,mode,type,sha}` 목록을 path순 정렬, JSON sort_keys/separators=(',', ':')로 직렬화하여 SHA-1. 구현은 `GitHub.code_fingerprint`.
- `document`, `registry_sha`: 동일 main SHA에서 읽은 원문과 blob SHA. 파일 부재는 tree/API로 확인했을 때만 빈 문자열/null.
- `branches`: 전체 페이지의 이름 → HEAD SHA. main은 main_head와 같아야 함.
- `prs`: 모든 open PR의 number/branch/head/base/files/complete/draft/mergeable/merge_base_code. files는 모든 변경 파일과 rename 이전 경로. merge_base_code는 main...PR의 merge-base commit의 동일 fingerprint.
- `complete`: 실제 pagination을 끝냈을 때만 true.
- `observed_at`: 실제 조회 시간 ISO-8601 with timezone. 5분 이상 된 snapshot은 거절.
- 복구 요청에 필요한 경우 `write_proof`, `sync_proof`, `merge_proof`: adapter의 함수와 같은 실제 Git 근거.

## 최초 전환 — 현재 작업 보존

1. 제품 main/AGENTS/ACTIVE_WORK, 모든 branch와 open PR, 최근 관련 코드를 읽는다.
2. 기존 ACTIVE_WORK의 모든 활성 작성자·인계 여부를 확인한다. main에서 다른 세션이 직접 쓰고 있는 경우 종료 전 초기 전환을 선언하지 않는다.
3. `inspect`의 inventory_id, 실제 검토 요약, `legacy_writers_accounted_for: true`와 함께 `init` 요청을 만든다.
4. open PR은 자동 HOLD로 등록한다. PR 없는 실제 작업 브랜치는 imports로 명시한다. 단순히 목록에 있는 과거 브랜치 전체를 활성 작업이라고 추정하지 않는다.
5. lead가 이전 작성자 종료를 확인한 작업만 `adopt`한다. 담당자가 아직 작업 중이면 HOLD를 유지한다.
6. 전환 전 Markdown은 유지하되 그 본문을 각 branch에서 별도로 갱신하지 않는다. 변경이 생기면 reviewed `reconcile` 후 진행한다.

```json
{
  "action": "init",
  "actor": "project-integration-lead",
  "request_id": "unique-init-id",
  "inventory_id": "inspect에서 확인한 실제 값",
  "inventory_review": "검토한 활성 작업/담당자/관련 PR과 근거",
  "legacy_writers_accounted_for": true,
  "imports": []
}
```

이 도구 구현 배포가 세 제품의 초기 전환까지 완료했다는 뜻은 아니다. 담당자가 모르는 작업을 덮어쓰는 자동 init은 금지다.

## 일상 흐름과 요청

모든 변경 요청에는 고유 request_id, actor, 최신 revision이 필요하다. 작성자 동작에는 task와 현재 epoch도 필요하다. revision은 registry의 동시 변경 방지 번호, epoch는 작성자 인계 차수이며 의미가 다르다.

```json
{
  "action": "claim",
  "actor": "mystori-ui-session-a",
  "task": "UI-SIGNUP-01",
  "request_id": "unique-request-id",
  "revision": 1,
  "branch": "work/signup-layout",
  "feature": "mystori/signup-layout",
  "paths": ["src/web/auth/", "tests/auth-ui/"],
  "contracts": ["ui/signup-layout"],
  "tags": ["UI"],
  "risk": "LOW",
  "kind": "implementation",
  "acceptance": "승인된 회원가입 화면 구성; 기존 인증 API/권한 보존",
  "preflight_evidence": "실제로 확인한 코드/PR/계약 근거",
  "dependencies": []
}
```

이는 형식 예시이며 실제 프로젝트 파일 경로·상태가 아니다. 요청 이름만 바꿔 중복 기능을 예약하지 않는다.

| action | 의미 |
|---|---|
| init / reconcile | lead의 검토된 전환 / 기존 기록·미등록 PR 재조정 |
| claim | 신규 목적/범위 예약. branch는 아직 만들지 않음 |
| adopt | HOLD의 실제 기존 branch를 writer에게 인계. 이전 작성자 종료 증거 필요 |
| create-branch | 예약한 branch 하나 생성 및 HEAD 확인 |
| write | 예약 범위의 UTF-8 text files map을 한 커밋으로 게시; message 필수 |
| sync | 현재 main을 pinned SHA로 작업 branch에 정상 병합; force 없음 |
| extend-scope | 동일 작업의 필요한 경로/contract 확장. 충돌 검사와 기존 증거 초기화 |
| pause / resume | BLOCKED와 ACTIVE 전환. reason 필수. BLOCKED여도 범위·WIP 점유 |
| offer-handoff / accept | 쓰기 종료 후 recipient에게 제안, 상대가 epoch 확인 후 수락 |
| tests | 실제 실행한 commands/report/passed/head/base_code 증거 제출 |
| review | 다른 reviewer의 decision/report/head/base_code 제출 |
| submit | 증거·dependency·PR 범위 확인 후 READY; validation은 VALIDATED |
| merge | lead의 명시적 approval 후 하나씩 정상 병합·결과 검증 |
| cancel | lead가 사용자 승인 근거를 기록해 작업 취소. branch는 삭제하지 않음 |
| transfer-lead | integration이 없을 때 기존 lead가 다음 담당에게 권한 인계 |

`write` 요청은 files={"허용/경로": "전체 UTF-8 코드"}, message를 포함한다. 삭제는 지원하지 않는다. `tests`의 passed=false는 정상 기록이지만 READY/PASS가 되지 않는다. HIGH는 review가 PASS이고 작성자와 다른 reviewer여야 한다.

### 장애 복구

BRANCHING: 결과 HEAD가 예약 base와 같으면 create-finish. branch가 실제 없으면 create-abort.
WRITING: 실제 단일 자식 commit과 전체 변경 경로가 맞으면 finish-write. HEAD가 그대로면 abort-write.
SYNCING: pinned main과 이전 HEAD의 merge/fast-forward 근거로 finish-sync. HEAD가 그대로면 abort-sync.
INTEGRATING: PR merged/head/부모/base 코드/main 포함 근거로 merge-finish. 아직 open이고 base가 그대로일 때만 merge-abort.

finish/abort는 해당 operation ID를 요구한다. 시간이 오래 지났다는 이유로 lock을 자동 해제하지 않는다. 결과 불명·부모 불일치·새 보안 문제가 있으면 관련 작업만 BLOCKED로 조정·검토하고 무관한 프로젝트 전체를 멈추지 않는다.

## 리소스·보안 운영

메타데이터 CAS commit에는 `[skip ci] [skip render]`를 붙인다. 이는 알려진 일반 자동 실행을 줄이는 보조 장치다. 실제 workflow/provider 설정과 required checks를 확인해야 하며 모든 종류의 자동화를 차단했다고 주장하지 않는다. 제품 code/merge에는 이 도구가 임의로 CI skip을 삽입하지 않는다. 정상 테스트/배포 정책을 적용한다.

HTTP는 GitHub API host만 사용하고 redirect에 token을 넘기지 않는다. timeout, response size, pagination 상한을 두고, 실패 응답의 본문/secret을 출력하지 않는다. write를 blind retry하지 않는다. registry/history 크기가 상한에 도달하면 임의 삭제 대신 검토된 archive/migration을 요구한다.

## 검증 기록

- 로컬 Python 3.13 환경에서 전체 unittest 실행. 결과는 `docs/WORK_GUARD_VALIDATION.md`.
- mock transport/service는 API 권한, 실제 네트워크, 플랫폼 전체 안전성을 인증하지 않는다.
- 실 GitHub의 isolated 작업 branch에서 오래된 contents SHA가 409로 거절되는 원리를 추가 확인했다.
- 이 환경의 standalone urllib live-read는 API_READ_FAILED. 따라서 standalone REST 전 구간 실계정 E2E 완료라고 주장하지 않는다. connector publication과 로컬 회귀를 별도로 기록한다.
- 제품 DB/배포/코드·제품 브랜치 정리 또는 제품별 live 활성화는 이번 테스트에서 수행하지 않는다.

## 참고한 공식 API 계약

- GitHub Contents: https://docs.github.com/en/rest/repos/contents
- GitHub refs (non-force): https://docs.github.com/en/rest/git/refs
- GitHub compare: https://docs.github.com/en/rest/commits/commits#compare-two-commits
- GitHub branches/merge: https://docs.github.com/en/rest/branches/branches#merge-a-branch
- GitHub pull merge: https://docs.github.com/en/rest/pulls/pulls#merge-a-pull-request
- Render skip: https://render.com/docs/deploys#skipping-an-auto-deploy
