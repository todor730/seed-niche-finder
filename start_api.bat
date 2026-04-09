@echo off
setlocal

cd /d "%~dp0"

set "APP_ENV=dev"
set "HOST=127.0.0.1"
set "PORT=8000"

set "PYTHON_EXE="
set "USE_PY_LAUNCHER=0"

if exist "C:\Users\Todor\AppData\Local\Programs\Python\Python314\python.exe" (
    set "PYTHON_EXE=C:\Users\Todor\AppData\Local\Programs\Python\Python314\python.exe"
) else if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
) else (
    where py >nul 2>nul
    if not errorlevel 1 (
        set "USE_PY_LAUNCHER=1"
    ) else (
        set "PYTHON_EXE=python"
    )
)

echo Starting Ebook Niche Research API...
echo APP_ENV=%APP_ENV%
echo URL=http://%HOST%:%PORT%
echo.

if "%USE_PY_LAUNCHER%"=="1" (
    py -3.14 -m uvicorn app.main:app --host %HOST% --port %PORT%
) else (
    "%PYTHON_EXE%" -m uvicorn app.main:app --host %HOST% --port %PORT%
)

if errorlevel 1 (
    echo.
    echo Failed to start the API.
    pause
)

endlocal
