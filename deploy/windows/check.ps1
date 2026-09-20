# 健康检查:Docker 服务 + 可选 miniQMT probe
param(
    [string]$EnvFile = ".env.prod",
    [switch]$Miniqmt
)

$ErrorActionPreference = "Continue"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

Write-Host "==> docker compose ps" -ForegroundColor Cyan
docker compose `
  -f deploy/docker-compose.prod.yml `
  -f deploy/docker-compose.windows.yml `
  --env-file $EnvFile ps

Write-Host "==> GET /health (via Caddy,可能需 Basic Auth)" -ForegroundColor Cyan
try {
    Invoke-WebRequest -Uri "http://127.0.0.1/health" -UseBasicParsing -TimeoutSec 5 | Select-Object StatusCode, Content
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Yellow
}

if ($Miniqmt) {
    Write-Host "==> signal_live.probe" -ForegroundColor Cyan
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        $i = $line.IndexOf("=")
        if ($i -lt 1) { return }
        $k = $line.Substring(0, $i).Trim()
        $v = $line.Substring($i + 1).Trim()
        Set-Item -Path "Env:$k" -Value $v
    }
    uv run python -m signal_live.probe
}
