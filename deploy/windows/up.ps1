# Windows Docker 一键启动生产栈(默认 stub broker)
# 用法(仓库根目录):
#   powershell -ExecutionPolicy Bypass -File deploy/windows/up.ps1
#   powershell -ExecutionPolicy Bypass -File deploy/windows/up.ps1 -Miniqmt

param(
    [switch]$Miniqmt,
    [switch]$Backup,
    [string]$EnvFile = ".env.prod"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

if (-not (Test-Path $EnvFile)) {
    Write-Host "缺少 $EnvFile ,先: copy .env.prod.example .env.prod 并改密码" -ForegroundColor Yellow
    exit 1
}

$files = @(
    "-f", "deploy/docker-compose.prod.yml",
    "-f", "deploy/docker-compose.windows.yml"
)
if ($Miniqmt) {
    $files += @("-f", "deploy/docker-compose.windows-miniqmt.yml")
}

$args = $files + @("--env-file", $EnvFile, "up", "-d", "--build")
if ($Backup) {
    $args = $files + @("--env-file", $EnvFile, "--profile", "backup", "up", "-d", "--build")
}

if ($Miniqmt) {
    Write-Host "==> miniQMT 模式:只起 db/web/caddy,请另开窗口跑 run-host-api.ps1" -ForegroundColor Cyan
    & docker compose @files --env-file $EnvFile up -d --build db web caddy
} else {
    Write-Host "==> Docker 全栈启动(LIVE_BROKER 建议 stub)" -ForegroundColor Cyan
    & docker compose @args
}

if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "完成。浏览器打开 http://127.0.0.1/ (Basic Auth)" -ForegroundColor Green
if ($Miniqmt) {
    Write-Host "下一步: powershell -File deploy/windows/run-host-api.ps1" -ForegroundColor Green
}
