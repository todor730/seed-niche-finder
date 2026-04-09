@echo off
setlocal

cd /d "%~dp0"

set "API_BASE=http://127.0.0.1:8000"
set /p SEED_NICHE=Enter niche: 

if "%SEED_NICHE%"=="" (
    echo.
    echo No niche entered.
    pause
    exit /b 1
)

echo.
echo Creating research run for: %SEED_NICHE%
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop';" ^
  "try { Invoke-RestMethod -Method Get -Uri '%API_BASE%/api/v1/health' | Out-Null } catch { Write-Host 'API is not running at %API_BASE%.'; exit 2 };" ^
  "$body = @{ seed_niche = '%SEED_NICHE%'; config = @{ max_candidates = 20; top_k = 10 } } | ConvertTo-Json -Depth 5;" ^
  "$response = Invoke-RestMethod -Method Post -Uri '%API_BASE%/api/v1/research-runs' -ContentType 'application/json' -Body $body;" ^
  "$response | ConvertTo-Json -Depth 10"

if errorlevel 1 (
    echo.
    echo Failed to create research run.
    pause
    exit /b 1
)

echo.
echo Run created successfully.
pause

endlocal
