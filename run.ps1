# FindIt - Interactive Launcher
# Usage: .\run.ps1

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   FindIt - Launcher" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  1) Provision Azure infrastructure (first time)" -ForegroundColor White
Write-Host "  2) Deploy to Azure (full)" -ForegroundColor White
Write-Host "  3) Deploy backend only (Azure)" -ForegroundColor White
Write-Host "  4) Deploy frontend only (Azure)" -ForegroundColor White
Write-Host "  5) Start local servers" -ForegroundColor White
Write-Host "  6) Stop local servers" -ForegroundColor White
Write-Host "  7) Teardown Azure deployment" -ForegroundColor Red
Write-Host "  0) Exit" -ForegroundColor Gray
Write-Host ""

$choice = Read-Host "Select an option"

switch ($choice) {
    "1" {
        Write-Host ""
        & "$PSScriptRoot\scripts\deploy_infra.ps1"
    }
    "2" {
        Write-Host ""
        & "$PSScriptRoot\scripts\deploy.ps1"
    }
    "3" {
        Write-Host ""
        & "$PSScriptRoot\scripts\deploy_backend.ps1"
    }
    "4" {
        Write-Host ""
        & "$PSScriptRoot\scripts\deploy_frontend.ps1"
    }
    "5" {
        Write-Host ""
        & "$PSScriptRoot\scripts\start_local.ps1"
    }
    "6" {
        Write-Host ""
        & "$PSScriptRoot\scripts\stop_local.ps1"
    }
    "7" {
        Write-Host ""
        & "$PSScriptRoot\scripts\teardown_azure.ps1"
    }
    "0" {
        Write-Host "Bye!" -ForegroundColor Gray
    }
    default {
        Write-Host "Invalid option. Run .\run.ps1 again." -ForegroundColor Red
    }
}
