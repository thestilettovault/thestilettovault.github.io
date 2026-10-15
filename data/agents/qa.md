# QA agent: check every generated ad before Ofer sees it

Look at each of the 4 ads next to source.jpg. Report, never fix or regenerate on your own.

## Fail (⚠️) if any of these
1. Anatomy: wrong number of legs / feet / hands / arms, fused or missing toes, a foot
   without a leg, impossible joints, a third shoe.
2. Shoe mismatch vs source.jpg: different colour, heel height, toe shape, straps,
   ornaments, or an invented red sole / logo.
3. Text: any letters, words, price, logo or watermark in the image.
4. Layout: split-screen, collage, before/after, two panels.
5. Shoe not visible: covered by clothes, cropped off, out of focus, too small (< ~10% of frame).
6. Face / skin badly distorted (melted, double face).
8. Toes visible but no pedicure, or polish that clashes with the shoe.
7. INA's face is visible (she is never shown above the lips), or the model is clearly
   not Ina (skinny build, different hair) or wears the reference outfit (black blazer).

## Output (one line per ad, written to GELEM/<slug>/_QA.md and into the Telegram caption)
`A ✅` or `A ⚠️ <short reason in Hebrew>` (e.g. `B ⚠️ 3 רגליים`, `C ⚠️ טקסט בתמונה`).
If all 4 fail → still send, with the header "⚠️ כל 4 המודעות בעייתיות: לייצר מחדש?".
