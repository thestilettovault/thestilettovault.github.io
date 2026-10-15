"""
Pinterest OAuth Token Generator — localhost version
Runs a local server to capture the OAuth code automatically.
"""

import os
import webbrowser
import urllib.parse
import requests
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv

load_dotenv(override=True)

APP_ID       = os.getenv("PINTEREST_APP_ID")
APP_SECRET   = os.getenv("PINTEREST_APP_SECRET")
REDIRECT_URI = "http://localhost:8080/callback"
SCOPES       = "boards:read boards:write pins:read pins:write user_accounts:read"

auth_code = None

class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if "code" in params:
            auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h2>Success! You can close this tab.</h2>")
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"<h2>No code found. Try again.</h2>")

    def log_message(self, format, *args):
        pass  # silence server logs

def exchange_code(code):
    r = requests.post(
        "https://api.pinterest.com/v5/oauth/token",
        data={
            "grant_type":  "authorization_code",
            "code":         code,
            "redirect_uri": REDIRECT_URI,
        },
        auth=(APP_ID, APP_SECRET),
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    r.raise_for_status()
    return r.json()

if __name__ == "__main__":
    params = {
        "client_id":     APP_ID,
        "redirect_uri":  REDIRECT_URI,
        "response_type": "code",
        "scope":         SCOPES,
    }
    auth_url = "https://www.pinterest.com/oauth/?" + urllib.parse.urlencode(params)

    print("\n" + "="*55)
    print("Pinterest OAuth — Write Token Generator")
    print("="*55)
    print("\nStarting local server on http://localhost:8080...")

    server = HTTPServer(("localhost", 8080), CallbackHandler)
    thread = threading.Thread(target=server.handle_request)
    thread.start()

    print("Opening browser for authorization...")
    webbrowser.open(auth_url)
    print("Waiting for Pinterest to redirect back...")

    thread.join(timeout=120)

    if auth_code:
        print(f"\nCode received! Exchanging for token...")
        try:
            token_data = exchange_code(auth_code)
            access_token = token_data.get("access_token", "")
            print(f"\n✅ Success!")
            print(f"\nCopy this line into your .env file:")
            print(f"\nPINTEREST_ACCESS_TOKEN={access_token}\n")
        except Exception as e:
            print(f"\nError exchanging code: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response: {e.response.text}")
    else:
        print("\nTimeout — no code received. Try again.")

    server.server_close()
