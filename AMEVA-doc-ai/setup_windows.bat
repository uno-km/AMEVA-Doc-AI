@echo off
setlocal enabledelayedexpansion
chcp 65001 > nul
color 0E
title AMEVA Doc AI - Ultimate Supreme Installer v10.0

:: 변수 초기화
set "NEED_REBOOT=NO"
set "OLLAMA_EXE=ollama"

echo.
echo    █████╗ ███╗   ███╗███████╗██╗   ██╗ █████╗ 
echo   ██╔══██╗████╗ ████║██╔════╝██║   ██║██╔══██╗
echo   ███████║██╔████╔██║█████╗  ██║   ██║███████║
echo   ██╔══██║██║╚██╔╝██║██╔══╝  ╚██╗ ██╔╝██╔══██║
echo   ██║  ██║██║ ╚═╝ ██║███████╗ ╚████╔╝ ██║  ██║
echo   ╚═╝  ╚═╝╚═╝     ╚═╝╚══════╝  ╚═══╝  ╚═╝  ╚═╝
echo  ─────────────────────────────────────────────────────
echo   [ SYSTEM ] PRE-FLIGHT CHECK AND AUTO-DEPLOYMENT
echo  ─────────────────────────────────────────────────────
echo.

:: 0. 파워쉘 실행 권한 해제
powershell -Command "Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process -Force"

:: -------------------------------------------------------
:: [STEP 1] 파이썬 엔진 검사 및 설치
:: -------------------------------------------------------
echo  [STEP 1] 파이썬 엔진 (Python Engine)
python --version >nul 2>&1
if !errorlevel! neq 0 (
    echo  [!] 파이썬이 없습니다. 시스템 이식을 시작합니다...
    winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements --override "/quiet InstallAllUsers=1 PrependPath=1"
    if !errorlevel! neq 0 (
        color 0C & echo [ERROR] 파이썬 설치 실패! & pause & exit /b
    )
    set "NEED_REBOOT=YES"
    echo  [DONE] 엔진 장착 완료.
) else (
    echo  [OK] 최적의 파이썬 엔진이 이미 가동 중입니다.
)

:: -------------------------------------------------------
:: [STEP 2] 가상 환경(venv) 검사 및 구축
:: -------------------------------------------------------
echo.
echo  [STEP 2] 가상 환경 기지 (Virtual Environment)
if not exist venv (
    echo  [!] venv 기지가 없습니다. 새로운 섹터를 구축합니다...
    python -m venv venv
    echo  [DONE] 섹터 구축 완료.
) else (
    echo  [OK] 준비된 venv 기지가 감지되었습니다.
)
echo  [ACTION] 가상 환경 프로토콜 진입 중...
call venv\Scripts\activate

:: -------------------------------------------------------
:: [STEP 3] 라이브러리 연쇄 스캔 및 무장
:: -------------------------------------------------------
echo.
echo  [STEP 3] 필수 유닛 무장 (Library Components)
python -m pip install --upgrade pip --quiet

:: 호환성 보정용 세트업툴 체크
pip show setuptools >nul 2>&1
if !errorlevel! neq 0 (
    echo  [ARMING] setuptools 영입 중...
    pip install setuptools --quiet
)

set "libs=PyQt6 reportlab ollama psutil GPUtil python-docx openpyxl python-pptx olefile"

for %%i in (%libs%) do (
    pip show %%i >nul 2>&1
    if !errorlevel! equ 0 (
        echo  [OK] %%i : 무장 상태 양호.
    ) else (
        echo  [ARMING] %%i : 신규 유닛 장착 중...
        pip install %%i --quiet
        echo  [DONE] %%i : 장착 성공.
    )
)

:: -------------------------------------------------------
:: [STEP 4] 올라마 엔진 (Ollama Core)
:: -------------------------------------------------------
echo.
echo  [STEP 4] AI 심장 (Ollama Core Engine)
ollama --version >nul 2>&1
if !errorlevel! neq 0 (
    if exist "%LocalAppData%\Programs\Ollama\ollama.exe" (
        set "OLLAMA_EXE=%LocalAppData%\Programs\Ollama\ollama.exe"
        echo  [OK] 올라마 엔진이 이미 숨겨진 경로에 대기 중입니다.
    ) else (
        echo  [!] 심장이 멈춰 있습니다. 신규 엔진 이식 시작...
        winget install -e --id Ollama.Ollama --accept-source-agreements --accept-package-agreements
        set "NEED_REBOOT=YES"
        set "OLLAMA_EXE=%LocalAppData%\Programs\Ollama\ollama.exe"
        echo  [DONE] 엔진 이식 완료.
    )
) else (
    echo  [OK] 올라마 엔진이 힘차게 고동치고 있습니다.
)

:: -------------------------------------------------------
:: [STEP 5] AI 모델 소환 및 배치
:: -------------------------------------------------------
echo.
echo  [STEP 5] AI 모델 배치 (AI Model Deployment)

:: 모델 목록 임시 캐시
"!OLLAMA_EXE!" list > models.tmp 2>&1

set "targets=gemma2:2b qwen2.5:1.5b phi3:mini"
for %%m in (%targets%) do (
    findstr /C:"%%m" models.tmp >nul 2>&1
    if !errorlevel! equ 0 (
        echo  [OK] %%m : 이미 배치됨.
    ) else (
        echo  [DEPLOY] %%m : 미배치 상태. 소환 프로토콜 시작...
        "!OLLAMA_EXE!" pull %%m
        echo  [DONE] %%m : 배치 완료.
    )
)
del models.tmp

:: -------------------------------------------------------
:: 최종 시퀀스
:: -------------------------------------------------------
echo.
color 0B
echo  ─────────────────────────────────────────────────────
echo   축하합니다! AMEVA Doc AI의 모든 무장이 완료되었습니다.
echo  ─────────────────────────────────────────────────────
echo.

if "%NEED_REBOOT%"=="YES" (
    echo  [NOTICE] 시스템 환경이 변경되었습니다. 재부팅을 권장합니다.
    echo.
    set /p REBOOT_NOW="지금 바로 컴퓨터를 재부팅하시겠습니까? (Y/N): "
    if /i "!REBOOT_NOW!"=="Y" (
        echo  [BYE] 10초 뒤 시스템을 다시 시작합니다...
        shutdown /r /t 10 & exit /b
    )
)

echo  [READY] 현재 모든 준비가 완벽합니다.
set /p RUN_NOW="지금 바로 AMEVA Doc AI를 기동할까요? (Y/N): "
if /i "!RUN_NOW!"=="Y" (
    echo  [EXEC] 메인 엔진 가동 시작!!! 🚀
    python main.py
)

echo.
echo  설치 스크립트를 마칩니다.
pause