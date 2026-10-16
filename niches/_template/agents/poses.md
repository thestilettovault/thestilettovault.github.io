# Trend agent: pose & frame library for {product_noun} content

STATUS: SKELETON. Replace with a real library built from measured trend data for {product_noun_plural}
(saved posts, TikTok / Instagram scans). Each entry: id | frame | pose | camera | setting. Add `score:` when known.

## Camera logic (engine rule, keep it)
Every shot answers first: WHO IS HOLDING THE CAMERA, AND WHY WOULD THE PERSONA POST THIS?
Define the cameras for this niche and a mix per {product_noun}, e.g.
PHONE (the persona's own phone: selfie / mirror / POV / self-timer, iPhone look) x2 +
SET (a photographer on a paid shoot, campaign finish) x1 + BTS (crew phone between takes) x1.
Each library id below belongs to one camera; every shot brief starts with `CAMERA: ...`.
A cinematic third-person view of a private moment with nobody there = QA fail.
Captions follow the camera (a PHONE moment is captioned as her moment, SET as work).

## Library
P01 | TODO frame | TODO pose | TODO camera | TODO setting
P02 | TODO
P03 | TODO
(aim for 8-10 entries that show the {product_noun} clearly and look native to the platform)

## Persona camera roll (use first)
Every image is one personal moment, as if from a phone or a crew member's camera.
C01 | work: TODO
C02 | work: TODO
C03 | life: TODO
C04 | life: TODO
Each shot also gets ONE personal detail (coffee, receipt, hair clip...).

## HARD RULES (copy the failures you have actually seen)
1. TODO: exact count / placement of the {product_noun} per image.
2. ONE simple action per shot.
3. TODO: framing rule that protects the persona's anonymity (if any).
4. Write each shot as a full prompt: THE CONCEIT + SHOT + LIGHT + CAMERA AUTHENTICITY, ending with the count rule and "No text."

## Rules
- Four shots per {product_noun} = four DIFFERENT entries; at least two {product_noun}-dominant.
- Never a split-screen, collage or before/after.
- The {product_noun} is always fully visible and sharp.
