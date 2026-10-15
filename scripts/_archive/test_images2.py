import sys, re, requests
sys.stdout.reconfigure(encoding='utf-8')

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36"
}

def test(url, domain_hint=""):
    print(f"\n=== {domain_hint or url[:50]} ===")
    r = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
    print(f"status: {r.status_code}")
    html = r.text

    # Shopify CDN
    m = re.search(r'(https://cdn\.shopify\.com/s/files/[^\s"\'<>]+\.(?:jpg|jpeg|webp|png))', html)
    if m:
        print(f"Shopify CDN img: {m.group(1)[:100]}")

    # featured_image
    m = re.search(r'"featured_image"\s*:\s*"(https?://[^"]+)"', html)
    if m:
        print(f"featured_image: {m.group(1)[:100]}")

    # Amazon landingImage
    m = re.search(r'id="landingImage"[^>]+src="([^"]+)"', html)
    if m:
        print(f"Amazon landingImage: {m.group(1)[:100]}")
    m = re.search(r'data-old-hires="(https?://[^"]+)"', html)
    if m:
        print(f"Amazon old-hires: {m.group(1)[:100]}")

    # JSON-LD image
    m = re.search(r'"image"\s*:\s*"(https?://[^"]+)"', html)
    if m:
        print(f"JSON-LD image: {m.group(1)[:100]}")

    # OG image
    m = re.search(r'property=["\']og:image["\'][^>]+content=["\'](https?://[^"\'>\s]+)["\']', html, re.IGNORECASE)
    if not m:
        m = re.search(r'content=["\'](https?://[^"\'>\s]+)["\'][^>]+property=["\']og:image["\']', html, re.IGNORECASE)
    if m:
        img_url = m.group(1)
        ir = requests.get(img_url, headers=HEADERS, timeout=8)
        print(f"OG image: {img_url[:80]} | size: {len(ir.content)} bytes")

test("https://eu.killstar.com/products/shadow-play-mini-backpack", "Killstar")
test("https://www.amazon.com/Dravira-Gothic-Coffin-Wall-Clock/dp/B09G6PHL5C", "Amazon")
