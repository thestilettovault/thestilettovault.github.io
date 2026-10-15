# register_task.ps1 — Register TheGothicVault Bot as a resilient Scheduled Task
# Run once: powershell -ExecutionPolicy Bypass -File register_task.ps1
#
# Fixes the "dies every 1-2 days" problem:
#   - Uses pythonw.exe → NO console window that can be closed by accident
#     (the old task used python.exe; a clean window-close = exit 0 = no restart)
#   - Triggers at logon AND every 10 min (self-heal if the whole process is gone)
#   - MultipleInstances IgnoreNew + the bot's own socket lock → never a 409
#   - The bot also self-restarts in-process (supervisor loop) on network death

$TaskName   = "TheGothicVault-TelegramBot"
$ScriptDir  = "E:\PROJECTS\thegothicvault\scripts"
$BotScript  = "$ScriptDir\telegram_bot.py"

# Resolve the REAL pythonw.exe. NOTE: (Get-Command python) resolves to the
# broken WindowsApps Store shim (App Execution Alias) which is NOT a real
# interpreter — that would silently break the task. Prefer known-good paths.
$PythonwCandidates = @(
    "C:\Users\ofera\AppData\Local\Python\bin\pythonw.exe",
    "C:\Users\ofera\AppData\Local\Python\pythoncore-3.14-64\pythonw.exe"
)
$PythonwExe = $PythonwCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $PythonwExe) {
    # Fall back to the py launcher's interpreter dir
    $realPy = (& py -3 -c "import sys; print(sys.executable)") 2>$null
    if ($realPy) { $PythonwExe = Join-Path (Split-Path -Parent $realPy) "pythonw.exe" }
}
if (-not $PythonwExe -or -not (Test-Path $PythonwExe)) {
    Write-Host "ERROR: could not locate a real pythonw.exe. Aborting." -ForegroundColor Red
    exit 1
}

# Remove existing task if any
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# Action: pythonw telegram_bot.py (no window)
$Action = New-ScheduledTaskAction `
    -Execute $PythonwExe `
    -Argument "`"$BotScript`"" `
    -WorkingDirectory $ScriptDir

# Triggers: at logon + a repeating 10-min heartbeat that re-launches if the
# process is gone (IgnoreNew makes the heartbeat a no-op while it's alive).
$TriggerLogon = New-ScheduledTaskTrigger -AtLogOn
$TriggerRepeat = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes 10) `
    -RepetitionDuration (New-TimeSpan -Days 9999)

# Settings: restart on failure, single instance, no time limit
$Settings = New-ScheduledTaskSettingsSet `
    -RestartCount 99 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

# Run as current user, no admin needed
$Principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive `
    -RunLevel Limited

$Task = New-ScheduledTask `
    -Action $Action `
    -Trigger $TriggerLogon, $TriggerRepeat `
    -Settings $Settings `
    -Principal $Principal `
    -Description "TheGothicVault Telegram curation bot. Windowless, single-instance, self-healing."

Register-ScheduledTask -TaskName $TaskName -InputObject $Task -Force

Write-Host "Registered: $TaskName" -ForegroundColor Green
Write-Host "Runner: $PythonwExe"
Write-Host "Script: $BotScript"
Write-Host ""

# Start it now
Write-Host "Starting bot now..." -ForegroundColor Cyan
Start-ScheduledTask -TaskName $TaskName
Start-Sleep 4

$State = (Get-ScheduledTask -TaskName $TaskName).State
Write-Host "Task state: $State" -ForegroundColor $(if ($State -eq "Running") { "Green" } else { "Yellow" })
Write-Host ""
Write-Host "Verify it is polling:  Get-Content '$ScriptDir\bot_callbacks.log' -Tail 5" -ForegroundColor Gray
