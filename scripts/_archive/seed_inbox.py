"""
Seed INBOX board with initial gothic products for pipeline testing.
Run once: python seed_inbox.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from gothic_scout import create_pin, get_all_boards

INBOX_ID = "522347325470861758"

PRODUCTS = [
    # ── GTHIC.COM — 15% commission ──────────────────────────────────
    {
        "title": "https://gthic.com/products/gothic-tribute-gem-stainless-steel-skull-ring",
        "image": "https://gthic.com/cdn/shop/products/gothic_tribute_gem_stainless_steel_skull_ring_gthic_5_1024x.jpg?v=1762199841",
        "source": "https://gthic.com/products/gothic-tribute-gem-stainless-steel-skull-ring",
        "desc": "Gothic Tribute Gem Stainless Steel Skull Ring — $33 | gthic.com | 15% affiliate"
    },
    {
        "title": "https://gthic.com/products/odin-skull-feather-gothic-sterling-silver-ring",
        "image": "https://gthic.com/cdn/shop/files/odin_skull_feather_gothic_sterling_silver_ring_gthic_3_1024x.jpg?v=1774602375",
        "source": "https://gthic.com/products/odin-skull-feather-gothic-sterling-silver-ring",
        "desc": "Odin Skull Feather Gothic Sterling Silver Ring — $257 | gthic.com | 15% affiliate"
    },
    {
        "title": "https://gthic.com/products/gothic-claw-skull-sterling-silver-ring",
        "image": "https://gthic.com/cdn/shop/products/gothic_claw_skull_sterling_silver_ring_gthic_2_1024x.jpg?v=1762200123",
        "source": "https://gthic.com/products/gothic-claw-skull-sterling-silver-ring",
        "desc": "Gothic Claw Skull Sterling Silver Ring — $272 | gthic.com | 15% affiliate"
    },
    {
        "title": "https://gthic.com/products/gothic-skull-mask-stainless-steel-ring",
        "image": "https://gthic.com/cdn/shop/files/gothic_skull_mask_stainless_steel_ring_gthic_3_1024x.jpg?v=1776848192",
        "source": "https://gthic.com/products/gothic-skull-mask-stainless-steel-ring",
        "desc": "Gothic Skull Mask Stainless Steel Ring — $29 | gthic.com | 15% affiliate"
    },
    {
        "title": "https://gthic.com/products/gothic-bone-stainless-steel-skull-ring",
        "image": "https://gthic.com/cdn/shop/products/gothic_bone_stainless_steel_skull_ring_gthic_1_1024x.jpg?v=1762200233",
        "source": "https://gthic.com/products/gothic-bone-stainless-steel-skull-ring",
        "desc": "Gothic Bone Stainless Steel Skull Ring — $25.90 | gthic.com | 15% affiliate"
    },
    {
        "title": "https://gthic.com/products/unique-punk-gothic-demon-316l-stainless-steel-biker-skull-ring",
        "image": "https://gthic.com/cdn/shop/products/gthic-ring-10-gothic-demon-biker-skull-ring-13777078943796_1024x.png?v=1762198195",
        "source": "https://gthic.com/products/unique-punk-gothic-demon-316l-stainless-steel-biker-skull-ring",
        "desc": "The Devil Satan Stainless Steel Skull Ring — $31 | gthic.com | 15% affiliate"
    },
    # ── RESTYLE.PL — 15% commission ─────────────────────────────────
    {
        "title": "https://restyle.pl/product-eng-2521-DARK-SOUL-NECKLACE.html",
        "image": "https://static5.restyle.pl/hpeciai/2897f41b49704227acc100231c99adb2/eng_pm_DARK-SOUL-NECKLACE-2521_1.jpg",
        "source": "https://restyle.pl/product-eng-2521-DARK-SOUL-NECKLACE.html",
        "desc": "DARK SOUL NECKLACE — $26 | restyle.pl | 15% affiliate"
    },
    {
        "title": "https://restyle.pl/product-eng-2758-RUBRUM-LUX-BACKPACK.html",
        "image": "https://static2.restyle.pl/hpeciai/010c71194853e7bbd954972ef52b4aa0/eng_pm_RUBRUM-LUX-BACKPACK-2758_1.webp",
        "source": "https://restyle.pl/product-eng-2758-RUBRUM-LUX-BACKPACK.html",
        "desc": "RUBRUM LUX BACKPACK — $114 | restyle.pl | 15% affiliate"
    },
    {
        "title": "https://restyle.pl/product-eng-2756-BLOODSPIRE-BAG.html",
        "image": "https://static2.restyle.pl/hpeciai/72960d55e0c58ca6a3dee4c49baf44f5/eng_pm_BLOODSPIRE-BAG-2756_3.webp",
        "source": "https://restyle.pl/product-eng-2756-BLOODSPIRE-BAG.html",
        "desc": "BLOODSPIRE BAG — $101 | restyle.pl | 15% affiliate"
    },
]

if __name__ == "__main__":
    print(f"Seeding {len(PRODUCTS)} products to INBOX ({INBOX_ID})...\n")
    ok = 0
    for p in PRODUCTS:
        pin_id = create_pin(INBOX_ID, p["image"], p["title"], p["source"], p["desc"])
        if pin_id:
            print(f"  OK  {p['desc'][:70]}")
            ok += 1
        else:
            print(f"  FAIL: {p['title'][:60]}")
    print(f"\nDone: {ok}/{len(PRODUCTS)} pinned.")
