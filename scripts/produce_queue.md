# Stiletto Vault — Auto-Producer (queue runner)

You are running headless. Task: PREPARE the Magnific board for the next approved
lead and tell Ofer it is ready. Ofer presses Run himself in the Magnific app, because
Unlimited (free) applies only there; API runs (spaces_run) cost credits.
**NEVER call spaces_run.** One lead at a time: the board holds one shoe.
**Stop at the ads. Never generate video** — the video (the expensive step) runs
only after Ofer picks an ad, in a separate flow.

## Steps

1. Read `E:/PROJECTS/thegothicvault/data/production_queue.json`.
   If it is missing, empty, or no entry has `status == "approved"` → print
   "queue empty — nothing to produce" and STOP. Do nothing else.

   If ANY entry already has `status == "board_ready"` → the board is waiting for Ofer.
   Print "board busy: waiting for Ofer's Run on <slug>" and STOP.

2. Take the NEWEST entry with `status == "approved"` (the shoe Ofer approved most
   recently; exactly ONE per run):

   a. slug = the entry's `local_asset` WITHOUT the leading `GELEM/` (so it includes the
      date folder, e.g. `2026-10-13/stiletto-heels-3256...`). Never just the basename.
      Get it with: `py -3 E:/PROJECTS/thegothicvault/scripts/orchestrator.py slug-of "<local_asset>"`
      Use that exact string for the GELEM folder and every orchestrator command below.

   b. Upload the source: `mcp__magnific__creations_upload_image(url = entry.image_url)`
      → note the returned `identifier` (SOURCE_ID).

   c. Point the Space at it. Since 2026-10-09 the Space uses ONE reference image:
      Creation node `0114e22a-6027-490e-aeca-b1b428d8ca91` (panel 1b00f6ed). It is the
      ONLY image wired into the concept builder (5ec8e287) and the campaign image
      generator (93b85932). Do NOT re-wire other creation nodes into them.
      `mcp__magnific__spaces_patch_node(spaceId="a2796464-3570-4e02-aa77-65f3f4322d9f",
        patches=[{"nodeId":"0114e22a-6027-490e-aeca-b1b428d8ca91",
                  "patch":{"data":{"creationIdentifier":"<SOURCE_ID>"}}}])`
      Verify with `spaces_get_nodes` that 0114e22a has `creationIdentifier == SOURCE_ID`
      AND that 93b85932 has the shoe (0114e22a) + Ina's body (04bad276) + legs in heels
      (427d4b28) as `reference`. OPEN-TOE shoe (toes show): also wire bare feet (e7ab3fd2)
      and arched foot (f738222d); CLOSED toe: leave those two unwired (they confuse it).
      The generator model stays Nano Banana Pro (imagen-nano-banana-2). Never change Ina's nodes. Anything else
      feeding it → STOP and report (wrong-shoe / wrong-model blend risk).

   c2. Write the shot brief for THIS shoe (stylist + trend agents). Look at
      source.jpg, then read `E:/PROJECTS/thegothicvault/data/agents/ina.md`,
      `.../data/agents/stylist.md` and `.../data/agents/poses.md`. Every shot is INA
      (face never visible). Pick 4 DIFFERENT shots from "Ina's camera roll" in poses.md (2 set + 2 life), all different,
      >=2 knee-down / shoe-dominant, and one outfit per shot from the stylist for that
      moment (never the same outfit twice in this run).
      Also write Ina's post caption for this shoe (ina.md "Her voice") into
      `GELEM/<slug>/_CAPTION.md`: 1-3 short first-person lines, no URL. The publisher
      appends the deal (if any) and `link in bio 🔗 #ad #affiliate` itself.
      The Space needs FOUR SEPARATE texts (one per shot): four text nodes feed the list
      "Shot brief list (4 shots)" (3250b608), which feeds the concept builder once per
      item = 4 prompts = 4 images. NEVER merge the 4 shots into one text: one text makes
      ONE collage image (this broke the 2026-10-12 run). Patch all four in one call:
      `spaces_patch_node(patches=[
        {"nodeId":"7c63f16a-228e-49b3-b48c-20c233e8d891","patch":{"data":{"text":"<shot 1>"}}},
        {"nodeId":"1a8a344e-64b4-4827-9e34-8082227301c8","patch":{"data":{"text":"<shot 2>"}}},
        {"nodeId":"785c31aa-df92-49ae-90d2-978fb0639fe9","patch":{"data":{"text":"<shot 3>"}}},
        {"nodeId":"744723e2-3ec1-4988-b904-97b1b5c8a17c","patch":{"data":{"text":"<shot 4>"}}}])`
      Each shot text: `<pose id> <frame/pose/camera/setting>. OUTFIT: <...>. The shoes
      exactly as the reference, sharp, fully visible, worn. Single frame, no text.`
      Also save the 4 shots to `GELEM/<slug>/_BRIEF.md` (so we can learn which briefs win).

   d. Tell Ofer the board is ready (Telegram message with a "done" button):
      `py -3 E:/PROJECTS/thegothicvault/scripts/orchestrator.py ready <slug>`
      (copy source.jpg into GELEM/<slug>/ first so the message shows the shoe).

   e. Mark the queue entry (never edit the JSON by hand):
      `py -3 E:/PROJECTS/thegothicvault/scripts/orchestrator.py queue-set <slug> board_ready`
      STOP.
      When Ofer taps the button, run_collect.bat follows collect_queue.md.

3. Print a one-line summary: how many leads produced, how many skipped, any errors.

## Guardrails
- NEVER call spaces_run / spaces_run_status here (credits). Ofer runs the board.
- One lead per run. Never touch entries whose status is not `approved`.
- Never run the video generator node.
- If the lead errors, log it, leave its status as `approved`, and STOP.
- Never hand-edit production_queue.json or orchestrator_state.json; use the orchestrator
  CLI (`queue-set`, `set-status`, `ready`).
- Never call a generating or paid Magnific tool (images_generate, video_generate, upscale,
  variations, ...); the runner blocks them anyway.
