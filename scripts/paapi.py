# -*- coding: utf-8 -*-
"""
paapi.py — Amazon Product Advertising API 5.0 client (reliable product data/images).

Replaces fragile HTML scraping. Fetches product title, price, and MULTIPLE image
URLs (primary + variants = the angles the Space needs) by ASIN — no throttling.

SETUP (Ofer, one-time):
  Amazon gates PA-API behind >=3 qualifying sales in 180 days. Once eligible:
  Associates dashboard → Tools → Product Advertising API → create credentials.
  Put in scripts/.env:
    AMAZON_PAAPI_ACCESS_KEY=...
    AMAZON_PAAPI_SECRET_KEY=...
    AMAZON_PARTNER_TAG=thegothicvaul-20     # already our tag

Usage:
    py -3 paapi.py test B0DPLLM13G          # fetch one ASIN, print title + image URLs
    from paapi import get_item ; get_item("B0DPLLM13G")
"""
import os, sys, json, hashlib, hmac, datetime, urllib.request

sys.stdout.reconfigure(encoding="utf-8") if sys.stdout else None
sys.path.insert(0, os.path.dirname(__file__))
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

ACCESS_KEY  = os.getenv("AMAZON_PAAPI_ACCESS_KEY", "")
SECRET_KEY  = os.getenv("AMAZON_PAAPI_SECRET_KEY", "")
PARTNER_TAG = os.getenv("AMAZON_PARTNER_TAG", "thegothicvaul-20")

HOST   = "webservices.amazon.com"
REGION = "us-east-1"
SERVICE = "ProductAdvertisingAPI"
URI    = "/paapi5/getitems"
TARGET = "com.amazon.paapi5.v1.ProductAdvertisingAPIv1.GetItems"
MARKETPLACE = "www.amazon.com"

RESOURCES = [
    "Images.Primary.Large",
    "Images.Variants.Large",          # the extra angles
    "ItemInfo.Title",
    "Offers.Listings.Price",
]


def _sign(key, msg):
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _signature_key(secret, date_stamp, region, service):
    k_date = _sign(("AWS4" + secret).encode("utf-8"), date_stamp)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, service)
    return _sign(k_service, "aws4_request")


def get_item(asin):
    """Return {title, price, images:[url,...]} for an ASIN, or {'error':...}."""
    if not (ACCESS_KEY and SECRET_KEY):
        return {"error": "PA-API keys not set in .env (AMAZON_PAAPI_ACCESS_KEY / SECRET_KEY)"}

    payload = json.dumps({
        "ItemIds": [asin],
        "Resources": RESOURCES,
        "PartnerTag": PARTNER_TAG,
        "PartnerType": "Associates",
        "Marketplace": MARKETPLACE,
    })

    now = datetime.datetime.utcnow()
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    # ── SigV4 canonical request ──
    canonical_headers = (
        f"content-encoding:amz-1.0\n"
        f"content-type:application/json; charset=utf-8\n"
        f"host:{HOST}\n"
        f"x-amz-date:{amz_date}\n"
        f"x-amz-target:{TARGET}\n"
    )
    signed_headers = "content-encoding;content-type;host;x-amz-date;x-amz-target"
    payload_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    canonical_request = f"POST\n{URI}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"

    algorithm = "AWS4-HMAC-SHA256"
    scope = f"{date_stamp}/{REGION}/{SERVICE}/aws4_request"
    string_to_sign = (
        f"{algorithm}\n{amz_date}\n{scope}\n"
        f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
    )
    signing_key = _signature_key(SECRET_KEY, date_stamp, REGION, SERVICE)
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    authorization = (
        f"{algorithm} Credential={ACCESS_KEY}/{scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    headers = {
        "Content-Encoding": "amz-1.0",
        "Content-Type": "application/json; charset=utf-8",
        "X-Amz-Date": amz_date,
        "X-Amz-Target": TARGET,
        "Authorization": authorization,
        "Host": HOST,
    }

    req = urllib.request.Request(f"https://{HOST}{URI}", data=payload.encode("utf-8"),
                                 headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode('utf-8','replace')[:400]}"}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}

    items = data.get("ItemsResult", {}).get("Items", [])
    if not items:
        errs = data.get("Errors", [])
        return {"error": "no item returned", "details": errs}
    it = items[0]

    images = []
    primary = it.get("Images", {}).get("Primary", {}).get("Large", {}).get("URL")
    if primary:
        images.append(primary)
    for v in it.get("Images", {}).get("Variants", []):
        u = v.get("Large", {}).get("URL")
        if u:
            images.append(u)

    title = it.get("ItemInfo", {}).get("Title", {}).get("DisplayValue", "")
    price = ""
    listings = it.get("Offers", {}).get("Listings", [])
    if listings:
        price = listings[0].get("Price", {}).get("DisplayAmount", "")

    return {"asin": asin, "title": title, "price": price, "images": images}


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "test":
        res = get_item(sys.argv[2])
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print("usage: py -3 paapi.py test <ASIN>")
