import sys, re, requests
sys.stdout.reconfigure(encoding='utf-8')

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36"
}

def debug_og(url):
    print(f"\n--- {url[:60]} ---")
    try:
        r = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
        print(f"  page status: {r.status_code}")
        html = r.text

        patterns = [
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](https?://[^"\'>\s]+)["\']',
            r'<meta[^>]+content=["\'](https?://[^"\'>\s]+)["\'][^>]+property=["\']og:image["\']',
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\'](https?://[^"\'>\s]+)["\']',
        ]
        for pat in patterns:
            m = re.search(pat, html, re.IGNORECASE)
            if m:
                img_url = m.group(1)
                print(f"  OG image found: {img_url[:80]}")
                img_r = requests.get(img_url, headers=HEADERS, timeout=10)
                print(f"  image fetch: {img_r.status_code} | content-type: {img_r.headers.get('content-type','?')} | size: {len(img_r.content)} bytes")
                return
        print("  NO og:image found in page")
    except Exception as e:
        print(f"  ERROR: {e}")

debug_og("https://eu.killstar.com/products/shadow-play-mini-backpack")
debug_og("https://www.amazon.com/Dravira-Gothic-Coffin-Wall-Clock/dp/B09G6PHL5C")
debug_og("https://gthic.com/products/gothic-bone-stainless-steel-skull-ring")
