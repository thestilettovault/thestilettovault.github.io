@echo off
title TheGothicVault Telegram Bot
cd /d "E:\PROJECTS\thegothicvault\scripts"
echo [%date% %time%] Bot starting... >> bot.log

:loop
echo Starting bot...
python telegram_bot.py >> bot.log 2>&1
echo [%date% %time%] Bot stopped (exit %ERRORLEVEL%), restarting in 5s... >> bot.log
echo Bot stopped. Restarting in 5 seconds...
timeout /t 5 /nobreak
goto loop
