param(
    [int]$ProcessId = 4368,
    [int]$DurationMinutes = 60,
    [int]$CheckIntervalMinutes = 3
)

$startTime = Get-Date
$logPath = "C:\workspace\cthulu\logs\Cthulu.log"
$reportPath = "C:\workspace\cthulu\SYSTEM_REPORT.md"

Write-Host "`n╔════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║   Cthulu 60-Minute Stability Monitor Started    ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host "  Process ID:     $ProcessId" -ForegroundColor White
Write-Host "  Start Time:     $($startTime.ToString('HH:mm:ss'))" -ForegroundColor White
Write-Host "  Duration:       $DurationMinutes minutes" -ForegroundColor White
Write-Host "  Check Interval: $CheckIntervalMinutes minutes" -ForegroundColor White
Write-Host ""

$lastLogPosition = if (Test-Path $logPath) { (Get-Item $logPath).Length } else { 0 }
$errorCount = 0
$warningCount = 0
$checkCount = 0
$crashDetected = $false

function Update-SystemReport {
    param(
        [string]$Status,
        [int]$Errors,
        [int]$Warnings,
        [int]$Checks,
        [datetime]$Start
    )
    
    $elapsed = [math]::Round(((Get-Date) - $Start).TotalMinutes, 2)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    
    $statusSection = @"

### Live Monitoring Status
**Last Update:** $timestamp UTC  
**Elapsed Time:** $elapsed / $DurationMinutes minutes  
**Process Status:** $Status  
**Total Checks:** $Checks  
**Total Errors:** $Errors  
**Total Warnings:** $Warnings  
**Health:** $(if ($Errors -eq 0 -and $Status -eq "Running") { "✅ HEALTHY" } elseif ($Status -like "*Stopped*") { "🔴 STOPPED" } else { "⚠️ ISSUES" })

"@
    
    if (Test-Path $reportPath) {
        $content = Get-Content $reportPath -Raw
        if ($content -match "(?s)(### Live Monitoring Status.*?)\n\n") {
            $content = $content -replace "(?s)### Live Monitoring Status.*?\n\n", $statusSection
        }
        else {
            $insertPoint = $content.IndexOf("### Next Steps")
            if ($insertPoint -gt 0) {
                $content = $content.Insert($insertPoint, $statusSection)
            }
        }
        Set-Content -Path $reportPath -Value $content -NoNewline
    }
}

while (((Get-Date) - $startTime).TotalMinutes -lt $DurationMinutes) {
    $checkCount++
    $currentTime = Get-Date
    $elapsed = [math]::Round(((Get-Date) - $startTime).TotalMinutes, 2)
    $remaining = [math]::Round($DurationMinutes - $elapsed, 2)
    
    Write-Host "`n┌────────────────────────────────────────────────────┐" -ForegroundColor Yellow
    Write-Host "│ Check #$checkCount - $($currentTime.ToString('HH:mm:ss')) | $elapsed/$DurationMinutes min │" -ForegroundColor Yellow
    Write-Host "└────────────────────────────────────────────────────┘" -ForegroundColor Yellow
    
    $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    
    if ($proc) {
        $cpu = [math]::Round($proc.CPU, 2)
        $mem = [math]::Round($proc.WorkingSet / 1MB, 2)
        Write-Host "  ✅ Process Running (PID: $ProcessId)" -ForegroundColor Green
        Write-Host "     CPU: ${cpu}s | Memory: ${mem} MB" -ForegroundColor Cyan
        
        if (Test-Path $logPath) {
            $currentLogSize = (Get-Item $logPath).Length
            if ($currentLogSize -gt $lastLogPosition) {
                $newLines = Get-Content $logPath -Tail 100
                $errors = $newLines | Select-String -Pattern "(ERROR|CRITICAL|Exception|Traceback|AttributeError)" | Select-Object -First 5
                $warnings = $newLines | Select-String -Pattern "WARNING" | Select-Object -First 3
                
                if ($errors) {
                    Write-Host "  🔴 ERRORS DETECTED:" -ForegroundColor Red
                    $errors | ForEach-Object {
                        Write-Host "     $_" -ForegroundColor Red
                        $errorCount++
                    }
                    Write-Host "`n  🛑 ERRORS FOUND - STOPPING MONITORING..." -ForegroundColor Red
                    $crashDetected = $true
                    break
                }
                elseif ($warnings) {
                    Write-Host "  ⚠️  Warnings:" -ForegroundColor Yellow
                    $warnings | ForEach-Object {
                        Write-Host "     $_" -ForegroundColor Yellow
                        $warningCount++
                    }
                }
                else {
                    Write-Host "  ✅ No issues in logs" -ForegroundColor Green
                }
                
                $lastLogPosition = $currentLogSize
            }
        }
    }
    else {
        Write-Host "  🔴 PROCESS NOT FOUND!" -ForegroundColor Red
        $crashDetected = $true
        break
    }
    
    Update-SystemReport -Status "Running" -Errors $errorCount -Warnings $warningCount -Checks $checkCount -Start $startTime
    
    Write-Host "`n  Stats: Errors=$errorCount | Warnings=$warningCount" -ForegroundColor Cyan
    
    if (((Get-Date) - $startTime).TotalMinutes -lt $DurationMinutes) {
        Write-Host "  ⏳ Next check in $CheckIntervalMinutes minutes..." -ForegroundColor Gray
        Start-Sleep -Seconds ($CheckIntervalMinutes * 60)
    }
}

$totalDuration = [math]::Round(((Get-Date) - $startTime).TotalMinutes, 2)

Write-Host "`n╔════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║          Monitoring Session Complete            ║" -ForegroundColor Green
Write-Host "╚════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host "  Duration: $totalDuration minutes" -ForegroundColor White
Write-Host "  Checks: $checkCount" -ForegroundColor White
Write-Host "  Errors: $errorCount" -ForegroundColor $(if ($errorCount -eq 0) { "Green" } else { "Red" })
Write-Host "  Warnings: $warningCount" -ForegroundColor $(if ($warningCount -eq 0) { "Green" } else { "Yellow" })

if ($crashDetected) {
    Write-Host "`n  STATUS: 🔴 ISSUES DETECTED" -ForegroundColor Red
    Update-SystemReport -Status "Stopped (issues)" -Errors $errorCount -Warnings $warningCount -Checks $checkCount -Start $startTime
    exit 1
}
elseif ($errorCount -eq 0 -and $totalDuration -ge $DurationMinutes) {
    Write-Host "`n  STATUS: ✅ SUCCESS - 60 minutes error-free!" -ForegroundColor Green
    Update-SystemReport -Status "Completed successfully" -Errors $errorCount -Warnings $warningCount -Checks $checkCount -Start $startTime
    exit 0
}
else {
    Write-Host "`n  STATUS: ⚠️  INCOMPLETE" -ForegroundColor Yellow
    Update-SystemReport -Status "Incomplete" -Errors $errorCount -Warnings $warningCount -Checks $checkCount -Start $startTime
    exit 2
}
