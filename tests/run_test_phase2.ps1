
$logFile = "$PWD/server_test.log"
$current = $PWD
Write-Host "[*] Starting Server for Test Phase 2..." -ForegroundColor Cyan

# Start server in background ensure CWD is correct
$serverJob = Start-Job -ScriptBlock {
    Set-Location $using:current
    python web/server.py > server_test.log 2>&1
}

Write-Host "[*] Waiting 5 seconds for server boot..."
Start-Sleep -Seconds 5

# Check if server is running (port 5000)
# (Optional skip)

Write-Host "[*] Running Test Script..." -ForegroundColor Cyan
python tests/test_phase2_server.py

# Cleanup
Write-Host "[*] Stopping Server..." -ForegroundColor Yellow
Stop-Job $serverJob
Remove-Job $serverJob

# If Python process persists (uvicorn), kill it
Get-Process | Where-Object { $_.Name -eq "python" -and $_.CommandLine -like "*web/server.py*" } | Stop-Process -Force -ErrorAction SilentlyContinue

Write-Host "[*] Test Complete." -ForegroundColor Green
