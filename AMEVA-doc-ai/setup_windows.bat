@echo off
setlocal enabledelayedexpansion
chcp 65001 > nul
color 0E
title AMEVA Doc AI - Hyper Installer v6.5

:: 변수 초기화
set "NEED_REBOOT=NO"

echo.
echo  =======================================================
echo     █████╗ ███╗   ███╗███████╗██╗   ██╗ █████╗ 
echo    ██╔══██╗████╗ ████║██╔════╝██║   ██║██╔══██╗
echo    ███████║██╔████╔██║█████╗  ██║   ██║███████║
echo    ██╔══██║██║╚██╔╝██║██╔══╝  ╚██╗ ██╔╝██╔══██║
echo    ██║  ██║██║ ╚═╝ ██║███████╗ ╚████╔╝ ██║  ██║
echo    ╚═╝  ╚═╝╚═╝     ╚═╝╚══════╝  ╚═══╝  ╚═╝  ╚═╝
echo  =======================================================
echo.
echo   🚀 AMEVA Doc AI 통합 설치 시스템(v6.5)을 가동합니다...
echo.

:: 0. 파워쉘 실행 권한 해제 (RemoteSigned)
echo  [SYSTEM] 스크립트 실행 권한을 해제합니다...
powershell -Command "Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process -Force"

:: 1. 파이썬 엔진 탐색 및 자동 설치
echo  [SYSTEM] 파이썬 엔진 탐색 중...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  [⚠️ WARNING] 파이썬이 실종되었습니다! 긴급 설치를 시작합니다...
    echo.
    winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements --override "/quiet InstallAllUsers=1 PrependPath=1"
    
    if !errorlevel! neq 0 (
        color 0C
        echo  [❌ ERROR] 파이썬 설치 실패. 수동 설치가 필요합니다.
        pause
        exit /b
    )
    echo  [✅ SUCCESS] 파이썬 엔진 장착 완료!
    set "NEED_REBOOT=YES"
)

:: 2. 가상 환경(venv) 구성
echo.
echo  -------------------------------------------------------
if not exist venv (
    echo  [🔥 PHASE 1] "가상 환경(venv)이 없네요? 새로 구축하겠습니다..."
    python -m venv venv
    echo  [DONE] 가상 환경 구축 성공!
) else (
    echo  [🔥 PHASE 1] 가상 환경(venv)이 이미 존재합니다.
)

echo  [ACTION] 가상 환경 안으로 텔레포트 중... 🌀
call venv\Scripts\activate

:: 3. 화려한 라이브러리 설치 로직
echo.
echo  -------------------------------------------------------
echo  [🔥 PHASE 2] "라이브러리 및 호환성 도구를 설치합니다!!!"
echo.

:: 3.12+ 호환성을 위한 setuptools 선행 설치
echo  [FIX] distutils 누락 방지를 위해 setuptools를 먼저 설치합니다...
pip install setuptools --quiet

set "libs=PyQt6 reportlab ollama psutil gputil python-docx openpyxl python-pptx olefile"

python -m pip install --upgrade pip > nul

for %%i in (%libs%) do (
    echo  [INSTALL] %%i 📦 설치 시작합니다~~~ 얍!
    pip install %%i --quiet
    if !errorlevel! equ 0 (
        echo  [✨ SUCCESS] %%i 설치 완료!!
    ) else (
        echo  [🚨 FAIL] %%i 설치 실패. 인터넷을 확인하세요.
    )
)

:: 4. 올라마 및 AI 모델 세팅
echo.
echo  -------------------------------------------------------
echo  [🔥 PHASE 3] "AI의 심장! 올라마(Ollama) 세팅 드갑니다!!!"
echo.

ollama --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ACTION] 올라마가 없네요? 당장 데려오겠습니다!
    winget install -e --id Ollama.Ollama --accept-source-agreements --accept-package-agreements
    set "NEED_REBOOT=YES"
)

echo  [ACTION] "초경량 모델 3남매 소환 작업..."
echo.

echo  [1/3] 🤖 gemma2:2b 소환 중...
ollama pull gemma2:2b
echo  [SUCCESS] gemma2 소환 성공!

echo  [2/3] 🧠 qwen2.5:1.5b 소환 중...
ollama pull qwen2.5:1.5b
echo  [SUCCESS] qwen2.5 소환 성공!

echo  [3/3] 🛡️ phi3:mini 소환 중...
ollama pull phi3:mini
echo  [SUCCESS] phi3 소환 성공!

echo.
color 0B
echo  =======================================================
echo     축하합니다! AMEVA Doc AI의 모든 무장이 완료되었습니다.
echo  =======================================================
echo.

:: 재부팅 권고 및 즉시 실행 로직 통합
if "%NEED_REBOOT%"=="YES" (
    echo  [🔔 중요] 파이썬이나 올라마가 새로 설치되었습니다.
    echo  환경 변수 적용을 위해 시스템 재부팅을 강력히 권장합니다.
    echo.
    set /p REBOOT_NOW="지금 바로 컴퓨터를 재부팅하시겠습니까? (Y/N): "
    if /i "!REBOOT_NOW!"=="Y" (
        echo  [BYE] 10초 뒤에 재부팅을 시작합니다. 작업 중인 파일을 저장하세요!
        shutdown /r /t 10
        exit /b
    ) else (
        echo  [!] 재부팅을 건너뜁니다. 명령어가 인식되지 않으면 터미널을 다시 켜주세요.
    )
) else (
    echo  [🚀 READY] 시스템 환경이 완벽합니다. 재부팅 없이 즉시 기동 가능!
)

echo.
set /p RUN_NOW="지금 바로 AMEVA Doc AI를 실행할까요? (Y/N): "
if /i "!RUN_NOW!"=="Y" (
    echo  [EXEC] 프로그램 엔진 가동!!!
    python main.py
)

echo.
echo  설치 프로세스를 종료합니다. 
pause