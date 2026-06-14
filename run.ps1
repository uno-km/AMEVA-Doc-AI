# AMEVA Doc AI 실행 및 환경 진단 스크립트

$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Definition
if ($ScriptPath) { Set-Location -Path $ScriptPath }

$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
if ($PSVersionTable.PSVersion.Major -le 5) { chcp 65001 | Out-Null }
$ErrorActionPreference = "Stop"

Write-Host "--- AMEVA Doc AI Environment Setup ---" -ForegroundColor Cyan
Write-Host "Path: $(Get-Location)" -ForegroundColor Gray

# [0] 파워쉘 실행 권한 설정
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force

# [1] 파이썬 엔진 검사
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Host "Python is not found. Installing Python 3.12 via winget..." -ForegroundColor Yellow
    & winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements --override "/quiet InstallAllUsers=1 PrependPath=1"
    Write-Host "Please restart the script/terminal after installation is complete." -ForegroundColor Yellow
    exit 1
}

# [2] 가상환경(venv) 검증 및 패키지 설치
$EnvDir = ".\venv"
if (-not (Test-Path -Path $EnvDir)) {
    Write-Host "Virtual environment (venv) not found. Creating virtual environment..." -ForegroundColor Yellow
    python -m venv $EnvDir
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to create virtual environment."
        exit 1
    }
}

Write-Host "Upgrading pip and installing requirements..." -ForegroundColor Yellow
& "$EnvDir\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel
& "$EnvDir\Scripts\python.exe" -m pip install -r requirements.txt

# [3] Ollama 환경변수 설정
Write-Host "Configuring Ollama environment variables..." -ForegroundColor Cyan
[System.Environment]::SetEnvironmentVariable('OLLAMA_NUM_PARALLEL', '8', 'User')
$env:OLLAMA_NUM_PARALLEL = "8"

# [4] 하드웨어 감지
$videoControllers = Get-CimInstance Win32_VideoController
$hasNvidia = $false
foreach ($vc in $videoControllers) {
    if ($vc.Name -match "NVIDIA") { $hasNvidia = $true }
}
$hardwareMode = if ($hasNvidia) { "GPU" } else { "CPU" }
Write-Host "Hardware detected: $hardwareMode Mode" -ForegroundColor Green

# [5] Ollama 서비스 기동 확인
Write-Host "Verifying Ollama service status..." -ForegroundColor Cyan
$ollamaPort = 11434
$ollamaCheck = Test-NetConnection -ComputerName "127.0.0.1" -Port $ollamaPort -WarningAction SilentlyContinue

$ollamaExe = "ollama.exe"
$ollamaLocalPath = "$env:LocalAppData\Programs\Ollama\ollama.exe"
if (Test-Path $ollamaLocalPath) {
    $ollamaExe = $ollamaLocalPath
}

if (-not $ollamaCheck.TcpTestSucceeded) {
    Write-Host "Ollama is not running. Launching Ollama serve..." -ForegroundColor Yellow
    Stop-Process -Name "ollama*" -Force -ErrorAction SilentlyContinue
    Start-Process -FilePath $ollamaExe -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 5
} else {
    Write-Host "Ollama service: ONLINE" -ForegroundColor Green
}

# [6] 모델 풀링 (CPU/GPU 맞춤형 자동 선택)
Write-Host "Checking required models..." -ForegroundColor Cyan
$targets = if ($hardwareMode -eq "GPU") { "qwen2.5-coder:7b", "gemma2:2b" } else { "qwen2.5:1.5b", "gemma2:2b" }

$installedModels = & $ollamaExe list
foreach ($m in $targets) {
    if ($installedModels -match $m) {
        Write-Host "Model already exists: $m" -ForegroundColor Green
    } else {
        Write-Host "Pulling model: $m" -ForegroundColor Green
        & $ollamaExe pull $m
    }
}

# [7] 가상환경 활성화 및 가동
Write-Host "Activating virtual environment..." -ForegroundColor Cyan
. "$EnvDir\Scripts\Activate.ps1"

Write-Host "Launching AMEVA Doc AI..." -ForegroundColor Cyan
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONIOENCODING = "utf-8"

& "$EnvDir\Scripts\python.exe" main.py
