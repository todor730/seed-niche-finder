@echo off
setlocal

cd /d "%~dp0"

set "API_BASE=http://127.0.0.1:8000"
set "START_SCRIPT=%~dp0start_api.bat"

set /p SEED_NICHE=Enter niche: 

if "%SEED_NICHE%"=="" (
    echo.
    echo No niche entered.
    pause
    exit /b 1
)

echo.
echo Running research for: %SEED_NICHE%
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop';" ^
  "$apiBase = '%API_BASE%';" ^
  "$startScript = '%START_SCRIPT%';" ^
  "$seedNiche = '%SEED_NICHE%';" ^
  "function Test-ApiHealth { try { Invoke-RestMethod -Method Get -Uri ($apiBase + '/api/v1/health') -TimeoutSec 3 | Out-Null; return $true } catch { return $false } }" ^
  "function Format-Number([object]$value) { if ($null -eq $value -or $value -eq '') { return 'n/a' } return [string]$value }" ^
  "if (-not (Test-ApiHealth)) {" ^
  "  Write-Host 'API is not running. Starting it now...';" ^
  "  Start-Process -FilePath 'cmd.exe' -ArgumentList '/c', ('\"' + $startScript + '\"') -WorkingDirectory (Split-Path -Parent $startScript) -WindowStyle Minimized | Out-Null;" ^
  "  $started = $false;" ^
  "  for ($i = 0; $i -lt 20; $i++) { Start-Sleep -Seconds 1; if (Test-ApiHealth) { $started = $true; break } }" ^
  "  if (-not $started) { throw 'API did not start in time.' }" ^
  "}" ^
  "$body = @{ seed_niche = $seedNiche; config = @{ max_candidates = 20; top_k = 10 } } | ConvertTo-Json -Depth 5;" ^
  "$runResponse = Invoke-RestMethod -Method Post -Uri ($apiBase + '/api/v1/research-runs') -ContentType 'application/json' -Body $body;" ^
  "$run = $runResponse.data;" ^
  "$runId = $run.id;" ^
  "$runDetails = (Invoke-RestMethod -Method Get -Uri ($apiBase + '/api/v1/research-runs/' + $runId)).data;" ^
  "$keywords = (Invoke-RestMethod -Method Get -Uri ($apiBase + '/api/v1/research-runs/' + $runId + '/keywords')).data;" ^
  "$opportunities = (Invoke-RestMethod -Method Get -Uri ($apiBase + '/api/v1/research-runs/' + $runId + '/opportunities')).data;" ^
  "$createdExport = $null;" ^
  "$exports = $null;" ^
  "try {" ^
  "  $exportBody = @{ format = 'json'; scope = 'full_run' } | ConvertTo-Json -Depth 3;" ^
  "  $createdExport = (Invoke-RestMethod -Method Post -Uri ($apiBase + '/api/v1/research-runs/' + $runId + '/exports') -ContentType 'application/json' -Body $exportBody).data;" ^
  "  $exports = (Invoke-RestMethod -Method Get -Uri ($apiBase + '/api/v1/research-runs/' + $runId + '/exports')).data;" ^
  "} catch { Write-Host ('Export step skipped: ' + $_.Exception.Message) }" ^
  "Write-Host '';" ^
  "Write-Host ('Run ID: ' + $runId);" ^
  "Write-Host ('Status: ' + $runDetails.status);" ^
  "if ($runDetails.error_message) { Write-Host ('Error: ' + $runDetails.error_message) }" ^
  "if ($runDetails.depth_score) {" ^
  "  $depth = $runDetails.depth_score;" ^
  "  Write-Host ('Depth Score: ' + (Format-Number $depth.score));" ^
  "  Write-Host ('  Queries=' + (Format-Number $depth.source_queries_count) + ' | Attempted=' + (Format-Number $depth.attempted_queries_count) + ' | Success=' + (Format-Number $depth.successful_queries_count));" ^
  "  Write-Host ('  Items=' + (Format-Number $depth.source_items_count) + ' | Signals=' + (Format-Number $depth.extracted_signals_count) + ' | Clusters=' + (Format-Number $depth.signal_clusters_count) + ' | Hypotheses=' + (Format-Number $depth.niche_hypotheses_count) + ' | Failures=' + (Format-Number $depth.provider_failures_count));" ^
  "  Write-Host ('  Providers with evidence=' + (Format-Number $depth.evidence_provider_count) + ' | Query success rate=' + (Format-Number $depth.breakdown.query_success_rate));" ^
  "}" ^
  "if ($runDetails.summary) {" ^
  "  Write-Host ('Summary: ' + $runDetails.summary.keyword_count + ' keywords, ' + $runDetails.summary.opportunity_count + ' opportunities, ' + $runDetails.summary.export_count + ' exports');" ^
  "}" ^
  "Write-Host '';" ^
  "Write-Host ('Keywords (' + (@($keywords).Count) + '):');" ^
  "if (-not $keywords -or @($keywords).Count -eq 0) { Write-Host '  (none)' } else { $i = 1; foreach ($keyword in $keywords) { $demand = if ($keyword.metrics) { $keyword.metrics.demand_score } else { $null }; $opp = if ($keyword.metrics) { $keyword.metrics.opportunity_score } else { $null }; Write-Host ('  ' + $i + '. ' + $keyword.keyword_text + ' [' + $keyword.status + ']'); if ($null -ne $demand -or $null -ne $opp) { Write-Host ('     demand=' + (Format-Number $demand) + ' | opportunity=' + (Format-Number $opp)) }; $i++ } }" ^
  "Write-Host '';" ^
  "Write-Host ('Opportunities (' + (@($opportunities).Count) + '):');" ^
  "if (-not $opportunities -or @($opportunities).Count -eq 0) { Write-Host '  (none)' } else { $i = 1; foreach ($opportunity in $opportunities) { Write-Host ('  ' + $i + '. ' + $opportunity.title); if ($opportunity.summary) { Write-Host ('     summary: ' + $opportunity.summary) }; if ($opportunity.score_breakdown) { Write-Host ('     scores: final=' + (Format-Number $opportunity.score_breakdown.opportunity_score) + ' | demand=' + (Format-Number $opportunity.score_breakdown.demand_score) + ' | competition=' + (Format-Number $opportunity.score_breakdown.competition_score)) }; if ($opportunity.rationale_summary) { Write-Host ('     rationale: ' + $opportunity.rationale_summary) }; $i++ } }" ^
  "Write-Host '';" ^
  "Write-Host 'Export:';" ^
  "if ($createdExport) { Write-Host ('  created: ' + $createdExport.id + ' [' + $createdExport.status + ']'); if ($createdExport.file_name) { Write-Host ('  file: ' + $createdExport.file_name) } } else { Write-Host '  (not created)' }" ^
  "if ($exports) { Write-Host ('  total exports for run: ' + @($exports).Count) }"

if errorlevel 1 (
    echo.
    echo Failed to run research.
    pause
    exit /b 1
)

echo.
pause

endlocal
