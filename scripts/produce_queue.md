# Stiletto Vault — Auto-Producer (queue runner)

You are running headless. Task: drain the production queue by turning each approved
lead into 4 ad candidates and pushing them to Telegram for Ofer's A/B/C/D pick.
**Stop at the ads. Never generate video** — the video (the expensive step) runs
only after Ofer picks an ad, in a separate flow.

## Steps

1. Read `E:/PROJECTS/thegothicvault/data/production_queue.json`.
   If it is missing, empty, or no entry has `status == "approved"` → print
   "queue empty — nothing to produce" and STOP. Do nothing else.

2. For EACH entry with `status == "approved"` (process at most 5 per run):

   a. slug = run `py -3 E:/PROJECTS/thegothicvault/scripts/space_runner.py` is not
      needed — derive it the same way: AliExpress `/item/<id>` → `<title-slug>-<id>`.
      The folder is the entry's `local_asset` basename; use that slug.

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
      AND that 93b85932 has exactly ONE incoming `reference` connection (from 0114e22a).
      If anything else feeds it → STOP the run and report (wrong-shoe blend risk).

   d. Run the ads chain (NOT the video):
      `mcp__magnific__spaces_run(spaceId="a2796464-3570-4e02-aa77-65f3f4322d9f",
        startNodeId="5ec8e287-6633-44a9-bcaf-2562c656728e", mode="downstream")`
      Poll `spaces_run_status` until `allTerminal`. Collect the 4 creation ids from
      node `93b85932-6752-4bfa-a801-28fd3c0c097c`.

   e. `mcp__magnific__creations_wait` on the 4 ids → 4 render URLs.

   f. Download to `E:/PROJECTS/thegothicvault/GELEM/<slug>/ad_A.jpg … ad_D.jpg`
      with curl (also copy source.jpg there). Order A,B,C,D = the 4 ids in order.

   g. Send for the pick:
      `py -3 E:/PROJECTS/thegothicvault/scripts/orchestrator.py send <slug>`

   h. Set that entry's `status = "awaiting_choice"` in production_queue.json and save.

3. Print a one-line summary: how many leads produced, how many skipped, any errors.

## Guardrails
- Cap: 5 leads per run. If more are approved, leave the rest for the next run.
- Never touch entries whose status is not `approved`.
- Never run the video generator node here.
- CREDIT GUARD: one ads run must produce exactly 4 creations (all from 93b85932).
  After `spaces_run_status` is terminal, if `creationIdentifiers` has MORE than 4
  ids, the board was re-wired downstream of the ads node → STOP the whole run, do
  not process further leads, and print "CREDIT GUARD: run produced N images" so it
  is visible in producer.log. (2026-10-09: an extra chain made 24 images/run.)
- If any single lead errors, log it, leave its status as `approved`, and continue
  to the next — do not abort the whole run.
