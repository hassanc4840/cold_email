@echo off
echo Starting Nexariza Backend (FastAPI)...
start "Nexariza Backend" cmd /k "cd /d "%~dp0" && python main.py"

echo Starting Nexariza Frontend (React/Vite)...
start "Nexariza Frontend" cmd /k "cd /d "%~dp0frontend" && npm run dev"

echo.
echo Both servers are launching in separate windows:
echo - Backend:  http://127.0.0.1:8000
echo - Frontend: http://localhost:5173
echo.
pause
