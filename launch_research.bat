@echo off
setlocal

cd /d "%~dp0"

set "API_BASE=http://127.0.0.1:8000"
set "START_SCRIPT=%~dp0start_api.bat"
set "HTML_SCRIPT=%~dp0generate_html_report.py"
set "DEFAULT_PYTHON=C:\Users\Todor\AppData\Local\Programs\Python\Python314\python.exe"

if exist "%DEFAULT_PYTHON%" (
    set "PYTHON_CMD=%DEFAULT_PYTHON%"
) else if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_CMD=%~dp0.venv\Scripts\python.exe"
) else (
    set "PYTHON_CMD=python"
)

set /p SEED_NICHE=Enter niche: 

if "%SEED_NICHE%"=="" (
    echo.
    echo No niche entered.
    pause
    exit /b 1
)

echo.
echo Starting research run for: %SEED_NICHE%
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop';" ^
  "$apiBase = '%API_BASE%';" ^
  "$startScript = '%START_SCRIPT%';" ^
  "$htmlScript = '%HTML_SCRIPT%';" ^
  "$pythonCmd = '%PYTHON_CMD%';" ^
  "$seedNiche = '%SEED_NICHE%';" ^
  "$noBrowser = $env:BOOKFUNNEL_NO_BROWSER -eq '1';" ^
  "function Test-ApiHealth { try { Invoke-RestMethod -Method Get -Uri ($apiBase + '/api/v1/health') -TimeoutSec 3 | Out-Null; return $true } catch { return $false } }" ^
  "function Format-Value([object]$value) { if ($null -eq $value -or $value -eq '') { return 'n/a' } return [string]$value }" ^
  "if (-not (Test-ApiHealth)) {" ^
  "  Write-Host 'API is not running. Starting it now...';" ^
  "  if (Test-Path $startScript) {" ^
  "    Start-Process -FilePath 'cmd.exe' -ArgumentList '/c', ('\"' + $startScript + '\"') -WorkingDirectory (Split-Path -Parent $startScript) -WindowStyle Minimized | Out-Null;" ^
  "  } else {" ^
  "    Start-Process -FilePath $pythonCmd -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory (Split-Path -Parent $htmlScript) -WindowStyle Minimized | Out-Null;" ^
  "  }" ^
  "  $started = $false;" ^
  "  for ($i = 0; $i -lt 20; $i++) { Start-Sleep -Seconds 1; if (Test-ApiHealth) { $started = $true; break } }" ^
  "  if (-not $started) { throw 'API did not start in time.' }" ^
  "}" ^
  "Write-Host 'Collecting evidence and generating report...';" ^
  "$body = @{ seed_niche = $seedNiche; config = @{ max_candidates = 20; top_k = 10 } } | ConvertTo-Json -Depth 5;" ^
  "$runResponse = Invoke-RestMethod -Method Post -Uri ($apiBase + '/api/v1/research-runs') -ContentType 'application/json' -Body $body;" ^
  "$runId = $runResponse.data.id;" ^
  "$runDetails = (Invoke-RestMethod -Method Get -Uri ($apiBase + '/api/v1/research-runs/' + $runId)).data;" ^
  "$opportunities = (Invoke-RestMethod -Method Get -Uri ($apiBase + '/api/v1/research-runs/' + $runId + '/opportunities')).data;" ^
  "$createdExport = $null;" ^
  "$reportWarnings = @();" ^
  "$htmlPath = $null;" ^
  "try {" ^
  "  $exportBody = @{ format = 'json'; scope = 'full_run' } | ConvertTo-Json -Depth 3;" ^
  "  $createdExport = (Invoke-RestMethod -Method Post -Uri ($apiBase + '/api/v1/research-runs/' + $runId + '/exports') -ContentType 'application/json' -Body $exportBody).data;" ^
  "} catch { Write-Host ('Warning: full export generation failed: ' + $_.Exception.Message) }" ^
  "$topRecommendation = if ($opportunities -and @($opportunities).Count -gt 0) { $opportunities[0].title } else { 'No evidence-backed opportunity' };" ^
  "if ($createdExport -and $createdExport.storage_uri -and (Test-Path $createdExport.storage_uri)) {" ^
  "  try {" ^
  "    $exportPayload = Get-Content -Path $createdExport.storage_uri -Raw | ConvertFrom-Json;" ^
  "    $runPayload = @($exportPayload)[0];" ^
  "    if ($runPayload -and $runPayload.warnings) { $reportWarnings = @($runPayload.warnings | ForEach-Object { $_.message }) }" ^
  "    if ($runPayload -and $runPayload.niche_summaries -and @($runPayload.niche_summaries).Count -gt 0) { $topRecommendation = $runPayload.niche_summaries[0].niche_label }" ^
  "  } catch { Write-Host ('Warning: could not read report warnings from full export: ' + $_.Exception.Message) }" ^
  "}" ^
  "if (Test-Path $htmlScript) {" ^
  "  try {" ^
  "    $htmlLines = & $pythonCmd $htmlScript $runId 2>&1;" ^
  "    if ($LASTEXITCODE -eq 0 -and $htmlLines) {" ^
  "      $htmlPath = @($htmlLines)[-1].ToString().Trim();" ^
  "      if (-not $noBrowser -and $htmlPath -and (Test-Path $htmlPath)) { Start-Process -FilePath $htmlPath | Out-Null }" ^
  "    }" ^
  "  } catch { Write-Host ('Warning: HTML report generation failed: ' + $_.Exception.Message) }" ^
  "} else {" ^
  "  Write-Host 'Warning: generate_html_report.py was not found.';" ^
  "}" ^
  "$depth = $runDetails.depth_score;" ^
  "Write-Host '';" ^
  "Write-Host '=== RUN SUMMARY ===';" ^
  "Write-Host ('Run ID: ' + $runId);" ^
  "Write-Host ('Status: ' + $runDetails.status);" ^
  "if ($depth) {" ^
  "  Write-Host ('Depth Score: ' + (Format-Value $depth.score));" ^
  "  Write-Host ('Counts: queries=' + (Format-Value $depth.successful_queries_count) + '/' + (Format-Value $depth.attempted_queries_count) + ' items=' + (Format-Value $depth.source_items_count) + ' signals=' + (Format-Value $depth.extracted_signals_count) + ' clusters=' + (Format-Value $depth.signal_clusters_count) + ' hypotheses=' + (Format-Value $depth.niche_hypotheses_count) + ' failures=' + (Format-Value $depth.provider_failures_count));" ^
  "}" ^
  "Write-Host ('Top Recommendation: ' + $topRecommendation);" ^
  "if ($reportWarnings -and @($reportWarnings).Count -gt 0) {" ^
  "  Write-Host 'Warnings:';" ^
  "  foreach ($warning in @($reportWarnings) | Select-Object -First 3) { Write-Host ('- ' + $warning) }" ^
  "}" ^
  "if ($runDetails.error_message) { Write-Host ('Warning: ' + $runDetails.error_message) }" ^
  "if ($htmlPath) { Write-Host ('HTML Report: ' + $htmlPath) } else { Write-Host 'HTML Report: not generated' }" ^
  "if ($createdExport -and $createdExport.storage_uri) { Write-Host ('Full Export: ' + $createdExport.storage_uri) } elseif ($createdExport -and $createdExport.file_name) { Write-Host ('Full Export: ' + $createdExport.file_name) } else { Write-Host 'Full Export: not created' }"

if errorlevel 1 (
    echo.
    echo Failed to run research.
    pause
    exit /b 1
)

echo.
pause

endlocal
