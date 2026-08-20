Write-Host "Starting Nexariza System..." -ForegroundColor Cyan

# Start FastAPI Backend
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$PSScriptRoot'; python main.py"

# Start React Frontend
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$PSScriptRoot\frontend'; npm run dev"

Write-Host "Backend running at:  http://127.0.0.1:8000" -ForegroundColor Green
Write-Host "Frontend running at: http://localhost:5173" -ForegroundColor Green
