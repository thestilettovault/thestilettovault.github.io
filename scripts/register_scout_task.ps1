# register_scout_task.ps1 — 8am daily heel scout (The Stiletto Vault)
# Run once AS ADMINISTRATOR:
#   powershell -ExecutionPolicy Bypass -File register_scout_task.ps1
#
# Replaces the old broken task (WindowsApps shim + crashing gothic_scout.py)
# with the clean daily_heel_scout.py on the real interpreter.

$TaskName  = "TheGothicVault-DailyScout"
$ScriptDir = "E:\PROJECTS\thegothicvault\scripts"
$Script    = "$ScriptDir\daily_heel_scout.py"

# Real pythonw (NOT the WindowsApps shim)
$PythonwCandidates = @(
    "C:\Users\ofera\AppData\Local\Python\pythoncore-3.14-64\pythonw.exe",
    "C:\Users\ofera\AppData\Local\Python\bin\pythonw.exe"
)
$Pythonw = $PythonwCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Pythonw) { Write-Host "ERROR: no real pythonw found" -ForegroundColor Red; exit 1 }

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$Action = New-ScheduledTaskAction -Execute $Pythonw -Argument "`"$Script`"" -WorkingDirectory $ScriptDir

# Daily 08:00, plus catch-up if the PC was off
$Trigger = New-ScheduledTaskTrigger -Daily -At 8:00AM

$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

$Principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive -RunLevel Limited

$Task = New-ScheduledTask -Action $Action -Trigger $Trigger -Settings $Settings `
    -Principal $Principal -Description "The Stiletto Vault 8am heel scout -> Telegram."

Register-ScheduledTask -TaskName $TaskName -InputObject $Task -Force

Write-Host "Registered: $TaskName" -ForegroundColor Green
Write-Host "Runner: $Pythonw"
Write-Host "Script: $Script"
$ti = Get-ScheduledTaskInfo -TaskName $TaskName
Write-Host "Next run: $($ti.NextRunTime)" -ForegroundColor Cyan
Write-Host ""
Write-Host "Test now (optional):  Start-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Gray
