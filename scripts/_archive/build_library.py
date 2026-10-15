"""
build_library.py — Download approved product images into LIBRARY/ folder structure.
Also writes LIBRARY/marketing-links.md with all affiliate links.
"""
import sys, os, re, time, json, requests
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

LIBRARY       = Path(__file__).parent.parent / "LIBRARY"
DATA_DIR      = Path(__file__).parent.parent / "data"
CATALOG_FILE  = DATA_DIR / "approved_catalog.json"

# ── Full approved catalog (all time, deduplicated) ────────────────────

PRODUCTS = {
    "shoes": {
        "amazon": [
            {
                "slug": "ojiaoer-stiletto-pumps",
                "title": "Ojiaoer Gothic Studded Spiked Stiletto Pumps",
                "url": "https://www.amazon.com/dp/B0G3PGSC6P?tag=thegothicvaul-20",
                "aff_link": "https://www.amazon.com/dp/B0G3PGSC6P?tag=thegothicvaul-20",
                "commission": "4%",
            },
            {
                "slug": "demonia-swing-220-platform-boot",
                "title": "Demonia Swing-220 5-Buckle Platform Boot",
                "url": "https://www.amazon.com/dp/B002A9H4BW?tag=thegothicvaul-20",
                "aff_link": "https://www.amazon.com/dp/B002A9H4BW?tag=thegothicvaul-20",
                "commission": "4%",
            },
            {
                "slug": "soireelady-platform-stiletto-sandals",
                "title": "Soireelady Gothic Platform Stiletto Sandals",
                "url": "https://www.amazon.com/dp/B0DSJ68LMN?tag=thegothicvaul-20",
                "aff_link": "https://www.amazon.com/dp/B0DSJ68LMN?tag=thegothicvaul-20",
                "commission": "4%",
            },
            {
                "slug": "foklysp-stiletto-heels",
                "title": "Foklysp Gothic Studded Pointed Toe Stiletto Heels",
                "url": "https://www.amazon.com/dp/B0FT2YGHWR?tag=thegothicvaul-20",
                "aff_link": "https://www.amazon.com/dp/B0FT2YGHWR?tag=thegothicvaul-20",
                "commission": "4%",
            },
        ],
        "killstar": [
            {
                "slug": "crux-obscura-boots",
                "title": "Crux Obscura Boots",
                "url": "https://www.killstar.com/products/crux-obscura-boots",
                "aff_link": "https://www.killstar.com/products/crux-obscura-boots",
                "commission": "10%",
                "image_url": "https://cdn.shopify.com/s/files/1/0228/2373/files/Crux-Obscura-Boots-A.jpg?v=1777364220",
            },
            {
                "slug": "broom-rider-boots",
                "title": "Broom Rider Boots",
                "url": "https://www.killstar.com/products/broom-rider-boots-b",
                "aff_link": "https://www.killstar.com/products/broom-rider-boots-b",
                "commission": "10%",
                "image_url": "https://cdn.shopify.com/s/files/1/0228/2373/files/BROOM-RIDER-BOOTS-C.jpg?v=1777305033",
            },
            {
                "slug": "raven-pointed-toe-bootie",
                "title": "Raven Pointed-Toe Bootie",
                "url": "https://www.killstar.com/products/raven-bootie",
                "aff_link": "https://www.killstar.com/products/raven-bootie",
                "commission": "10%",
                "image_url": "https://cdn.shopify.com/s/files/1/0228/2373/files/RAVEN-BOOTS.B.jpg?v=1777372182",
            },
            {
                "slug": "gloomed-and-doomed-boots",
                "title": "Gloomed and Doomed Boots",
                "url": "https://www.killstar.com/products/gloomed-and-doomed-boots",
                "aff_link": "https://www.killstar.com/products/gloomed-and-doomed-boots",
                "commission": "10%",
            },
        ],
        "tuk": [
            {
                "slug": "1970-creeper-black-leather",
                "title": "1970 Original Creeper Black Leather",
                "url": "https://tukshoes.co.uk/products/black-leather-original-creeper",
                "aff_link": "https://tukshoes.co.uk/products/black-leather-original-creeper",
                "commission": "TBD (TradeTracker — register)",
            },
            {
                "slug": "1970-creeper-black-white",
                "title": "1970 Original Creeper Black Leather & White Stitch",
                "url": "https://tukshoes.co.uk/products/1970-creeper-black-leather",
                "aff_link": "https://tukshoes.co.uk/products/1970-creeper-black-leather",
                "commission": "TBD",
            },
            {
                "slug": "creeper-sneaker-stacked-suede",
                "title": "Creeper Sneaker Stacked Black Suede",
                "url": "https://tukshoes.co.uk/products/creeper-sneaker-stacked-black-suede",
                "aff_link": "https://tukshoes.co.uk/products/creeper-sneaker-stacked-black-suede",
                "commission": "TBD",
            },
            {
                "slug": "viva-high-sandal-gothic-lace",
                "title": "Viva High Sandal Black Gothic Lace",
                "url": "https://tukshoes.co.uk/products/viva-high-creeper-sandal-black-gothic-lace",
                "aff_link": "https://tukshoes.co.uk/products/viva-high-creeper-sandal-black-gothic-lace",
                "commission": "TBD",
            },
            {
                "slug": "viva-high-stud-sandal",
                "title": "Viva High Stud Sandal Black",
                "url": "https://tukshoes.co.uk/products/viva-high-stud-sandal-black",
                "aff_link": "https://tukshoes.co.uk/products/viva-high-stud-sandal-black",
                "commission": "TBD",
            },
        ],
    },
    "clothing": {
        "killstar": [
            {
                "slug": "midnight-vale-corset-top",
                "title": "Midnight Vale Corset Top",
                "url": "https://www.killstar.com/products/midnight-vale-corset-top",
                "aff_link": "https://www.killstar.com/products/midnight-vale-corset-top",
                "commission": "10%",
                "image_url": "https://cdn.shopify.com/s/files/1/0228/2373/files/MIDNIGHT-VALE-CORSET-TOP-B.jpg?v=1778491740",
            },
            {
                "slug": "kihilist-nova-maxi-dress",
                "title": "Kihilist Nova Maxi Dress",
                "url": "https://www.killstar.com/products/kihilist-nova-maxi-dress",
                "aff_link": "https://www.killstar.com/products/kihilist-nova-maxi-dress",
                "commission": "10%",
                "image_url": "https://cdn.shopify.com/s/files/1/0228/2373/files/KIHILIST-NOVA-MAXI-DRESS-B.jpg?v=1778061310",
            },
        ],
        "darkinlove": [
            {
                "slug": "dw488-rebel-doll-dress",
                "title": "Alternative Rebel Doll Black White Dress DW488",
                "url": "https://www.darkinlove.com/products/alternative-rebel-doll-black-white-dress-dw488?sca_ref=ll249558.3UXnWnByxo",
                "aff_link": "https://www.darkinlove.com/products/alternative-rebel-doll-black-white-dress-dw488?sca_ref=ll249558.3UXnWnByxo",
                "commission": "10% — coupon: OFERRABIN",
                "image_url": "https://cdn.shopify.com/s/files/1/0051/7088/8794/products/DW488__105.jpg?v=1620895220",
            },
            {
                "slug": "kw236-plaid-frilly-dress",
                "title": "Angel Coming Plaid Lace Frilly Strap Dress KW236",
                "url": "https://www.darkinlove.com/products/angel-coming-plaid-lace-frilly-strap-dress-kw236?sca_ref=ll249558.3UXnWnByxo",
                "aff_link": "https://www.darkinlove.com/products/angel-coming-plaid-lace-frilly-strap-dress-kw236?sca_ref=ll249558.3UXnWnByxo",
                "commission": "10% — coupon: OFERRABIN",
                "image_url": "https://cdn.shopify.com/s/files/1/0051/7088/8794/products/KW236.jpg?v=1663836233",
            },
        ],
        "other": [
            {
                "slug": "lip-service-mini-dress",
                "title": "4 On The Floor Mini Dress",
                "url": "https://www.lip-service.com/products/4-on-the-floor-mini-dress",
                "aff_link": "https://www.lip-service.com/products/4-on-the-floor-mini-dress",
                "commission": "TBD",
            },
            {
                "slug": "lip-service-pvc-leggings",
                "title": "4-Way Stretch PVC Leggings",
                "url": "https://www.lip-service.com/products/4-way-stretch-pvc-leggings-in-black",
                "aff_link": "https://www.lip-service.com/products/4-way-stretch-pvc-leggings-in-black",
                "commission": "TBD",
            },
            {
                "slug": "lip-service-moto-jacket",
                "title": "As I Am You Will Be Moto Jacket",
                "url": "https://www.lip-service.com/products/vintage-as-i-am-you-will-be-moto-jacket",
                "aff_link": "https://www.lip-service.com/products/vintage-as-i-am-you-will-be-moto-jacket",
                "commission": "TBD",
            },
            {
                "slug": "blackcraft-zip-hoodie",
                "title": "Lovers and Sinners Zip-Up Hoodie",
                "url": "https://www.blackcraftcult.com/products/lovers-and-sinners-zip-up-hoodie",
                "aff_link": "https://www.blackcraftcult.com/products/lovers-and-sinners-zip-up-hoodie",
                "commission": "TBD",
            },
            {
                "slug": "blackcraft-lovecvlt-hoodie",
                "title": "Lovecvlt Pullover Hoodie",
                "url": "https://www.blackcraftcult.com/products/lovecvlt-pullover-hoodie",
                "aff_link": "https://www.blackcraftcult.com/products/lovecvlt-pullover-hoodie",
                "commission": "TBD",
            },
            {
                "slug": "dollskill-spiked-shrug",
                "title": "Darker Wavs Vegan Leather Shrug With Spikes",
                "url": "https://www.dollskill.com/products/downbeat-spiked-shrug",
                "aff_link": "https://www.dollskill.com/products/downbeat-spiked-shrug",
                "commission": "TBD",
            },
        ],
    },
    "accessories": {
        "all": [
            {
                "slug": "lip-service-bondage-cuff",
                "title": "Lip Service PVC Bondage Ring Bracelet Cuff Vegan",
                "url": "https://www.lip-service.com/products/lip-service-bondage-ring-bracelet-cuff",
                "aff_link": "https://www.lip-service.com/products/lip-service-bondage-ring-bracelet-cuff",
                "commission": "TBD",
                "image_url": "https://cdn.shopify.com/s/files/1/1383/0065/files/LS242Cuff_2916webedit.jpg?v=1755983103",
            },
            {
                "slug": "lip-service-dagger-suspenders",
                "title": "Classic Dagger Suspenders",
                "url": "https://www.lip-service.com/products/classic-dagger-suspenders",
                "aff_link": "https://www.lip-service.com/products/classic-dagger-suspenders",
                "commission": "TBD",
                "image_url": "https://cdn.shopify.com/s/files/1/1383/0065/products/LS-113-Suspenders-Lip-Service-men-2.jpg?v=1711594893",
            },
            {
                "slug": "killstar-nova-handbag",
                "title": "Kihilist Nova Handbag",
                "url": "https://www.killstar.com/products/kihilist-nova-handbag",
                "aff_link": "https://www.killstar.com/products/kihilist-nova-handbag",
                "commission": "10%",
                "image_url": "https://cdn.shopify.com/s/files/1/0228/2373/files/KIHILIST-NOVA-HANDBAG-C_228d5a18-db17-44bb-8b6f-ed0d8d823a61.jpg?v=1778839742",
            },
            {
                "slug": "killstar-shadow-play-backpack",
                "title": "Shadow Play Mini Backpack",
                "url": "https://eu.killstar.com/products/shadow-play-mini-backpack",
                "aff_link": "https://eu.killstar.com/products/shadow-play-mini-backpack",
                "commission": "10%",
            },
            {
                "slug": "vex-13-chain",
                "title": "13\" Restraint Chain",
                "url": "https://vexclothing.com/products/13-inch-chain",
                "aff_link": "https://vexclothing.com/products/13-inch-chain",
                "commission": "TBD",
            },
            {
                "slug": "vex-20-chain",
                "title": "20\" Restraint Chain",
                "url": "https://vexclothing.com/products/20-inch-chain",
                "aff_link": "https://vexclothing.com/products/20-inch-chain",
                "commission": "TBD",
            },
            {
                "slug": "skintwo-fishnet-stockings",
                "title": "Vinyl Top Fishnet Stockings Black",
                "url": "https://www.skintwo.com/products/vinyl-top-fishnet-stockings-black-one-size",
                "aff_link": "https://www.skintwo.com/products/vinyl-top-fishnet-stockings-black-one-size",
                "commission": "15% ⚠️ PINTEREST BLOCKED",
            },
            {
                "slug": "skintwo-pvc-waspie-belt",
                "title": "PVC Buckle Waspie Belt in Black",
                "url": "https://www.skintwo.com/products/pvc-buckle-waspie-belt-in-black",
                "aff_link": "https://www.skintwo.com/products/pvc-buckle-waspie-belt-in-black",
                "commission": "15% ⚠️ PINTEREST BLOCKED",
            },
            {
                "slug": "restyle-rubrum-lux-backpack",
                "title": "RUBRUM LUX BACKPACK",
                "url": "https://restyle.pl/product-eng-2758-RUBRUM-LUX-BACKPACK.html",
                "aff_link": "https://restyle.pl/product-eng-2758-RUBRUM-LUX-BACKPACK.html",
                "commission": "15%",
            },
        ]
    }
}


# ── Helpers ───────────────────────────────────────────────────────────

def shopify_thumb(url):
    url = url.split("?")[0]
    return re.sub(r'\.(jpg|jpeg|png|webp)$', r'_800x.\1', url, flags=re.IGNORECASE)


def download_image(img_url, dest_path):
    try:
        # Try thumb first for Shopify
        if "cdn.shopify.com" in img_url:
            thumb = shopify_thumb(img_url)
            r = requests.get(thumb, headers=HEADERS, timeout=10)
            if r.ok and r.headers.get("content-type","").startswith("image"):
                dest_path.write_bytes(r.content)
                return True
        r = requests.get(img_url, headers=HEADERS, timeout=10)
        if r.ok and r.headers.get("content-type","").startswith("image"):
            dest_path.write_bytes(r.content)
            return True
    except Exception as e:
        print(f"    error: {e}")
    return False


def scrape_amazon_image(url):
    """Scrape main product image from Amazon."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=12, allow_redirects=True)
        if not r.ok:
            return None
        html = r.text
        for pat in [
            r'data-old-hires="(https?://[^"]+)"',
            r'"hiRes"\s*:\s*"(https://[^"]+)"',
            r'"large"\s*:\s*"(https://m\.media-amazon\.com/images/[^"]+)"',
        ]:
            m = re.search(pat, html)
            if m:
                img_r = requests.get(m.group(1), headers=HEADERS, timeout=8)
                if img_r.ok:
                    return img_r.content
    except Exception as e:
        print(f"    amazon scrape error: {e}")
    return None


def scrape_shopify_image(url):
    """Scrape product image via Shopify suggest API."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        handle = url.split("/products/")[-1].split("?")[0].rstrip("/")
        base = f"{parsed.scheme}://{parsed.netloc}"
        r = requests.get(
            f"{base}/search/suggest.json",
            params={"q": handle.replace("-", " "), "resources[type]": "product", "resources[limit]": "5"},
            headers=HEADERS, timeout=8
        )
        if r.ok:
            results = r.json().get("resources", {}).get("results", {}).get("products", [])
            for p in results:
                if p.get("handle") == handle:
                    img_url = p.get("image") or p.get("featured_image", {}).get("url", "")
                    if img_url:
                        img_r = requests.get(img_url.split("?")[0], headers=HEADERS, timeout=8)
                        if img_r.ok:
                            return img_r.content
    except Exception as e:
        print(f"    shopify scrape error: {e}")
    return None


# ── Download all images ───────────────────────────────────────────────

def download_all():
    total = ok = 0
    for category, subcats in PRODUCTS.items():
        for subcat, items in subcats.items():
            folder = LIBRARY / category / subcat
            folder.mkdir(parents=True, exist_ok=True)

            for p in items:
                slug = p["slug"]
                dest = folder / f"{slug}.jpg"
                if dest.exists():
                    print(f"  SKIP (exists): {slug}")
                    continue

                total += 1
                print(f"  Downloading: {p['title'][:60]}")

                img_bytes = None

                # 1. Use known image_url if available
                if p.get("image_url"):
                    try:
                        url_to_try = shopify_thumb(p["image_url"]) if "cdn.shopify.com" in p["image_url"] else p["image_url"]
                        r = requests.get(url_to_try, headers=HEADERS, timeout=10)
                        if r.ok and r.headers.get("content-type","").startswith("image"):
                            img_bytes = r.content
                    except Exception:
                        pass

                # 2. Amazon scrape
                if not img_bytes and "amazon.com" in p["url"]:
                    img_bytes = scrape_amazon_image(p["url"])

                # 3. Shopify suggest API for Killstar/TUK/other Shopify
                if not img_bytes and "/products/" in p["url"]:
                    img_bytes = scrape_shopify_image(p["url"])

                if img_bytes:
                    dest.write_bytes(img_bytes)
                    ok += 1
                    print(f"    ✅ saved → {dest.name}")
                else:
                    print(f"    ❌ no image found")

                time.sleep(1)

    print(f"\nסיום הורדות: {ok}/{total} תמונות נשמרו.")
    return ok, total


# ── Build marketing-links.md ──────────────────────────────────────────

def build_marketing_md():
    lines = [
        "# TheGothicVault — Marketing Links Catalog",
        f"_Updated: 2026-06-04_",
        "",
        "> כל הלינקים כוללים affiliate tracking. Skintwo מסומן ⚠️ — לא לפרסם ב-Pinterest.",
        "",
    ]

    LABELS = {
        "shoes/amazon":       "👠 נעליים — Amazon (4% עמלה)",
        "shoes/killstar":     "🥾 נעליים — Killstar (10% עמלה)",
        "shoes/tuk":          "👟 נעליים — TUK Shoes (עמלה ממתינה — הרשם ל-TradeTracker)",
        "clothing/killstar":  "🖤 ביגוד — Killstar (10% עמלה)",
        "clothing/darkinlove":"🌹 ביגוד — Dark In Love (10% + קופון OFERRABIN)",
        "clothing/other":     "👗 ביגוד — Other Brands",
        "accessories/all":    "👜 אביזרים",
    }

    for category, subcats in PRODUCTS.items():
        for subcat, items in subcats.items():
            key = f"{category}/{subcat}"
            label = LABELS.get(key, f"{category} / {subcat}")
            lines += ["", f"## {label}", ""]
            lines.append("| מוצר | עמלה | לינק |")
            lines.append("|------|------|------|")
            for p in items:
                title = p["title"]
                comm  = p.get("commission", "—")
                link  = p["aff_link"]
                lines.append(f"| {title} | {comm} | {link} |")

    out = LIBRARY / "marketing-links.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n✅ marketing-links.md נשמר → {out}")


# ── Build from dynamic approved_catalog.json ─────────────────────────

def load_catalog():
    """Load approved_catalog.json — products approved via Telegram OK button."""
    if not CATALOG_FILE.exists():
        return []
    with open(CATALOG_FILE, encoding="utf-8") as f:
        return json.load(f)


def build_marketing_md_full():
    """
    Build marketing-links.md from BOTH sources:
    - PRODUCTS dict (manually curated, legacy)
    - approved_catalog.json (dynamic, from Telegram OK votes)
    Deduplicates by URL. New approvals always take precedence.
    """
    catalog = load_catalog()

    # Catalog items indexed by URL for dedup
    catalog_urls = {item["url"] for item in catalog}

    lines = [
        "# TheGothicVault — Marketing Links Catalog",
        f"_Updated: {__import__('datetime').date.today()}_",
        "",
        "> כל הלינקים כוללים affiliate tracking. Skintwo מסומן ⚠️ — לא לפרסם ב-Pinterest.",
        "",
    ]

    # ── Section 1: Dynamic catalog (from Telegram approvals) ──────────
    if catalog:
        lines += [
            "## ✅ אושרו בטלגרם (דינמי)",
            "",
            "| מוצר | Brand | עמלה | לינק |",
            "|------|-------|------|------|",
        ]
        for item in sorted(catalog, key=lambda x: x.get("date", ""), reverse=True):
            title = item["title"]
            domain = item.get("domain", "—")
            comm = item.get("commission", "—")
            link = item.get("aff_link") or item.get("url")
            lines.append(f"| {title} | {domain} | {comm} | {link} |")
        lines.append("")

    # ── Section 2: Curated library (manual, from PRODUCTS dict) ───────
    LABELS = {
        "shoes/amazon":       "👠 נעליים — Amazon (4% עמלה)",
        "shoes/killstar":     "🥾 נעליים — Killstar (10% עמלה)",
        "shoes/tuk":          "👟 נעליים — TUK Shoes",
        "clothing/killstar":  "🖤 ביגוד — Killstar (10% עמלה)",
        "clothing/darkinlove":"🌹 ביגוד — Dark In Love (10% + קופון OFERRABIN)",
        "clothing/other":     "👗 ביגוד — Other Brands",
        "accessories/all":    "👜 אביזרים",
    }

    for category, subcats in PRODUCTS.items():
        for subcat, items in subcats.items():
            # Filter out items already in dynamic catalog
            items_to_show = [p for p in items if p["url"] not in catalog_urls]
            if not items_to_show:
                continue
            key = f"{category}/{subcat}"
            label = LABELS.get(key, f"{category} / {subcat}")
            lines += ["", f"## {label}", ""]
            lines.append("| מוצר | עמלה | לינק |")
            lines.append("|------|------|------|")
            for p in items_to_show:
                lines.append(f"| {p['title']} | {p.get('commission','—')} | {p['aff_link']} |")

    out = LIBRARY / "marketing-links.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n✅ marketing-links.md נשמר → {out}")
    print(f"   {len(catalog)} מוצרים מהקטלוג הדינמי")
    return out


# ── Entry ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"

    if cmd == "links":
        # Only regenerate marketing-links.md (fast)
        build_marketing_md_full()
    elif cmd == "images":
        download_all()
    else:
        print("=== TheGothicVault Library Builder ===\n")
        print("--- שלב 1: הורדת תמונות ---")
        download_all()
        print("\n--- שלב 2: בניית marketing-links.md ---")
        build_marketing_md_full()
