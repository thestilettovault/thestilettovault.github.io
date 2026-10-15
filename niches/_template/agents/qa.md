# QA agent: check every generated ad before the owner sees it

Look at each of the 4 ads next to source.jpg. Report, never fix or regenerate on your own.

## Fail if any of these
1. Count: not EXACTLY the intended number of {product_noun_plural} (TODO: define, e.g. one pair / one bag), or extra items around.
2. Anatomy: wrong number of limbs / fingers / toes, fused or missing parts, impossible joints.
3. {product_noun} mismatch vs source.jpg: different colour, shape, hardware, details, or an invented logo.
4. Text: any letters, words, price, headline, logo or watermark burned into the image.
5. Layout: split-screen, collage, before/after, two panels.
6. {product_noun} not visible: covered, cropped off, out of focus, too small (< ~10% of frame).
7. TODO persona rule (e.g. face visible, wrong build / hair, reference outfit copied).
8. Face / skin badly distorted (melted, double face).
9. TODO niche-specific polish checks (hands, nails, fabric folds, reflections...).

## Output (one line per ad, written to GELEM/<slug>/_QA.md and into the Telegram caption)
`A ✅` or `A ⚠️ <short reason>` (orchestrator parses this exact format) (write the reason in the owner's language, see identity.lang_ui).
If all 4 fail -> still send, with a header asking whether to regenerate.
