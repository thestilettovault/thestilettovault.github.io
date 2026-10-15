# Stiletto Vault: collect the ads after Ofer pressed Run (headless)

Ofer ran the ads board in the Magnific app and tapped "✅ הרצתי" in Telegram.
Task: fetch his 4 new ad images, QA them, send them for his A/B/C/D pick, then
prepare the board for the next shoe. **NEVER call spaces_run** or any generating Magnific tool (credits; the runner blocks them).

## Steps

1. Read `E:/PROJECTS/thegothicvault/data/production_queue.json` and
   `E:/PROJECTS/thegothicvault/data/orchestrator_state.json`. The lead to collect is the
   queue entry with `status == "board_ready"`. Its slug = `local_asset` WITHOUT the leading
   `GELEM/` (e.g. `2026-10-13/stiletto-heels-3256...`):
   `py -3 E:/PROJECTS/thegothicvault/scripts/orchestrator.py slug-of "<local_asset>"`.
   Its orchestrator state must have `status == "collecting"` (the Telegram bot sets it
   when Ofer taps the button) and holds `board_ready_ts` (unix seconds).
   If the state is still `board_ready` (manual start): run
   `py -3 E:/PROJECTS/thegothicvault/scripts/orchestrator.py claim <slug>` first; if that
   fails, someone else is collecting - STOP.
   No such lead / state is neither → STOP.

   ON ANY FAILURE OR EARLY STOP after this point (fewer than 4 images, download error,
   send error, anything unexpected) restore the slug so Ofer can tap again:
   `py -3 E:/PROJECTS/thegothicvault/scripts/orchestrator.py set-status <slug> board_ready`
   Never edit the JSON files by hand.

2. Find the 4 images Ofer just made:
   `mcp__magnific__creations_search(from="history", fileType="image",
     dateStart=<board_ready_ts as ISO 8601 UTC>, orderBy="created_at",
     orderDirection="desc", perPage=12, full=true)`
   Keep only square (1:1) images created after board_ready_ts. Take the 4 OLDEST of
   those (the first run after the board was prepared), in creation order = A, B, C, D.
   - Fewer than 4 → the run is not finished or failed. Send Telegram text
     "⚠️ <slug>: אני רואה רק N תמונות. אם הריצה הסתיימה, לחץ שוב על הכפתור."
     with `py -3 -c "import sys; sys.path.insert(0, r'E:/PROJECTS/thegothicvault/scripts'); import telegram_sender as t; t.send_text('<message>', parse_mode=None)"`,
     run the `set-status <slug> board_ready` restore above, STOP.

3. Download to `E:/PROJECTS/thegothicvault/GELEM/<slug>/ad_A.jpg … ad_D.jpg` with curl
   (source.jpg is already there).

4. QA (data/agents/qa.md): LOOK at ad_A…ad_D next to source.jpg. Write
   `GELEM/<slug>/_QA.md`, one line per ad (`A ✅` / `B ⚠️ <reason>`). Never regenerate.

5. `py -3 E:/PROJECTS/thegothicvault/scripts/orchestrator.py send <slug>`
   If it exits non-zero (nothing reached Telegram) → restore with `set-status` as above, STOP.
   Otherwise: `py -3 E:/PROJECTS/thegothicvault/scripts/orchestrator.py queue-set <slug> awaiting_choice`

6. Board is free again: follow `E:/PROJECTS/thegothicvault/scripts/produce_queue.md`
   to prepare the NEXT approved shoe (it sends the next "הלוח מוכן" message).

7. Print one line: collected <slug> (N ads, QA summary) + next shoe prepared or none.
