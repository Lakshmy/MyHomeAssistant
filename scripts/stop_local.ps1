# Stop locally running FindIt servers
# Usage: .\stop_local.ps1

Write-Host ""
Write-Host "=== Stopping FindIt ===" -ForegroundColor Cyan
Write-Host ""

$stopped = 0

# Stop backend (uvicorn on port 8000)
$beConn = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($beConn) {
    $procIds = $beConn | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($p in $procIds) {
        Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
    }
    Write-Host "  Stopped backend (port 8000)" -ForegroundColor Green
    $stopped++
} else {
    Write-Host "  Backend not running (port 8000)" -ForegroundColor Gray
}

# Stop frontend (vite on port 5173)
$feConn = Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue
if ($feConn) {
    $procIds = $feConn | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($p in $procIds) {
        Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
    }
    Write-Host "  Stopped frontend (port 5173)" -ForegroundColor Green
    $stopped++
} else {
    Write-Host "  Frontend not running (port 5173)" -ForegroundColor Gray
}

Write-Host ""
if ($stopped -gt 0) {
    Write-Host "Servers stopped." -ForegroundColor Green
} else {
    Write-Host "No servers were running." -ForegroundColor Yellow
}
