# QA agent: check every generated ad before Ofer sees it

Look at each of the 4 ads next to source.jpg. Report, never fix or regenerate on your own.

## Fail (⚠️) if any of these
1. Shoe count: not EXACTLY one pair, both worn (a shoe in her hand, a bare foot, a third
   shoe, a missing shoe, a shoe box or other shoes around) = fail.
2. Anatomy: wrong number of legs / feet / hands / arms, fused or missing toes, a foot
   without a leg, impossible joints, a third shoe.
3. Shoe mismatch vs source.jpg: different colour, heel height, toe shape, straps,
   ornaments, or an invented red sole / logo. Also fail the plain nude pump from Ina's
   character sheet appearing instead of the product.
4. Text: any letters, words, price, headline, logo or watermark burned into the image
   (images must be clean - no price / headline / text).
5. Layout: split-screen, collage, before/after, two panels.
6. Shoe not visible: covered by clothes, cropped off, out of focus, too small (< ~10% of frame).
7. INA's FACE IS VISIBLE: the crop must be at the collarbone; anything at or above the chin
   (chin, lips, eyes, a partly hidden face) = fail. Also fail if the model is clearly not Ina
   (skinny build, different hair) or wears the reference outfit (black blazer).
8. Face / skin badly distorted (melted, double face).
9. Feet not campaign-perfect (veins, redness, crooked or odd toes, wide or flat feet).
10. Toes visible but no pedicure, or polish that clashes with the shoe.
11. Camera logic: nobody could plausibly have taken this photo (a cinematic third-person
    view of a private moment, e.g. stepping out of a taxi, alone on a street at night), or
    the look contradicts its camera (a "phone" shot that looks like a studio campaign,
    a "set" shot that looks like a snapshot). Check against `_BRIEF.md`.

## Output (one line per ad, written to GELEM/<slug>/_QA.md and into the Telegram caption)
`A ✅` or `A ⚠️ <short reason in Hebrew>` (e.g. `B ⚠️ 3 רגליים`, `C ⚠️ טקסט בתמונה`).
If all 4 fail → still send, with the header "⚠️ כל 4 המודעות בעייתיות: לייצר מחדש?".
