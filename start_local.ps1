# Start Memory Assistant locally (backend + frontend)
# Usage: Open PowerShell and run: .\start_local.ps1

Write-Host "Starting Memory Assistant locally..." -ForegroundColor Cyan

# Start backend in a new window
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot\server'; Write-Host 'BACKEND starting on http://localhost:8000' -ForegroundColor Green; python -m uvicorn main:app --host 0.0.0.0 --port 8000"

# Start frontend in a new window
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot\client'; Write-Host 'FRONTEND starting on http://localhost:5173' -ForegroundColor Green; npx vite --host"

Write-Host ""
Write-Host "Two terminal windows opened:" -ForegroundColor Yellow
Write-Host "  Backend  -> http://localhost:8000"
Write-Host "  Frontend -> http://localhost:5173"
Write-Host ""
Write-Host "Open http://localhost:5173 in your browser." -ForegroundColor Cyan
Write-Host "Close the terminal windows to stop the servers." -ForegroundColor Gray
