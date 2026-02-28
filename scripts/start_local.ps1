# Start FindIt locally (backend + frontend)
# Usage: Open PowerShell and run: .\start_local.ps1

Write-Host ""
Write-Host "=== FindIt - Local Start ===" -ForegroundColor Cyan
Write-Host ""

# -- Prerequisites check -----------------------------------------------
$failed = $false

# Python
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "  X  Python not found. Install Python 3.11+ from https://python.org" -ForegroundColor Red
    $failed = $true
} else {
    $pyVer = python --version 2>&1
    Write-Host "  OK Python: $pyVer" -ForegroundColor Green
}

# Node.js
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Host "  X  Node.js not found. Install from https://nodejs.org" -ForegroundColor Red
    $failed = $true
} else {
    $nodeVer = node --version 2>&1
    Write-Host "  OK Node.js: $nodeVer" -ForegroundColor Green
}

# Azure CLI login
$azAccount = az account show --query "user.name" -o tsv 2>$null
if (-not $azAccount) {
    Write-Host "  X  Not logged into Azure CLI. Run: az login" -ForegroundColor Red
    $failed = $true
} else {
    Write-Host "  OK Azure CLI: $azAccount" -ForegroundColor Green
}

# server/.env
if (-not (Test-Path "$PSScriptRoot\..\server\.env")) {
    Write-Host "  X  server\.env not found. Copy server\.env.example to server\.env and fill in values." -ForegroundColor Red
    $failed = $true
} else {
    $envContent = Get-Content "$PSScriptRoot\..\server\.env" -Raw
    if ($envContent -match "<your-") {
        Write-Host "  !  server\.env has placeholder values. Update with real keys." -ForegroundColor Yellow
    } else {
        Write-Host "  OK server\.env configured" -ForegroundColor Green
    }
}

if ($failed) {
    Write-Host ""
    Write-Host "Fix the above issues before starting." -ForegroundColor Red
    exit 1
}

# Check Azure storage account is reachable
if (Test-Path "$PSScriptRoot\..\server\.env") {
    $storageUrl = (Get-Content "$PSScriptRoot\..\server\.env" | Select-String "AZURE_STORAGE_ACCOUNT_URL=").ToString().Split("=",2)[1].Trim()
    $storageName = ($storageUrl -replace "https://","" -replace "\.blob\.core\.windows\.net","")
    $exists = az storage account show --name $storageName --query "name" -o tsv 2>$null
    if (-not $exists) {
        Write-Host ""
        Write-Host "  !  Storage account '$storageName' not found." -ForegroundColor Yellow
        Write-Host "     Run .\scripts\deploy_infra.ps1 to provision Azure infrastructure first." -ForegroundColor Yellow
        $answer = Read-Host "     Continue anyway? (y/n)"
        if ($answer -ne "y") { exit 1 }
    } else {
        Write-Host "  OK Storage account: $storageName" -ForegroundColor Green
    }
}

# -- Install dependencies if needed ------------------------------------
Write-Host ""
if (-not (Test-Path "$PSScriptRoot\..\client\node_modules")) {
    Write-Host "Installing frontend dependencies..." -ForegroundColor Yellow
    Push-Location "$PSScriptRoot\..\client"
    npm install --silent
    Pop-Location
}

# -- Start servers -----------------------------------------------------
Write-Host ""
Write-Host "Starting servers..." -ForegroundColor Cyan

# Start backend in a new window
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot\..\server'; pip install -q -r requirements.txt; Write-Host 'BACKEND starting on http://localhost:8000' -ForegroundColor Green; python -m uvicorn main:app --host 0.0.0.0 --port 8000"

# Start frontend in a new window
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot\..\client'; Write-Host 'FRONTEND starting on http://localhost:5173' -ForegroundColor Green; npx vite --host"

# -- Wait for servers --------------------------------------------------
Write-Host "Waiting for servers to be ready (backend takes ~30s)..." -ForegroundColor Gray
$ready = $false
for ($i = 0; $i -lt 15; $i++) {
    Start-Sleep -Seconds 5
    $be = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
    $fe = Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue
    if ($be -and $fe) { $ready = $true; break }
}

Write-Host ""
if ($ready) {
    Write-Host "=== Both servers are running! ===" -ForegroundColor Green
} else {
    Write-Host "=== Servers may still be starting - check the terminal windows ===" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "  Backend  -> http://localhost:8000" -ForegroundColor White
Write-Host "  Frontend -> http://localhost:5173" -ForegroundColor White
Write-Host ""
Write-Host "Open http://localhost:5173 in your browser." -ForegroundColor Cyan
Write-Host "Close the terminal windows to stop the servers." -ForegroundColor Gray
