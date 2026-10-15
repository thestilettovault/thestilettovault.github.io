@echo off
REM Stiletto Vault: Ofer tapped "ran the board" in Telegram -> collect the 4 ads,
REM QA, send for the pick, prepare the next shoe. Started by telegram_bot (boardrun).
cd /d E:\PROJECTS\thegothicvault
echo ================================================================ >> scripts\collect.log
echo collect run: %date% %time% >> scripts\collect.log
"C:\Users\ofera\.local\bin\claude.exe" -p "Read scripts/collect_queue.md and follow it exactly. Never call spaces_run." --dangerously-skip-permissions >> scripts\collect.log 2>&1
echo collect done: %date% %time% >> scripts\collect.log
