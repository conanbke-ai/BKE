# TORI Family UI System Standard v1

이 문서는 운토리·미스토리·농토리 및 이후 TORI 계열 프로젝트의 화면 재구현 기준이다. 목적은 기존 기능 계약을 보존하면서 오래된 화면/CSS/JS를 단계적으로 걷어내고, 프로젝트마다 다른 개성을 유지하는 하나의 TORI 패밀리 경험을 만드는 것이다.

## 1. 최상위 원칙

- 백엔드/도메인/API/DB/인증/결제/권한/게임 상태 등 동작 계약은 화면 재구현과 분리해 보존한다.
- 화면단은 레거시에 덧칠하지 않고 새 디자인 시스템으로 점진 교체한다.
- 새 화면은 기존 거대 CSS/JS 파일에 규칙을 추가하지 않는다. 새 토큰·공통 primitive·작은 기능 모듈을 사용한다.
- 레거시는 새 화면의 기능·회귀 검증이 끝난 뒤 삭제한다. 먼저 삭제하고 다시 맞추는 방식은 금지한다.
- TORI 캐릭터는 프로젝트마다 형제/자매처럼 다르되 공통 얼굴·귀·체형 언어를 유지한다.
- 커서 인터랙션은 TORI 패밀리 공통 시그니처로 유지한다: `고양이 젤리발 커서 + 뾰잉!`.

## 2. 고양이 젤리발 커서 규격

커서는 곰발/강아지발처럼 보이지 않아야 한다.

필수 형태:
- 발가락 젤리 4개만 사용한다.
- 발가락은 작고 타원형이며 서로 너무 넓게 벌어지지 않는다.
- 중앙 큰 젤리는 상단이 살짝 오목하고 하단이 3개의 둥근 로브로 느껴지는 고양이 metacarpal-pad 실루엣을 사용한다.
- 발톱, 다섯 번째 발가락, 두꺼운 곰발 외곽선은 넣지 않는다.
- 포인터는 가볍고 말랑한 젤리 느낌이어야 하며 시야를 과하게 가리지 않는다.
- 실제 클릭 hotspot은 발 앞쪽/중앙에 맞춘다.

동작:
- desktop/fine pointer에서만 커스텀 커서를 활성화한다.
- touch/mobile에서는 시스템 터치 동작을 건드리지 않는다.
- 텍스트 입력 영역에서는 시스템 text cursor를 우선한다.
- 클릭 가능한 요소에서는 젤리발이 아주 미세하게 통통해진다.
- pointer down 시 0.45~0.6초의 `뾰잉!` pop을 표시한다.
- `prefers-reduced-motion: reduce`에서는 이동/튀기 애니메이션과 pop을 최소화하거나 제거한다.
- 커서는 pointer-events:none 이어야 하며 실제 클릭을 가로채면 안 된다.

## 3. 프로젝트별 Theme Token v1

색은 화면별 임의 hex 값이 아니라 CSS variables/theme token으로 사용한다. 아래 값은 v1 기준이며 이후 디자인 검수에서 조정 가능하다.

### 운토리
- primary lilac: `#8B76C7`
- primary deep: `#6653A8`
- jelly rose: `#FF94BC`
- jelly highlight: `#FFD0E0`
- cream: `#FFF8F0`
- soft rainbow: 파스텔 pink/peach/mint/sky/lilac
- subtle gold: `#D7B66D`

느낌: 밝고 포근한 사주 노트, 라일락 눈/포인트, 무지개·구름은 배경 보조로만 사용.

### 미스토리
- deep navy: `#171C2C`
- charcoal: `#222632`
- plum: `#3D304A`
- antique gold: `#C5A76A`
- parchment: `#F2E8D7`
- jelly mauve: `#B985A4`
- jelly highlight: `#DEC0D1`

느낌: 어두운 미스터리, 문서/증거 가독성 우선. 캐릭터와 인터랙션은 귀엽지만 게임의 긴장감을 깨지 않는다.

### 농토리
- sky blue: `#78C5E2`
- field green: `#5F8E68`
- strawberry coral: `#EA8392`
- cream: `#FFF9EF`
- soil brown: `#7A5A46`
- jelly coral: `#F29AAA`

느낌: 현장 친화적이고 명료한 농작업 앱. 고령 농장주와 외국인 작업자를 고려해 대비·버튼 크기·아이콘 명료성을 우선한다.

## 4. 공통 UI primitive

새 화면은 우선 다음 primitive를 사용한다.

- PageShell / AppShell
- TopBar / BottomNav
- Button(primary, secondary, ghost, danger)
- Card / Panel
- Field / Select / Checkbox / Radio
- Modal / Sheet
- Tabs
- Badge / Status
- Toast
- Loading / Empty / Error
- MascotStage
- ToriCatPawCursor / BoingInteraction

프로젝트가 React가 아니어도 동일한 class/token contract를 사용할 수 있다.

## 5. Motion 규칙

- hover: 120~180ms
- press: 80~140ms
- 일반 panel transition: 180~260ms
- `뾰잉!`: 450~600ms
- 큰 장식 애니메이션은 반복을 최소화한다.
- 중요한 정보 확인/결제/삭제 화면에서는 장식 motion보다 안정성과 명료성을 우선한다.

## 6. Legacy migration 방식

Strangler 방식으로 화면 단위 교체한다.

1. 현재 화면의 API/event/data contract를 목록화한다.
2. 새 UI가 동일 contract를 소비하도록 구현한다.
3. 새 UI용 local test/smoke를 추가한다.
4. 새 화면으로 routing/entry를 전환한다.
5. 참조가 사라진 CSS/JS/template만 삭제한다.
6. 삭제 전 코드 검색으로 import/reference 0건을 확인한다.

분류:
- KEEP: domain/service/repository/API/security/payment/state 등 기능 핵심
- BRIDGE: 새 UI 전환 중 잠시 유지하는 adapter/compatibility layer
- REBUILD: template/component/CSS/interaction/navigation
- DELETE-LATER: 새 화면 전환 후 참조가 0이 된 legacy asset/module

## 7. 새 코드 금지 패턴

- `styles.css` 같은 거대 파일에 계속 규칙 추가
- 화면별로 동일 button/card/modal을 새로 복붙
- 버전명이 붙은 CSS를 계속 누적해 cascade로 덮기
- 한 기능을 여러 전역 JS 파일에서 동시에 DOM patch
- inline style/!important로 디자인 충돌을 임시 봉합하는 방식의 상시화
- 기존 기능 검증 없이 레거시 파일 일괄 삭제

## 8. 검증

UI 재구현은 무료 리소스 정책을 함께 따른다.

- 기본: local syntax/type/unit/smoke
- UI 큰 변경: local browser smoke
- 실제 DB/session/runtime 필요 시에만 staging
- GitHub-hosted heavy CI는 release/manual gate
- 화면 재구현만으로 domain/engine 전체 대량 검증을 매번 실행하지 않는다.

## 9. 완료 기준

한 화면이 새 시스템으로 이전됐다고 보기 위한 조건:
- 기존 기능/권한/데이터 계약 유지
- desktop/mobile 정상
- loading/empty/error 포함
- 키보드 focus 및 reduced-motion 고려
- 해당 프로젝트 theme token 적용
- 고양이 젤리발 커서/뾰잉 인터랙션이 desktop에서 정상
- 새 코드가 legacy monolith에 새 의존성을 만들지 않음
- 기존 레거시 참조 제거 여부 확인
