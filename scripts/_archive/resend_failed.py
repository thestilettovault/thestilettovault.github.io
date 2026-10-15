"""
resend_failed.py — Resend only the items that failed in resend_pending.py
"""
import sys, os, time, json
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from telegram_sender import send_product, send_text
import taste_engine

# Items that failed — skip the Coffin Clock (rejected 4 times)
FAILED = [
    {
        "url":        "https://www.darkinlove.com/products/alternative-rebel-doll-black-white-dress-dw488?sca_ref=ll249558.3UXnWnByxo",
        "title":      "Alternative Rebel Doll Black White Dress DW488",
        "image_url":  "https://cdn.shopify.com/s/files/1/0051/7088/8794/products/DW488__105.jpg?v=1620895220",
        "commission": "10%",
    },
    {
        "url":        "https://www.darkinlove.com/products/angel-coming-plaid-lace-frilly-strap-dress-kw236?sca_ref=ll249558.3UXnWnByxo",
        "title":      "Angel Coming Plaid Lace Frilly Strap Dress KW236",
        "image_url":  "https://cdn.shopify.com/s/files/1/0051/7088/8794/products/KW236.jpg?v=1663836233",
        "commission": "10%",
    },
    {
        "url":        "https://www.killstar.com/products/kihilist-nova-maxi-dress",
        "title":      "Kihilist Nova Maxi Dress",
        "image_url":  "https://cdn.shopify.com/s/files/1/0228/2373/files/KIHILIST-NOVA-MAXI-DRESS-B.jpg?v=1778061310",
        "commission": "10%",
    },
    {
        "url":        "https://www.killstar.com/products/midnight-vale-corset-top",
        "title":      "Midnight Vale Corset Top",
        "image_url":  "https://cdn.shopify.com/s/files/1/0228/2373/files/MIDNIGHT-VALE-CORSET-TOP-B.jpg?v=1778491740",
        "commission": "10%",
    },
]

def main():
    send_text(f"🔄 *שולח {len(FAILED)} מוצרים שנכשלו בשליחה הקודמת*")
    sent = 0
    for item in FAILED:
        domain = taste_engine.get_domain(item["url"])
        print(f"Sending: {item['title']}")
        ok = send_product(
            url=item["url"],
            title=item["title"],
            commission=item["commission"],
            image_url=item["image_url"],
            domain=domain,
        )
        print(f"  {'✅' if ok else '❌'}")
        if ok:
            sent += 1
        time.sleep(1.5)
    print(f"\nסיום. {sent}/{len(FAILED)} נשלחו.")

if __name__ == "__main__":
    main()
