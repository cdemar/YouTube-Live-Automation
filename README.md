# YouTube Live Automation

[![Tests](https://github.com/cdemar/YouTube-Live-Automation/actions/workflows/tests.yml/badge.svg)](https://github.com/cdemar/YouTube-Live-Automation/actions/workflows/tests.yml)

An AWS Lambda function that automates weekly YouTube Live operations for a multi-campus,
multi-language church — built for and running in production at San Jose Christian Alliance
Church (SJCAC), open-sourced in case it's useful to anyone running a similar setup.

Every week it automatically:
- **Creates next Sunday's YouTube Live broadcast** on each of 4 channels, with the correct
  title, description, and thumbnail in that channel's own language, bound to a persistent
  stream so the RTMP key in your streaming software (e.g. ProPresenter) never has to change.
- **Reports last Sunday's peak viewer counts** for each channel in an emailed summary.
- Optionally **syncs those viewer counts into a Google Sheet** for attendance tracking
  alongside in-person numbers.

No one has to touch YouTube Studio, week to week, to get a new scheduled broadcast up with
the right branding.

## How it's put together

Two independent pieces, connected by one small integration:

1. **The Lambda function** (`handler.py`) — runs on a weekly EventBridge schedule. Talks to
   the YouTube Data API and YouTube Analytics API (one OAuth2 account per channel), Amazon S3
   (for thumbnails), and Amazon SES (for the report email).
2. **A Google Sheet + Apps Script** (`apps_script/`) — an optional attendance tracker. If you
   wire it up, the Lambda function POSTs viewer counts to a Web App endpoint deployed from the
   Sheet's own Apps Script project, which logs them alongside manually-reported in-person
   attendance.

You can use just the Lambda half (channel automation with no Sheet at all) or both — the
Sheet sync is skipped automatically if you don't configure it.

```
EventBridge (weekly cron)
        │
        ▼
   handler.py  ───────►  YouTube Data API + Analytics API  (create events, read viewer counts)
        │
        ├──────────────► Amazon S3            (thumbnails)
        ├──────────────► Amazon SES            (weekly report email)
        └──────────────► Google Sheet Web App  (optional attendance sync, via apps_script/)
```

## Repository layout

| Path | What it is |
|---|---|
| `handler.py` | The Lambda function itself — this is the whole automation |
| `setup_credentials.py` | Run locally, once per Google account, to generate OAuth refresh tokens and persistent stream IDs |
| `apps_script/` | The Google Apps Script files for the optional attendance-Sheet integration (these live and run inside a Google Sheet, not on AWS — see below) |
| `thumbnails/` | Example thumbnail images |
| `tests/` | Pytest unit tests for `handler.py` — 100% line coverage, nothing hits a real API (see "Automated tests" in `OPERATIONS.md`) |
| `OPERATIONS.md` | The full internal runbook — every environment variable, every manual test payload, deployment steps, troubleshooting. Start here if you're adapting this for your own use |
| `LICENSE` | MIT |

## Running the tests

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

## Requirements to run your own copy

- An AWS account (Lambda, S3, SES — this runs comfortably within the free tier)
- A Google Cloud project with the YouTube Data API v3 and YouTube Analytics API enabled
- One Google account per YouTube channel you want to automate, each with OAuth consent
  granted via `setup_credentials.py`
- (Optional) A Google Sheet with an Apps Script Web App deployment, if you want the
  attendance-tracking half

None of this repo's code contains real credentials — every secret (OAuth tokens, API keys,
stream keys, the Sheet's shared secret) is supplied at runtime through environment variables
you set yourself. See **[OPERATIONS.md](OPERATIONS.md)** for the complete list of environment
variables, the one-time setup walkthrough, how to add a channel, and how to deploy.

## Adapting this for your own organization

This was built specifically for SJCAC's 4 channels, languages, and campuses — the channel
list, titles, descriptions, and congregation names in `handler.py` and `apps_script/` are all
specific to that setup. To reuse it: replace the `CHANNELS` dict in `handler.py` with your own
channels (see "How to add a new automated channel" in `OPERATIONS.md`), and if you want the
Sheet integration, do the same for `CONGREGATIONS` and `CHANNEL_TO_CONGREGATION` in
`apps_script/`.

## License

MIT — see [LICENSE](LICENSE). Use it, fork it, adapt it for your own church or organization.
