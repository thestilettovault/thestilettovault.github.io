@echo off
REM Stiletto Vault auto-producer — drains production_queue.json into ad candidates
REM on Telegram. Wired to a daily Windows Task (~10:00). Stops at ads; video only
REM runs after Ofer picks in Telegram. Logs to scripts\producer.log.
cd /d E:\PROJECTS\thegothicvault
echo ================================================================ >> scripts\producer.log
echo producer run: %date% %time% >> scripts\producer.log
"C:\Users\ofera\.local\bin\claude.exe" -p "Read scripts/produce_queue.md and follow it exactly to drain the Stiletto production queue. Stop at the ads and push them to Telegram; never generate video." --dangerously-skip-permissions >> scripts\producer.log 2>&1
echo producer done: %date% %time% >> scripts\producer.log
REM close the loop: heels Ofer picked in Telegram -> image-only post, next free day (0 credits)
py -3 scripts\auto_schedule.py --apply >> scripts\producer.log 2>&1
echo auto schedule done: %date% %time% >> scripts\producer.log
REM self-heal TikTok "at capacity" failures: revive failed posts into future
REM openings, capped/spread so we never cluster and trip the limit again.
py -3 scripts\tiktok_retry.py --spread --apply >> scripts\producer.log 2>&1
py -3 scripts\tiktok_retry.py --apply >> scripts\producer.log 2>&1
echo tiktok retry done: %date% %time% >> scripts\producer.log
REM refresh the control dashboard (funnel/shoes/sales) and push it live
py -3 scripts\collect_metrics.py --push >> scripts\producer.log 2>&1
echo dashboard refreshed: %date% %time% >> scripts\producer.log
