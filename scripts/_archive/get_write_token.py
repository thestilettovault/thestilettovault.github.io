# -*- coding: utf-8 -*-
"""
Pinterest OAuth — auto-capture write token via local callback server.
Run this once. It will:
  1. Open Pinterest OAuth in your browser
  2. Listen on localhost:8080 for the callback
  3. Exchange code for a write token automatically
  4. Save to .env as PINTEREST_WRITE_TOKEN
  5. Delete all non-affiliate pins from the Zamnai board

Usage:  python get_write_token.py
"""

import sys, os, re, json, time, threading, webbrowser, requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
sys.stdout.reconfigure(encoding='utf-8')

APP_ID     = os.getenv("PINTEREST_APP_ID")
APP_SECRET = os.getenv("PINTEREST_APP_SECRET")  # from scripts/.env
REDIRECT   = "http://localhost:8080/"
SCOPES     = "boards:read,boards:write,pins:read,pins:write,user_accounts:read"
PROD_API   = "https://api.pinterest.com/v5"
ENV_FILE   = os.path.join(os.path.dirname(__file__), ".env")

# Pin IDs to delete (NO affiliate — from audit run)
PINS_TO_DELETE = [
    "522347256805160269", "522347256805160265", "522347256805160263",
    "522347256805160262", "522347256805160255", "522347256805160252",
    "522347256805156719", "522347256805146453", "522347256805146445",
    "522347256805146443", "522347256805146438", "522347256805146436",
    "522347256805134087", "522347256805134081", "522347256805134080",
    "522347256805134079", "522347256805134071", "522347256805134050",
    "522347256805133267", "522347256805133266", "522347256805133265",
    "522347256805133264", "522347256805133263", "522347256805133262",
    "522347256805133261", "522347256805133259", "522347256805133254",
    "522347256805129061", "522347256805129059", "522347256805129058",
    "522347256805129057", "522347256805129048", "522347256805128491",
    "522347256805128483", "522347256805128482", "522347256805128474",
    "522347256805128464", "522347256805128457", "522347256805128451",
    "522347256805128449", "522347256805128448", "522347256805128447",
    "522347256805128439", "522347256805128411", "522347256805128400",
]

captured_code = {"value": None}


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        if code:
            captured_code["value"] = code
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
            <html><body style="font-family:monospace;background:#111;color:#c8a84b;padding:40px">
            <h2>TheGothicVault - Authorization OK</h2>
            <p>Token captured. You can close this tab.</p>
            <script>window.close();</script>
            </body></html>""")
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"No code found.")

    def log_message(self, format, *args):
        pass  # suppress server logs


def exchange_code(code):
    r = requests.post(
        f"{PROD_API}/oauth/token",
        data={
            "grant_type":   "authorization_code",
            "code":         code,
            "redirect_uri": REDIRECT,
        },
        auth=(APP_ID, APP_SECRET),
        timeout=15
    )
    if not r.ok:
        print(f"  Token exchange error {r.status_code}: {r.text}")
        return None
    return r.json().get("access_token")


def save_token(token):
    lines = []
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r") as f:
            lines = f.readlines()
    lines = [l for l in lines if not l.startswith("PINTEREST_WRITE_TOKEN=")]
    lines.append(f"PINTEREST_WRITE_TOKEN={token}\n")
    with open(ENV_FILE, "w") as f:
        f.writelines(lines)


def delete_pins(token):
    headers = {"Authorization": f"Bearer {token}"}
    deleted = 0
    failed  = 0
    print(f"\nDeleting {len(PINS_TO_DELETE)} non-affiliate pins...")
    for pin_id in PINS_TO_DELETE:
        r = requests.delete(f"{PROD_API}/pins/{pin_id}", headers=headers, timeout=10)
        if r.status_code in (200, 204):
            print(f"  DELETED  {pin_id}")
            deleted += 1
        elif r.status_code == 404:
            print(f"  SKIP     {pin_id}  (already deleted)")
        else:
            print(f"  FAILED   {pin_id}  HTTP {r.status_code}: {r.text[:80]}")
            failed += 1
        time.sleep(0.3)  # rate limit safety
    print(f"\nDone: {deleted} deleted, {failed} failed")


def main():
    auth_url = (
        f"https://www.pinterest.com/oauth/"
        f"?client_id={APP_ID}"
        f"&redirect_uri={REDIRECT}"
        f"&response_type=code"
        f"&scope={SCOPES}"
    )

    print("\n" + "="*60)
    print("Pinterest Write Token Setup")
    print("="*60)
    print("\nStarting local callback server on port 8080...")

    # Start server in background thread
    server = HTTPServer(("localhost", 8080), CallbackHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()

    print("Opening Pinterest authorization in browser...")
    webbrowser.open(auth_url)
    print("\nWaiting for you to authorize in the browser...")
    print("(The page will redirect back automatically)\n")

    # Wait up to 120 seconds for authorization
    for i in range(120):
        if captured_code["value"]:
            break
        time.sleep(1)
        if i % 10 == 9:
            print(f"  Still waiting... ({i+1}s)")

    server.shutdown()

    if not captured_code["value"]:
        print("\nTimeout — no authorization received.")
        print(f"Try opening this URL manually:\n  {auth_url}")
        return

    code = captured_code["value"]
    print(f"Authorization code received.")
    print("Exchanging for write token...")

    token = exchange_code(code)
    if not token:
        print("Failed to exchange code for token.")
        return

    print(f"Write token obtained: {token[:25]}...")
    save_token(token)
    print("Saved to .env")

    # Verify
    r = requests.get(f"{PROD_API}/user_account", headers={"Authorization": f"Bearer {token}"})
    if r.ok:
        print(f"Verified: connected as @{r.json().get('username', '?')}")

    # Now delete all non-affiliate pins
    delete_pins(token)
    print("\nZamnai board cleaned. Ready to fill with affiliate products.")


if __name__ == "__main__":
    main()
