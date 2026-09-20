# 在 Windows 宿主机跑 API,连接 Docker 内的 TimescaleDB,启用真 miniQMT。
# 前置:
#   1) QMT/miniQMT 已登录
#   2) docker 已起 db(可用 up.ps1 -Miniqmt)
#   3) .env.prod 已填 LIVE_MINIQMT_ACCOUNT / LIVE_MINIQMT_PATH
#   4) 本机 Python 3.11/3.12 + uv;xtquant 可 import(券商安装目录/site-packages)

param(
    [string]$EnvFile = ".env.prod",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

if (-not (Test-Path $EnvFile)) {
    Write-Host "缺少 $EnvFile" -ForegroundColor Yellow
    exit 1
}

# 读简单 KEY=VALUE(忽略注释与空行)
Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#")) { return }
    $i = $line.IndexOf("=")
    if ($i -lt 1) { return }
    $k = $line.Substring(0, $i).Trim()
    $v = $line.Substring($i + 1).Trim()
    if ($v.StartsWith('"') -and $v.EndsWith('"')) { $v = $v.Substring(1, $v.Length - 2) }
    Set-Item -Path "Env:$k" -Value $v
}

$pgUser = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "signal" }
$pgPass = $env:POSTGRES_PASSWORD
$pgDb = if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { "signal" }
$pgPort = if ($env:POSTGRES_HOST_PORT) { $env:POSTGRES_HOST_PORT } else { "5432" }
if (-not $pgPass) { Write-Host "POSTGRES_PASSWORD 未设置" -ForegroundColor Red; exit 1 }

$env:DATABASE_URL = "postgresql+psycopg://${pgUser}:${pgPass}@127.0.0.1:${pgPort}/${pgDb}"
$env:LIVE_BROKER = "miniqmt"
$env:SCHEDULER_ENABLED = if ($env:SCHEDULER_ENABLED) { $env:SCHEDULER_ENABLED } else { "true" }
$env:SCHEDULER_TIMEZONE = if ($env:SCHEDULER_TIMEZONE) { $env:SCHEDULER_TIMEZONE } else { "Asia/Shanghai" }
$env:RUNNER_CALLBACK_SECRET = if ($env:RUNNER_CALLBACK_SECRET) { $env:RUNNER_CALLBACK_SECRET } else { "dev-secret" }
$env:RESEARCH_CALLBACK_HOST = if ($env:RESEARCH_CALLBACK_HOST) { $env:RESEARCH_CALLBACK_HOST } else { "http://127.0.0.1:$Port" }

if (-not $env:LIVE_MINIQMT_ACCOUNT -or -not $env:LIVE_MINIQMT_PATH) {
    Write-Host "请在 $EnvFile 配置 LIVE_MINIQMT_ACCOUNT 与 LIVE_MINIQMT_PATH(userdata_mini)" -ForegroundColor Yellow
    exit 1
}

Write-Host "==> probe miniQMT..." -ForegroundColor Cyan
& uv run python -m signal_live.probe
if ($LASTEXITCODE -ne 0) {
    Write-Host "probe 未连通:确认 QMT 已登录、路径指向 userdata_mini、账号一致" -ForegroundColor Yellow
    Write-Host "仍继续启动 API(确认下单时会再连)..." -ForegroundColor Yellow
}

Write-Host "==> migrate + uvicorn :$Port" -ForegroundColor Cyan
Push-Location apps\api
& uv run alembic upgrade head
if ($LASTEXITCODE -ne 0) { Pop-Location; exit $LASTEXITCODE }
& uv run uvicorn signal_api.main:app --host 0.0.0.0 --port $Port
Pop-Location
