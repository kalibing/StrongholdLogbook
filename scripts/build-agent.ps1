# 用源码打包「本机助手」单文件 exe，产物直接放进站点静态目录，面板上的下载按钮即指向它。
# 用法：pwsh -File scripts\build-agent.ps1
#       pwsh -File scripts\build-agent.ps1 -SkipInstall   （依赖已装好时跳过 pip）
param(
    [switch]$SkipInstall
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    throw "缺少虚拟环境：先执行 python -m venv .venv 并安装 backend/requirements-dev.txt"
}

$target = Join-Path $root 'frontend\public\download'
$work = Join-Path $root '.local\pyi'
New-Item -ItemType Directory -Force $target, $work | Out-Null

if (-not $SkipInstall) {
    & $python -m pip install --quiet --disable-pip-version-check pyinstaller pycryptodome
}

& $python -m PyInstaller `
    --onefile `
    --name ArknightsAchvAgent `
    --distpath $target `
    --workpath $work `
    --specpath $work `
    --noconfirm `
    (Join-Path $root 'agent\achv_agent.py')
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 打包失败（exit $LASTEXITCODE）" }

$exe = Join-Path $target 'ArknightsAchvAgent.exe'
if (-not (Test-Path $exe)) { throw "没有生成 $exe" }
$size = [math]::Round((Get-Item $exe).Length / 1MB, 2)
Write-Host "已生成 $exe（$size MB）"
Write-Host '源码：agent\achv_agent.py；构建脚本：scripts\build-agent.ps1；spec：agent\ArknightsAchvAgent.spec'
