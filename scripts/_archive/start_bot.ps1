# start_bot.ps1 — TheGothicVault Telegram Bot launcher
# Run once: powershell -ExecutionPolicy Bypass -File start_bot.ps1
# The bot runs in background and auto-restarts on crash.

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BotScript  = Join-Path $ScriptDir "telegram_bot.py"
$LogFile    = Join-Path $ScriptDir "bot.log"

Write-Host "Starting TheGothicVault Telegram Bot..." -ForegroundColor Cyan
Write-Host "Log: $LogFile"
Write-Host "Press Ctrl+C to stop."
Write-Host ""

while ($true) {
    $start = Get-Date
    Write-Host "[$start] Bot starting..." -ForegroundColor Green
    Add-Content $LogFile "[$start] Bot starting"

    & python $BotScript 2>&1 | Tee-Object -Append -FilePath $LogFile

    $elapsed = (Get-Date) - $start
    if ($elapsed.TotalSeconds -lt 10) {
        Write-Host "Bot crashed too fast — waiting 30s before restart" -ForegroundColor Red
        Add-Content $LogFile "[(Get-Date)] Crashed fast, waiting 30s"
        Start-Sleep 30
    } else {
        Write-Host "Bot stopped, restarting in 5s..." -ForegroundColor Yellow
        Start-Sleep 5
    }
}
