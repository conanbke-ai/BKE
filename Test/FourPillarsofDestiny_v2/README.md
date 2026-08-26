# Four Pillars Compatibility v2.1

## 핵심 동작

- 사용자 원국 기준으로 1~12월 전체 날짜를 로컬 선별
- 날짜 1차 선별에서는 시주를 제외
- 다양성 제한 후 12시진 확장
- 상위 30개만 포스텔러 수집
- 메타데이터·본문·HTML·스크린샷·network.json 품질 검증
- 중단 후 재실행 시 유효 캐시는 자동 건너뜀
- 실패 후보 최대 3회 재시도 및 `retry` 모드
- 브라우저를 주기적으로 재시작
- **OpenAI API는 최종 TOP 10만 한 번에 비교·해석**
- TOP 10 비교표, 데이터/파싱/추론 품질 점수 제공

## 설치

```bash
"C:/Program Files/Python313/python.exe" -m pip install -r requirements.txt
"C:/Program Files/Python313/python.exe" -m playwright install chromium
```

## 환경변수

노출된 기존 API 키는 폐기하고 새 키를 사용하세요.

```bash
export OPENAI_API_KEY="새_API_키"
export OPENAI_MODEL="gpt-5.6"
```

선택 설정:

```bash
export COLLECT_COUNT=30
export COLLECTION_RETRY_COUNT=3
export BROWSER_RESTART_EVERY=20
export AI_INCLUDE_IMAGES=1
```

## 실행

```bash
python app.py local    # 로컬 선별
python app.py collect  # 상위 후보 수집 및 이어서 실행
python app.py retry    # 실패 후보만 재시도
python app.py status   # 진행 상태 확인
python app.py report   # TOP 10만 AI 보고서
python app.py all      # 전체 실행
```

## 캐시 검증

기존 결과는 다음이 모두 정상일 때만 재사용합니다.

- 수집 조건 서명 일치
- `/result` URL
- 유효한 스크린샷
- 충분한 HTML·본문 크기
- `network.json`이 정상 JSON
- 본문에 `생년·생월·생일·생시` 마커 존재

OCR은 사용하지 않습니다. 페이지 자체의 본문 텍스트가 이미지 OCR보다 정확하고 안정적이기 때문입니다.

## 산출물

```text
output/<사용자프로젝트ID>/
├─ profile.json
├─ local_ranking.json
├─ progress.json
├─ ai_top10_report.json
├─ top10_ai_report.md
├─ top10_ai_report.html
└─ candidates/<candidate_id>/
   ├─ result.png
   ├─ result.html
   ├─ result.txt
   ├─ network.json
   ├─ metadata.json
   └─ candidate_summary.md
```


## OpenAI 비용·캐시·429 처리

- AI는 최종 로컬 TOP 10 전체를 **한 번의 Responses API 호출**로 상대 비교합니다.
- 성공 결과는 `ai_top10_report.json`에 저장되며, 모델·프롬프트·TOP 10 입력이 같으면 재호출하지 않습니다.
- 요청 정보는 `ai_request_manifest.json`에 기록됩니다.
- `429 insufficient_quota`는 속도 제한이 아니라 API 결제/크레딧 부족입니다. 이 경우:
  - 로컬 순위와 포스텔러 원본은 보존됩니다.
  - `ai_error.json`에 원인이 저장됩니다.
  - `top10_local_fallback.md/html` 임시 보고서가 생성됩니다.
  - 결제 설정 후 `python app.py report`만 다시 실행하면 됩니다.
- traceback은 `logs/YYYY-MM-DD.error.log`에 저장되고 터미널에는 간단한 안내만 출력됩니다.
