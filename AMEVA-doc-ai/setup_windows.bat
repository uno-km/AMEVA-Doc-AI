@echo off
setlocal enabledelayedexpansion
chcp 65001 > nul
color 0E
title AMEVA Doc AI - Ultimate Ironclad Installer v13.0

:: 변수 초기화
set "NEED_REBOOT=NO"
set "OLLAMA_EXE=ollama"

echo.
echo    #####################################################
echo    #                                                   #
echo    #   A M E V A   D O C   A I   I N S T A L L E R     #
echo    #                                                   #
echo    #####################################################
echo.
echo    [ SYSTEM ] SECURITY POLICY, PATH REPAIR AND DEPLOY
echo    -----------------------------------------------------
echo.

:: 0. 파워쉘 보안 정책 해제 (PowerShell 호출)
echo  [STEP 0] 파워쉘 실행 권한 승인 시퀀스...
powershell -Command "Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force"
echo  [OK] 보안 정책 해제 완료.

:: 1. 파이썬 엔진 검사
echo.
echo  [STEP 1] 파이썬 엔진 (Python Engine) 확인 중
python --version >nul 2>&1
if !errorlevel! neq 0 (
    echo  [!] 파이썬 엔진 미감지. 긴급 이식을 시작합니다...
    winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements --override "/quiet InstallAllUsers=1 PrependPath=1"
    set "NEED_REBOOT=YES"
) else (
    echo  [OK] 파이썬 엔진이 이미 대기 중입니다.
)

:: 2. 가상 환경(venv) 구축
echo.
echo  [STEP 2] 가상 환경 기지 (Virtual Environment)
if not exist venv (
    echo  [!] venv 기지 건설 중... 얍!
    python -m venv venv
)
echo  [ACTION] 가상 환경 접속 중...
:: 가상환경 활성화 시 에러 방지를 위해 경로 직접 호출
call "%~dp0venv\Scripts\activate.bat"

:: 3. 라이브러리 연쇄 무장 (에러 방지를 위해 echo 단순화)
echo.
echo  [STEP 3] 필수 유닛 무장 (Library Components)
python -m pip install --upgrade pip --quiet
pip install setuptools --quiet

set "libs=PyQt6 reportlab ollama psutil GPUtil python-docx openpyxl python-pptx olefile"

for %%i in (%libs%) do (
    pip show %%i >nul 2>&1
    if !errorlevel! equ 0 (
        echo  [OK] %%i : 이미 장착됨
    ) else (
        echo  [ARMING] %%i : 신규 장착을 시작하겠숩니다...
        pip install %%i --quiet
        echo  [DONE] %%i : 장착 성공!
    )
)

:: 4. 올라마 엔진 복구 및 서비스 기동
echo.
echo  [STEP 4] AI 심장 (Ollama Core Fix)
ollama --version >nul 2>&1
if !errorlevel! neq 0 (
    set "OLLAMA_DIR=%LocalAppData%\Programs\Ollama"
    if exist "!OLLAMA_DIR!\ollama.exe" (
        set "OLLAMA_EXE=!OLLAMA_DIR!\ollama.exe"
        echo  [FIX] 환경 변수 강제 등록 중...
        powershell -Command "[System.Environment]::SetEnvironmentVariable('Path', $env:Path + ';$env:LocalAppData\Programs\Ollama', 'User')"
    ) else (
        echo  [!] 엔진 미설치. 신규 설치를 시작합니다...
        winget install -e --id Ollama.Ollama --accept-source-agreements --accept-package-agreements
        set "NEED_REBOOT=YES"
        set "OLLAMA_EXE=%LocalAppData%\Programs\Ollama\ollama.exe"
    )
)

:: 올라마 서비스 기동
powershell -Command "stop-process -name 'ollama*' -force -erroraction silentlycontinue"
start /b "" "!OLLAMA_EXE!" serve
timeout /t 3 > nul
echo  [OK] AI 심장 박동 정상.

:: 5. AI 모델 배치
echo.
echo  [STEP 5] AI 모델 배치 (AI Model Deployment)
"!OLLAMA_EXE!" list > models.tmp 2>&1
set "targets=gemma2:2b qwen2.5:1.5b phi3:mini"
for %%m in (%targets%) do (
    findstr /C:"%%m" models.tmp >nul 2>&1
    if !errorlevel! equ 0 (
        echo  [OK] %%m : 이미 소환됨
    ) else (
        echo  [DEPLOY] %%m : 소환술 시전 중... 얍!
        "!OLLAMA_EXE!" pull %%m
    )
)
del models.tmp

:: 최종 시퀀스
echo.
color 0B
echo  -----------------------------------------------------
echo   모든 보안 정책 및 무장이 완료되었습니다!
echo  -----------------------------------------------------
echo.

if "%NEED_REBOOT%"=="YES" (
    echo  [NOTICE] 환경 변수 적용을 위해 재부팅이 필요합니다.
    set /p REBOOT_NOW="지금 바로 재부팅하시겠습니까? (Y/N): "
    if /i "!REBOOT_NOW!"=="Y" (
        shutdown /r /t 10 & exit /b
    )
)

echo  [READY] 모든 준비가 끝났습니다.
set /p RUN_NOW="지금 바로 AMEVA Doc AI를 기동하겠숩니까? (Y/N): "
if /i "!RUN_NOW!"=="Y" (
    python main.py
)
pause