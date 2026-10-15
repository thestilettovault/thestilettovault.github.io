import sys
sys.stdout.reconfigure(encoding='utf-8')
from telegram_sender import send_product

products = [
    {
        "url": "https://eu.killstar.com/products/adder-bag",
        "title": "Adder Bag",
        "commission": "10%",
        "domain": "killstar.com"
    },
    {
        "url": "https://www.amazon.com/Dravira-Gothic-Coffin-Wall-Clock/dp/B09G6PHL5C",
        "title": "Dravira Coffin Wall Clock - Gothic Home Decor",
        "commission": "4%",
        "domain": "amazon.com"
    },
    {
        "url": "https://gthic.com/products/gothic-bone-stainless-steel-skull-ring",
        "title": "Gothic Bone Stainless Steel Skull Ring",
        "commission": "15%",
        "domain": "gthic.com"
    }
]

for p in products:
    ok = send_product(**p)
    print(f"  {p['domain']}: {'ok' if ok else 'failed'}")
