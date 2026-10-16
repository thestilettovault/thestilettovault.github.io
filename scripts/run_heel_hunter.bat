@echo off
REM Stiletto Vault Heel Hunter ? daily 07:30. Activates any "aff <domain> <link>"
REM Telegram replies, then sends signup cards for new heel brands. Never registers
REM anywhere itself. Logs to scripts\heel_hunter.log.
cd /d E:\PROJECTS\thegothicvault\scripts
echo ================================================================ >> heel_hunter.log
echo heel hunter run: %date% %time% >> heel_hunter.log
py -3 heel_hunter.py activate >> heel_hunter.log 2>&1
py -3 heel_hunter.py cards >> heel_hunter.log 2>&1
REM morning brief to Telegram: what needs Ofer today, today's posts, deltas, failures
py -3 morning_brief.py --send >> heel_hunter.log 2>&1
echo heel hunter done: %date% %time% >> heel_hunter.log
