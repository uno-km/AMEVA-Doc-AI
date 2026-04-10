@echo off
chcp 65001 > nul
color 0A
echo ===================================================
echo   AMEVA Doc AI 자동 설치 스크립트 (Windows용)
echo ===================================================
echo.

:: 1. 파이썬 라이브러리 설치
echo [1/3] 파이썬 필수 라이브러리를 설치합니다...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [경고] 라이브러리 설치 중 오류가 발생했습니다. (Python과 pip가 설치되어 있는지 확인하세요.)
    pause
    exit /b
)
echo.

:: 2. Ollama 코어 설치 (Winget 사용)
echo [2/3] Ollama 코어 엔진을 설치/확인합니다...
winget install -e --id Ollama.Ollama --accept-source-agreements --accept-package-agreements
echo.

:: 3. 초경량 모델 3종 다운로드
echo [3/3] 초경량 AI 모델 3종을 다운로드합니다. (인터넷 속도에 따라 시간이 걸릴 수 있습니다.)
echo.

echo - gemma2:2b (구글 경량 모델) 다운로드 중...
ollama pull gemma2:2b

echo - qwen2.5:1.5b (Qwen 초경량 모델) 다운로드 중...
ollama pull qwen2.5:1.5b

echo - phi3:mini (MS 고효율 모델) 다운로드 중...
ollama pull phi3:mini

echo.
echo ===================================================
echo   모든 설치가 완료되었습니다!
echo   프로그램을 실행하려면 'python main.py'를 입력하세요.
echo   (만약 Ollama가 방금 설치되었다면 컴퓨터 재부팅을 권장합니다.)
echo ===================================================
pause
