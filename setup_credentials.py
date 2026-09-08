#!/usr/bin/env python3
"""
YouTube Live Automation — Credential Setup Tool
================================================
Run this once locally to collect everything you need to configure a
YouTube Live automation Lambda function. It replaces three separate scripts:

  • OAuth refresh tokens (one per Google account)
  • Persistent stream IDs  (one per YouTube channel)
  • Stream keys / RTMP URLs (for ProPresenter or any encoder)

Usage:
    pip install google-auth-oauthlib google-api-python-client
    python setup_credentials.py

Prerequisites:
    1. Go to Google Cloud Console → APIs & Services → Credentials
    2. Create an OAuth 2.0 Client ID  (Application type: Desktop App)
    3. Download the JSON file and save it as client_secrets.json
       in the same folder as this script.

Output:
    Prints every env var value you need directly to the terminal.
    Saves full details (tokens + stream keys) to credentials.json.
    ⚠️  credentials.json is sensitive — keep it private, never commit it.

Notes:
    • If one Google account owns multiple YouTube channels, you only need
      to log in once — the same refresh token works for all of them.
    • Run in Incognito when switching between Google accounts to avoid
      the browser reusing the wrong session.
    • Tokens require both scopes so Lambda can create events AND pull
      viewer analytics. The consent screen must show:
        ✓ Manage your YouTube account
        ✓ View YouTube Analytics reports
"""

import json
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
CLIENT_SECRETS_FILE = "client_secrets.json"
OUTPUT_FILE = "credentials.json"

W = 62  # width for dividers


# ── Helpers ────────────────────────────────────────────────────────────────────

def divider(char="─"):
    print(char * W)


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    answer = input(f"  {prompt}{suffix}: ").strip()
    return answer or default


def authenticate():
    """Open browser OAuth flow. Returns (creds, youtube_client)."""
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
    creds = flow.run_local_server(port=0)
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    return creds, youtube


def discover_channels(youtube) -> list[dict]:
    """Return YouTube channels the API can see on this account."""
    try:
        resp = youtube.channels().list(
            part="snippet", mine=True, maxResults=50
        ).execute()
        return resp.get("items", [])
    except Exception:
        return []


def find_or_create_stream(youtube, channel_id: str, label: str) -> dict | None:
    """
    Find the persistent live stream for a channel, or create one if missing.

    Filters by channelId so accounts with multiple channels get the right stream.
    Returns None if live streaming is not enabled on the channel.
    """
    from googleapiclient.errors import HttpError

    try:
        resp = youtube.liveStreams().list(
            part="snippet,cdn,status", mine=True, maxResults=50
        ).execute()
    except HttpError as e:
        if "liveStreamingNotEnabled" in str(e):
            print(f"    ❌ Live streaming is not enabled on this channel.")
            print(f"       To fix: go to youtube.com/features and enable Live Streaming,")
            print(f"       then re-run this script. (May take up to 24 hours to activate.)")
            return None
        raise

    streams = [
        s for s in resp.get("items", [])
        if s.get("snippet", {}).get("channelId") == channel_id
    ]

    if streams:
        target = streams[0]
        print(f"    ✅ Found existing stream")
    else:
        print(f"    📡 No stream found — creating a persistent stream...")
        try:
            target = youtube.liveStreams().insert(
                part="snippet,cdn",
                body={
                    "snippet": {
                        "title": f"{label} Persistent Stream",
                        "channelId": channel_id,
                    },
                    "cdn": {
                        "frameRate": "variable",
                        "ingestionType": "rtmp",
                        "resolution": "variable",
                    },
                },
            ).execute()
        except HttpError as e:
            if "liveStreamingNotEnabled" in str(e):
                print(f"    ❌ Live streaming is not enabled on this channel.")
                print(f"       To fix: go to youtube.com/features and enable Live Streaming,")
                print(f"       then re-run this script. (May take up to 24 hours to activate.)")
                return None
            raise

    ingestion = target["cdn"]["ingestionInfo"]
    return {
        "stream_id":  target["id"],
        "stream_key": ingestion.get("streamName", "N/A"),
        "stream_url": ingestion.get("ingestionAddress", "N/A"),
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    if not Path(CLIENT_SECRETS_FILE).exists():
        print(f"\n❌  '{CLIENT_SECRETS_FILE}' not found.")
        print("    Download it from Google Cloud Console:")
        print("    APIs & Services → Credentials → Create OAuth Client ID → Desktop App")
        print("    Save the file as client_secrets.json in this folder.\n")
        return

    with open(CLIENT_SECRETS_FILE) as f:
        secrets = json.load(f)
    client_data = secrets.get("installed") or secrets.get("web", {})
    client_id     = client_data.get("client_id", "")
    client_secret = client_data.get("client_secret", "")

    print()
    divider("═")
    print("  YouTube Live Automation — Credential Setup")
    divider("═")
    print()
    print("  This tool collects OAuth tokens and persistent stream IDs")
    print("  for every YouTube channel you want to automate.")
    print()
    print("  You will be prompted to log in once per Google account.")
    print("  If you have multiple accounts, use Incognito between them.")
    print()

    try:
        num_accounts = int(ask("How many Google accounts do you have YouTube channels on?", "1"))
    except ValueError:
        num_accounts = 1

    # env_vars holds the final key=value pairs to print at the end
    env_vars: dict[str, str] = {
        "GOOGLE_CLIENT_ID":     client_id,
        "GOOGLE_CLIENT_SECRET": client_secret,
    }
    # full_data holds everything (including stream keys) for credentials.json
    full_data: dict = {
        "GOOGLE_CLIENT_ID":     client_id,
        "GOOGLE_CLIENT_SECRET": client_secret,
        "accounts": [],
    }

    for acct_num in range(1, num_accounts + 1):
        print()
        divider()
        print(f"  Account {acct_num} of {num_accounts}")
        divider()
        print()
        print("  A browser will open for OAuth. Log in as the correct Google account.")
        input("  Press Enter when ready...")

        creds, youtube = authenticate()

        if not creds.refresh_token:
            print()
            print("  ⚠️  No refresh token returned.")
            print("     This account may have previously authorized this app.")
            print("     To fix: go to myaccount.google.com/permissions,")
            print("     revoke access for this app, then re-run.")
            continue

        print("  ✅ Authentication successful.")
        print()

        # Try to auto-discover channels — may not return all of them
        discovered = discover_channels(youtube)
        channels_to_setup: list[dict] = []  # {"label": ..., "channel_id": ...}

        if discovered:
            print(f"  Channels found on this account ({len(discovered)}):")
            for i, ch in enumerate(discovered, 1):
                name = ch["snippet"]["title"]
                cid  = ch["id"]
                print(f"    {i}. {name}  ({cid})")
            print()
            print("  Give each channel a short uppercase label (e.g. MS, ES).")
            print("  This label determines the env var names: LABEL_REFRESH_TOKEN,")
            print("  LABEL_STREAM_ID.  Press Enter to skip a channel.")
            print()

            for ch in discovered:
                name = ch["snippet"]["title"]
                cid  = ch["id"]
                label = ask(f"Label for '{name}' ({cid}) or Enter to skip").upper()
                if label:
                    channels_to_setup.append({"label": label, "channel_id": cid, "name": name})
        else:
            print("  No channels auto-discovered (this is normal for some account types).")
            print()

        # Always offer to add channels manually
        print()
        print("  Add channels manually (required if a channel wasn't listed above).")
        print("  Find a channel ID in YouTube Studio → Settings → Channel → Advanced.")
        print("  Press Enter to skip.")
        while True:
            cid = ask("  Channel ID to add (UCxxxx...) or Enter to finish").strip()
            if not cid:
                break
            if not cid.startswith("UC"):
                print("    ⚠️  Channel IDs start with 'UC' — check and try again.")
                continue
            already = next((c for c in channels_to_setup if c["channel_id"] == cid), None)
            if already:
                print(f"    Already added as '{already['label']}'.")
                continue
            label = ask(f"  Label for {cid}").upper()
            if label:
                channels_to_setup.append({"label": label, "channel_id": cid, "name": cid})

        if not channels_to_setup:
            print("  No channels selected for this account — skipping.")
            continue

        # Determine the token env var name (first channel's label drives it)
        primary_token_key = f"{channels_to_setup[0]['label']}_REFRESH_TOKEN"
        env_vars[primary_token_key] = creds.refresh_token

        account_record = {
            "token_env":     primary_token_key,
            "refresh_token": creds.refresh_token,
            "channels":      [],
        }

        print()
        for ch in channels_to_setup:
            label      = ch["label"]
            channel_id = ch["channel_id"]
            name       = ch["name"]
            token_key  = f"{label}_REFRESH_TOKEN"
            stream_key = f"{label}_STREAM_ID"

            print(f"  Setting up {label} ({name})...")

            # If this channel is on the same account as a prior channel, note the shared token
            if token_key != primary_token_key:
                env_vars[token_key] = f"<same as {primary_token_key}>"
                print(f"    🔑 {token_key} → same token as {primary_token_key}")

            stream_data = find_or_create_stream(youtube, channel_id, label)

            if stream_data is None:
                env_vars[stream_key] = "NOT YET AVAILABLE — enable live streaming and re-run"
                account_record["channels"].append({
                    "label":      label,
                    "name":       name,
                    "channel_id": channel_id,
                    "token_env":  token_key,
                    "stream_env": stream_key,
                    "error":      "live streaming not enabled",
                })
            else:
                print(f"    Stream ID:  {stream_data['stream_id']}")
                print(f"    Stream URL: {stream_data['stream_url']}")
                print(f"    Stream Key: {stream_data['stream_key']}")
                env_vars[stream_key] = stream_data["stream_id"]
                account_record["channels"].append({
                    "label":      label,
                    "name":       name,
                    "channel_id": channel_id,
                    "token_env":  token_key,
                    "stream_env": stream_key,
                    **stream_data,
                })
            print()

        full_data["accounts"].append(account_record)

    # ── Final summary ──────────────────────────────────────────────────────────
    print()
    divider("═")
    print("  RESULTS — paste these into Lambda → Configuration → Environment Variables")
    divider("═")
    print()

    for key, value in env_vars.items():
        if key in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"):
            print(f"  {key}")
            print(f"    {value}")
        elif value.startswith("<same"):
            print(f"  {key}")
            print(f"    {value}")
        else:
            print(f"  {key}")
            print(f"    {value}")
        print()

    # Save full output including stream keys
    with open(OUTPUT_FILE, "w") as f:
        json.dump(full_data, f, indent=2)

    print(f"  💾 Full details (including stream keys) saved to {OUTPUT_FILE}")
    print(f"  ⚠️  Keep {OUTPUT_FILE} private — it contains tokens and RTMP keys.")
    print(f"     Never commit it to git.\n")


if __name__ == "__main__":
    main()
