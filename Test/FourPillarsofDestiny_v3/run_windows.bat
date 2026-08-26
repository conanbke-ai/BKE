@echo off
chcp 65001 > nul
if not exist .venv (
  echo [1/4] 가상환경 생성
  py -m venv .venv
)
call .venv\Scripts\activate

echo [2/4] Python 패키지 설치
python -m pip install -r requirements.txt || goto :error

echo [3/4] Playwright Chromium 설치
python -m playwright install chromium || goto :error

echo [4/4] 사주 리포트 시작
python app.py
goto :eof

:error
echo.
echo 실행 중 오류가 발생했습니다.
pause
