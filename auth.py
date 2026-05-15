"""Shared Strava auth helpers.

Loads credentials from .env, refreshes the access token (Strava expires
them every six hours), persists the rotated tokens back to .env, and
returns an authenticated stravalib Client.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv, set_key
from stravalib import Client

ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(ENV_PATH)


def get_client() -> Client:
    client_id = os.getenv("STRAVA_CLIENT_ID")
    client_secret = os.getenv("STRAVA_CLIENT_SECRET")
    refresh_token = os.getenv("STRAVA_REFRESH_TOKEN")
    if not all([client_id, client_secret, refresh_token]):
        sys.exit("Missing credentials in .env. Run do_oauth.py first.")

    client = Client()
    tokens = client.refresh_access_token(
        client_id=int(client_id),
        client_secret=client_secret,
        refresh_token=refresh_token,
    )
    set_key(str(ENV_PATH), "STRAVA_ACCESS_TOKEN", tokens["access_token"])
    set_key(str(ENV_PATH), "STRAVA_REFRESH_TOKEN", tokens["refresh_token"])
    client.access_token = tokens["access_token"]
    return client
