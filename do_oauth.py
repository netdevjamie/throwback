"""
One-time OAuth flow. Spins up a local web server on http://localhost:8000,
opens browser to Strava's authorize URL, captures the ?code= callback,
exchanges it for tokens, and writes them back to .env.

Run once after creating the Strava app:
    .venv/bin/python do_oauth.py
"""

import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from dotenv import load_dotenv, set_key
from stravalib import Client

ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(ENV_PATH)

CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")

if not CLIENT_ID or not CLIENT_SECRET:
    sys.exit("Missing STRAVA_CLIENT_ID or STRAVA_CLIENT_SECRET in .env")

REDIRECT_URI = "http://localhost:8000/callback"
SCOPES = ["activity:write", "activity:read_all"]

captured_code = {"value": None}
captured_event = threading.Event()


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        code = qs.get("code", [None])[0]
        error = qs.get("error", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        if error:
            self.wfile.write(f"<h1>Authorization failed: {error}</h1>".encode())
        elif code:
            captured_code["value"] = code
            captured_event.set()
            self.wfile.write(b"<h1>Authorized. You can close this tab.</h1>")
        else:
            self.wfile.write(b"<h1>No code received.</h1>")

    def log_message(self, *args):
        pass


def main():
    client = Client()
    auth_url = client.authorization_url(
        client_id=int(CLIENT_ID),
        redirect_uri=REDIRECT_URI,
        scope=SCOPES,
    )

    server = HTTPServer(("localhost", 8000), CallbackHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    print(f"Opening browser. If it doesn't open, paste this URL:\n  {auth_url}\n")
    webbrowser.open(auth_url)

    print("Waiting for authorization callback on http://localhost:8000/callback ...")
    captured_event.wait()
    server.shutdown()

    print("Got authorization code. Exchanging for tokens...")
    token_response = client.exchange_code_for_token(
        client_id=int(CLIENT_ID),
        client_secret=CLIENT_SECRET,
        code=captured_code["value"],
    )

    set_key(str(ENV_PATH), "STRAVA_ACCESS_TOKEN", token_response["access_token"])
    set_key(str(ENV_PATH), "STRAVA_REFRESH_TOKEN", token_response["refresh_token"])

    print("Tokens saved to .env. OAuth complete.")


if __name__ == "__main__":
    main()
