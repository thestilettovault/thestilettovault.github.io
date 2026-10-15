import sys, re, requests
sys.stdout.reconfigure(encoding='utf-8')

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36"
}

def check(url, label):
    print(f"\n=== {label} ===")
    r = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
    html = r.text

    # What does _fetch_og_image actually find?
    # Strategy 1: Shopify CDN
    m = re.search(r'(https://cdn\.shopify\.com/s/files/[^\s"\'<>]+\.(?:jpg|jpeg|webp|png))', html)
    if m: print(f"  S1 cdn.shopify: {m.group(1)[:80]}")

    m = re.search(r'"featured_image"\s*:\s*"(https?://[^"]+)"', html)
    if m: print(f"  S1 featured_image: {m.group(1)[:80]}")

    # Strategy 3: JSON-LD
    m = re.search(r'"image"\s*:\s*"(https?://[^"]+)"', html)
    if m: print(f"  S3 JSON-LD: {m.group(1)[:80]}")

    # Strategy 4: OG image + size
    for pat in [
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](https?://[^"\'>\s]+)["\']',
        r'<meta[^>]+content=["\'](https?://[^"\'>\s]+)["\'][^>]+property=["\']og:image["\']',
    ]:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            img_url = m.group(1)
            ir = requests.get(img_url, headers=HEADERS, timeout=8)
            ct = ir.headers.get('content-type','')
            size = len(ir.content)
            passes = size > 50000
            print(f"  S4 og:image: {img_url[:70]}")
            print(f"     size={size} type={ct} passes_50k={passes}")
            break
    else:
        print("  S4: no og:image found")

check("https://eu.killstar.com/products/shadow-play-mini-backpack", "Killstar")
check("https://gthic.com/products/gothic-bone-stainless-steel-skull-ring", "Gthic")
