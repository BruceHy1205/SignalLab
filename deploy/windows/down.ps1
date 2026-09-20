# 停止 Windows Docker 栈
param([string]$EnvFile = ".env.prod")

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

& docker compose `
  -f deploy/docker-compose.prod.yml `
  -f deploy/docker-compose.windows.yml `
  -f deploy/docker-compose.windows-miniqmt.yml `
  --env-file $EnvFile `
  down

exit $LASTEXITCODE
