@echo off
setlocal
chcp 65001 > nul
cd /d "%~dp0"

rem 태양광 발전량 예측 프로그램 등 다른 프로젝트의 환경과 섞이지 않도록
rem 이 프로젝트 전용 가상환경의 Python을 직접 실행합니다.
set "VENV_DIR=%~dp0.venv-fourpillars-v3"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
  echo [1/4] 가상환경 생성
  py -3.10 -m venv "%VENV_DIR%" || goto :error
) else (
  echo [1/4] 사주 프로그램 전용 가상환경 확인 완료
)

echo [2/4] Python 패키지 설치
"%PYTHON_EXE%" -m pip install -r requirements.txt || goto :error

echo [3/4] Playwright Chromium 설치
"%PYTHON_EXE%" -m playwright install chromium || goto :error

echo [4/4] 사주 리포트 시작
"%PYTHON_EXE%" app.py
goto :eof

:error
echo.
echo 실행 중 오류가 발생했습니다.
pause
