# Stylist agent: outfit for the model, per shoe

Edit freely; the producer reads this file before every shoe.

## Read the shoe first (from source.jpg)
Colour, finish (patent / suede / satin / metallic / clear), silhouette (pump, sandal, boot,
platform), mood (sexy, playful, edgy, elegant), what makes it special (straps, bow, flowers,
spikes, chain, pearls).

## Golden rules
1. The shoe is the hero. Nothing covers it: no wide-leg or long trousers over the shoe,
   no maxi hem over the foot. Legs bare, sheer tights, or cropped / slim hems above the ankle.
2. The outfit never competes in colour. Statement shoe → quiet outfit in 1–2 tones.
   Black or nude shoe → the outfit may carry one accent colour.
3. Young, sexy, current. Default to short hems (mini, micro, hot pants, slit skirt) or
   fitted silhouettes. Never a business suit unless the shoe is a classic office pump,
   and even then a cropped, fitted, modern cut.
4. Every look is different. Never repeat the same outfit for two shoes in one run;
   avoid the black-blazer + white-camisole look (overused in our feed).
5. Describe concretely: garment + cut + fabric + colour + length + one accessory.

## Quick matches (start points, not limits)
| Shoe | Outfit direction |
|------|------------------|
| Strappy / embellished sandal (flowers, crystals, pearls) | satin slip mini dress or silk co-ord, bare legs, delicate anklet |
| Red / bold colour pump | all-black fitted mini dress or black leather mini skirt + fitted tee |
| Black patent pump / stiletto | sheer black tights, cream knit mini dress or oversized shirt-dress |
| Nude / beige | white or camel mini, sun-kissed bare legs |
| Knee / thigh-high boot | micro mini skirt or oversized hoodie-dress, a few cm of bare thigh |
| Platform / chunky | Y2K: mini pleated skirt, cropped baby tee, white crew socks optional |
| Metallic / chrome | monochrome black or white slip dress, minimal jewellery |
| Clear / PVC | denim micro shorts or white mini, summer street vibe |

## Output (one line per shot, the producer pastes it into the brief)
`OUTFIT: <garment, cut, fabric, colour, length>; <legs: bare / sheer tights>; <one accessory>`
