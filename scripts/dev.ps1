# 本地开发一键启动：SQLite 后端 + 导入 worker + Vite
# 用法：pwsh -File scripts\dev.ps1            （API 8000 / 网页 5173）
#       pwsh -File scripts\dev.ps1 -NoWorker   （不启动 worker）
param(
    [switch]$NoWorker
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'

if (-not (Test-Path $python)) {
    throw "缺少虚拟环境：先执行 python -m venv .venv 并安装 backend/requirements-dev.txt"
}

New-Item -ItemType Directory -Force (Join-Path $root '.local') | Out-Null

$env:LOGBOOK_DB = 'sqlite'
$env:LOGBOOK_SQLITE = Join-Path $root '.local\logbook.sqlite3'
$env:PUBLIC_ORIGIN = 'http://localhost:5173'
$env:PYTHONPATH = Join-Path $root 'backend'

Write-Host "存储：SQLite  $env:LOGBOOK_SQLITE"
Write-Host "来源：$env:PUBLIC_ORIGIN"
Write-Host '首次使用请先建账号：cd backend; python -m logbook.admin create-user <用户名>'

Start-Process pwsh -ArgumentList @(
    '-NoExit', '-Command',
    "Set-Location '$root\backend'; & '$python' -m uvicorn logbook.api:app --host 127.0.0.1 --port 8010 --reload"
)

if (-not $NoWorker) {
    Start-Process pwsh -ArgumentList @(
        '-NoExit', '-Command',
        "Set-Location '$root\backend'; & '$python' -m logbook.worker"
    )
}

Start-Process pwsh -ArgumentList @(
    '-NoExit', '-Command',
    "Set-Location '$root\frontend'; npm run dev"
)

Write-Host '已打开三个窗口：API http://127.0.0.1:8010 、worker、网页 http://localhost:5173'
