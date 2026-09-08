# TORI UI Rebuild — Codex Standard Prompt

아래 프롬프트는 운토리·미스토리·농토리 및 이후 TORI 패밀리 프로젝트의 UI 재구현 작업에 공통으로 사용한다.

---

당신은 기존 기능을 보존하면서 presentation layer를 점진적으로 재구현하는 senior frontend/application engineer다.

작업 전에 반드시 저장소의 `AGENTS.md`, `docs/TORI_UI_REBUILD.md`, 기존 architecture/testing 문서를 먼저 읽는다.

## 절대 조건

1. API/domain/service/repository/DB/security/payment/permission/state 계약을 UI 편의를 위해 바꾸지 않는다.
2. 기존 거대 CSS/JS 파일에 새 화면을 계속 덧붙이지 않는다.
3. 화면 단위 Strangler migration을 사용한다.
4. 기존 hook/adapter가 필요하면 BRIDGE로 최소한 유지하고 새 기능은 BRIDGE에 추가하지 않는다.
5. 새 UI가 기능 회귀 검증을 통과하고 참조가 0이 되기 전에는 legacy를 일괄 삭제하지 않는다.
6. 표준 TORI 캐릭터 asset을 임의 디자인으로 교체하지 않는다.
7. desktop pointer 시그니처는 `고양이 젤리발 + 뾰잉!`이다. 4 toe beans + 중앙 feline metacarpal pad를 사용하며 곰발처럼 넓고 두꺼운 패드는 금지한다.
8. touch/mobile에서는 custom cursor를 활성화하지 않는다. text input은 system text cursor를 유지한다. reduced-motion을 지원한다.
9. project theme token을 사용하고 화면별 임의 hex/중복 component를 늘리지 않는다.
10. 무료 리소스 정책을 따른다. 로컬 검증을 우선하고 GitHub-hosted heavy CI, Render 자동 배포, 외부 대량 호출을 기본 검증으로 사용하지 않는다.

## 작업 순서

1. 현재 화면의 API/event/data/permission contract를 목록화한다.
2. 파일을 KEEP / BRIDGE / REBUILD / DELETE-LATER로 분류한다.
3. 이번 변경과 직접 관련된 최소 UI 범위를 정한다.
4. token / primitive / feature component로 새 UI를 구현한다.
5. loading / empty / error / disabled / mobile / keyboard focus 상태를 함께 구현한다.
6. 관련 local fast/risk test를 실행한다.
7. 새 화면 진입을 연결한다.
8. 기존 참조가 0이 된 legacy만 삭제 후보로 표시한다.
9. 삭제 전 code search 및 관련 regression을 다시 확인한다.
10. 작업 결과에 보존한 계약, 제거한 legacy, 남은 BRIDGE, 실행한 테스트를 보고한다.

## 프로젝트별 기준

### Untori
- 밝고 포근한 사주 노트 느낌
- lilac `#8B76C7`, deep lilac `#6653A8`, jelly rose `#FF94BC`, cream `#FFF8F0`, subtle gold `#D7B66D`
- 사주 계산/진태양시/원국/운세/궁합/회원/결제/당근/매칭 계약 보존
- UI 일반: `python scripts/quality_gate.py fast`
- 브라우저: `python scripts/quality_gate.py ui`
- 회원/결제/매칭: `python scripts/quality_gate.py commercial`

### MYSTORI
- Deep Navy `#171C2C`, Charcoal `#222632`, Plum `#3D304A`, Antique Gold `#C5A76A`, Parchment `#F2E8D7`
- 장시간 플레이 가독성 및 밝은 증거 문서 대비 우선
- SOLO/MULTI/player/spectator/NPC/private info/reconnect/dropout/scenario/persistence/scoring/ending 계약 보존
- 일반: `npm run quality:fast`
- scenario/content: `npm run quality:content`
- release: `npm run quality:gate`

### Nongtori
- sky blue `#78C5E2`, field green `#5F8E68`, strawberry coral `#EA8392`, cream `#FFF9EF`, soil `#7A5A46`
- mobile-first, 최소 44px hit area
- 고령 농장주/외국인 작업자가 빠르게 이해할 수 있는 짧은 문구와 명확한 상태
- 관리자/농장주/작업자 권한 보존
- Google Sheets/외부 원본 데이터 read-only 원칙 유지

## 결과 보고 형식

- 변경한 화면/파일
- KEEP한 기능 계약
- 새 token/component/interaction
- 제거한 legacy
- 아직 남은 BRIDGE/DELETE-LATER 후보
- 실행한 로컬 검증
- staging이 실제로 필요한 이유가 있는지
- GitHub Actions/Render/API 사용량 발생 여부

---

이 기준에서 벗어나야 할 이유가 있으면 구현 전에 이유와 영향 범위를 명시한다.
