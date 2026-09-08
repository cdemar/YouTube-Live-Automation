**Treat this file, `handler.py`, and the Apps Script project attached to the attendance Google Sheet as the source of truth.** If code and this doc ever disagree, the code is right — update this file to match.

There are **two connected systems**:
1. **YouTube automation** (this folder) — an AWS Lambda function that creates next Sunday's livestream events and reports last Sunday's viewer counts, for 4 of the church's channels.
2. **Attendance tracker** (Google Sheets + Apps Script, lives inside the spreadsheet itself, not in this folder) — logs in-person + online attendance for all 11 congregations. The Lambda function above feeds it viewer counts automatically for the 4 channels it covers; everyone else reports through a Google Form.

---
## Quick reference

| Question | Answer |
|---|---|
| What does it do | Every week: emails last Sunday's peak YouTube viewer counts, creates next Sunday's livestream events, and pushes the viewer counts into the attendance Google Sheet |
| Channels automated | Mandarin (`ms_channel`), English San Jose (`es_channel`), English Willow Glen (`es2_channel`), Spanish/Nueva Vida (`ss_channel`) — **all 4 are active**, none are "pending" anymore |
| Channel handled manually | Cantonese — YouTube's API can't bind a broadcast to a secondary channel on a multi-channel account (404 on every attempt), so it's created by hand in YouTube Studio each week |
| When it runs | Every Tuesday at 9:00 AM PST / 10:00 AM PDT — confirmed against the live EventBridge rule, see [Schedule](#schedule) below |
| Where the code lives | `handler.py` in this folder, deployed as the Lambda function's zip |
| Where the Sheet code lives | Apps Script editor attached to the attendance spreadsheet (Extensions → Apps Script) — **not** a file in this folder. Local backup copies of each script now live in `apps_script/`, see [Part B](#part-b--attendance-tracker-google-sheet--apps-script) |
| Manual re-run | Lambda console → Test tab, see [Manual test payloads](#manual-test-payloads) |
| Safe to test anytime | `{"dry_run": true}` — calculates everything, writes nothing, sends nothing |

---
## Part A — YouTube automation (`handler.py`)
### What it does, per run
1. **Viewer report** — looks back at last Sunday's completed broadcasts on all 4 channels, fetches peak concurrent viewers (Videos API first, falls back to YouTube Analytics API for anything more than a few hours old), and emails an HTML summary via Amazon SES.
2. **Event creator** — creates next Sunday's YouTube Live broadcast on each channel: title and description in the channel's own language, correct start time, thumbnail from S3, bound to the channel's **persistent stream** (so the RTMP key in ProPresenter never changes), and added to the channel's playlist.
3. **Sheet sync** — POSTs the successful viewer counts to the attendance Google Sheet's Apps Script Web App, which logs them into the Raw Log tab. Skipped during dry runs, and skipped silently (with a warning in the logs) if `SHEET_WEBAPP_URL` / `SHEET_WEBAPP_SECRET` aren't set.

**Things the API cannot do, so they're set manually in YouTube Studio each week:** live chat cannot be disabled per-broadcast via the API. Turn it off under YouTube Studio → Content → Live → Edit → Customization → Live chat, **every week, for every broadcast** — this does not carry over automatically from week to week. (Comments are separate and are controlled by YouTube Studio → Settings → Community → Defaults, which is a one-time, account-level setting that does persist.) Google has an open issue tracking this API limitation, status **Assigned** as of mid-2026 (not just filed-and-ignored) — worth checking back on periodically in case it ships: [issuetracker.google.com/issues/471770017](https://issuetracker.google.com/issues/471770017) ("FEATURE REQUEST: Disable/Enable Live Broadcast's Chat from API"). Already commented on with this exact use case. Until then, the live chat toggle is a manual weekly step.

### Schedule
**Confirmed against the live EventBridge rule** (checked in the AWS Console):

| Rule name           | `yt-live-wednesday-trigger`                                            |
| ------------------- | ---------------------------------------------------------------------- |
| Rule ARN            | `arn:aws:events:us-east-2:<AWS_ACCOUNT_ID>:rule/yt-live-wednesday-trigger` (account ID redacted for the public repo — check the AWS Console for the real one) |
| Schedule expression | `cron(0 17 ? * TUE *)`                                                 |
| Fires               | Every **Tuesday** at 9:00 AM PST / 10:00 AM PDT (17:00 UTC)            |
| State               | ENABLED                                                                |
So `handler.py`'s Tuesday mentions were correct; every "Wednesday" reference in the file
(header summary, a code comment, the `lambda_handler()` docstring, and — notably — the
footer text of the actual weekly email sent to staff) has been corrected to Tuesday.

One cosmetic loose end, not urgent: **the rule itself is still named
`yt-live-wednesday-trigger`**, a leftover from when it really did run Wednesdays. It works
fine as-is — EventBridge doesn't care what a rule is named — but it'll confuse the next
person who opens the console expecting the name to match the schedule. Renaming an
EventBridge rule means recreating it (AWS doesn't support renaming in place) and re-pointing
it at the Lambda target, so it's a deliberate one-time cleanup task, not something to do
casually.

### Channels

| Key           | Label                 | Campus                   | Language | Start time                     | Playlist configured |
| ------------- | --------------------- | ------------------------ | -------- | ------------------------------ | ------------------- |
| `ms_channel`  | Mandarin              | San Jose                 | Mandarin | 11:15 AM                       | Yes                 |
| `es_channel`  | English               | San Jose                 | English  | 11:15 AM                       | Yes                 |
| `es2_channel` | English (Willow Glen) | Willow Glen              | English  | 9:30 AM                        | Yes                 |
| `ss_channel`  | Spanish               | Willow Glen (Nueva Vida) | Spanish  | 7:00 PM                        | Yes                 |
| —             | Cantonese             | San Jose                 | —        | manual only, not in `CHANNELS` | —                   |
Exact values (channel IDs, stream-ID env var names, thumbnail keys) live in the `CHANNELS` dict near the top of `handler.py` — that's the only place to edit for routine changes, and the only place that won't drift out of sync with this doc.

### Thumbnails
Three files in S3 (`<EVENTS_S3_BUCKET>/thumbnails/`), matching what's in the local
`thumbnails/` folder:

| File | Used by |
|---|---|
| `mandarin.jpeg` | Mandarin |
| `english.jpg` | English (San Jose) and English (Willow Glen) |
| `spanish.jpeg` | Spanish |
Renamed from `sjcac.jpeg`/`wG.jpeg` to `mandarin.jpeg`/`spanish.jpeg` for clarity — the old
names didn't obviously map to a channel. `english.jpg` was left as-is. Both `handler.py`'s
`thumbnail_s3_key` values and the local `thumbnails/` folder have been updated to match.
**S3 itself still needs the corresponding manual step**: upload `mandarin.jpeg` and
`spanish.jpeg` under the new names, then delete the old `sjcac.jpeg`/`wG.jpeg` — I can't
touch the S3 bucket from here. To swap a thumbnail in the future: upload a new file to S3
with the same (new) filename. No code change or redeploy needed. Spec: JPG/PNG, 1280×720
recommended, 2 MB max.

### Environment variables (Lambda → Configuration → Environment variables)

| Variable | Purpose |
|---|---|
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | OAuth2 app credentials, shared across all 4 channels |
| `MS_REFRESH_TOKEN`, `ES_REFRESH_TOKEN`, `ES2_REFRESH_TOKEN`, `SS_REFRESH_TOKEN` | Per-channel OAuth refresh tokens |
| `MS_STREAM_ID`, `ES_STREAM_ID`, `ES2_STREAM_ID`, `SS_STREAM_ID` | Persistent stream resource IDs (API IDs, not the human-readable stream key) |
| `EVENTS_S3_BUCKET` | S3 bucket holding thumbnails |
| `SES_FROM_EMAIL`, `SES_TO_EMAIL`, `SES_REGION` | Weekly report email — `SES_REGION` must be `us-west-2` (where the identities were verified) |
| `SHEET_WEBAPP_URL` | The attendance Sheet's deployed Apps Script Web App `/exec` URL |
| `SHEET_WEBAPP_SECRET` | Shared secret — must exactly match `WEBAPP_SHARED_SECRET` in the Sheet's `lambda_integration.gs`. Treat like a password; never put it in this repo or this doc. |
Note the naming convention changed from both PDFs: it's now per-channel prefixes
(`MS_`/`ES_`/`ES2_`/`SS_`), not per-account numbers (`ACCT1_`...`ACCT4_`).

### Credential setup — one script, not three
Both PDFs describe running separate `get_refresh_token.py` and `list_streams.py` scripts. **Those no longer exist.** They've been replaced by a single tool:

```bash
pip install google-auth-oauthlib google-api-python-client
python setup_credentials.py
```

Run it once per Google account. It walks you through OAuth login, discovers (or lets you
manually add) that account's YouTube channels, creates a persistent stream for each one if none exists yet, and prints every env var you need straight to the terminal. It also saves everything — including refresh tokens and RTMP stream keys — to `credentials.json` locally.

**`credentials.json`, `stream_ids.json`, and `client_secrets.json` are all secrets.**
Never commit them, never paste their contents anywhere. `stream_ids.json` in particular contains live RTMP stream keys — anyone with one of those can push video to that channel's persistent stream.

Google Cloud project: one project ("YT Live Automation" or similar) covers every account. Two APIs must be enabled — **YouTube Data API v3** and **YouTube Analytics API** — and the OAuth consent screen must show both "Manage your YouTube account" and "View YouTube Analytics reports" when you authorize, or the Analytics fallback will fail with `invalid_scope`.

### Manual test payloads
Invoke from Lambda console → Test tab:

| Payload | Effect |
|---|---|
| `{}` | Full run — viewer report + event creation + email, all channels |
| `{"mode": "viewer_report"}` | Only fetch viewer counts + send email |
| `{"mode": "create_events"}` | Only create next Sunday's events, no email |
| `{"channel": "ms_channel"}` | Both tasks, one channel only — no email sent |
| `{"mode": "create_events", "channel": "ms_channel"}` | Just create that channel's event |
| `{"dry_run": true}` | Full run, no YouTube writes, no email, no sheet sync — safe anytime |
Response body includes `viewer_report.{success,errors}`, `event_creation.{success,errors}`, `email_sent`, and `sheet_sync` (the sheet sync result dict, or `null` if skipped).

### Rebuild & deploy

```bash
rm -rf build lambda_package.zip
mkdir build
pip install google-auth google-auth-oauthlib google-auth-httplib2 \
  google-api-python-client \
  --target build --platform mlinux_x86_64 --implementation cp \
  --python-version 3.12 --only-binary=:all:
cp handler.py build/handler.py
cd build && zip -r ../lambda_package.zip . && cd ..
```

Then Lambda → Upload From → .zip file → upload `lambda_package.zip`. **Must** use
`--platform mlinux_x86_64` when building on a Mac — without it you get `invalid ELF header` in Lambda, because the Mac build produces binaries Linux can't run.

### Known issues (from `handler.py`'s own docstring)
- **Live chat can't be disabled per-broadcast via API** — set manually every week in YouTube Studio → Content → Live → Edit → Customization → Live chat, for each broadcast. This does not persist between weeks. (Comments are separate and are a one-time account-level Community default — see the note above.) Tracked upstream: [issuetracker.google.com/issues/471770017](https://issuetracker.google.com/issues/471770017).
- **Cantonese can't be automated at all** (404 on stream bind for secondary channels on a multi-channel account) — created manually every week. No tracked upstream issue for this one (471770017 is the live-chat ticket above, not this) — worth searching Google's issue tracker again periodically in case someone else has filed it.
- **English Willow Glen (`es2_channel`)** has embedding disabled at the account level —
  `enable_embed: False` is set to avoid API errors.
- **OAuth tokens need both scopes** (`youtube` + `yt-analytics.readonly`). A token minted with only `youtube` throws `invalid_scope` the first time the Analytics fallback runs (which won't happen until a stream is a few hours to days old) — revoke access at `myaccount.google.com/permissions` and re-run `setup_credentials.py` for that account to fix.

*(The `SES_FROM_EMAIL`/`SES_TO_EMAIL`/`SES_REGION` note used to live in this list — moved up into the Environment Variables table above since it's a plain configuration fact, not a gotcha. `handler.py` briefly had three different SES regions floating around its own docstring — `us-east-2` in the env-var reference table, `us-west-2` as the actual runtime default, and a warning against `us-east-1` in this Known Issues section — all three now agree on `us-west-2`, the correct value.)*

### Troubleshooting

| Error | Likely cause | Fix |
|---|---|---|
| `invalid_scope: Bad Request` | Refresh token missing the Analytics scope | Revoke at `myaccount.google.com/permissions`, re-run `setup_credentials.py` for that account, confirm consent screen shows both permissions |
| `Auth failed` / `Missing env var` | Env var name in Lambda doesn't match `refresh_token_env`/`stream_id_env` in `CHANNELS` | Compare exactly — case-sensitive |
| `Viewer count not yet available` | Too soon after the stream ended | Normal within a few hours; the scheduled run (days later) should work via the Analytics API |
| `invalid ELF header` | Zip built on Mac without the Linux platform flag | Rebuild with `--platform mlinux_x86_64` |
| `Thumbnail not found in S3` | File missing at the expected key | Check `thumbnails/` prefix and filename in the S3 bucket match the `thumbnail_s3_key` for that channel |
| `Stream not found` / 404 on bind | Wrong stream ID, or it's the API resource ID vs. the human-readable key confused | Re-run `setup_credentials.py`, use the `stream_id` value not the `stream_key` |
| Sheet sync always `"skipped"` | `SHEET_WEBAPP_URL`/`SHEET_WEBAPP_SECRET` not set, or don't match the Sheet's `WEBAPP_SHARED_SECRET` | Set both env vars; confirm the secret matches exactly |

---
## Part B — Attendance tracker (Google Sheet + Apps Script)

This lives entirely inside the attendance spreadsheet's **Extensions → Apps Script** editor
— that's the **live, authoritative copy**, and it's easy to forget it's part of the system
since none of it is a file in this AWS folder. It has its own `.gs` files (roughly one per
concern): core logging, form trigger, Lambda web-app endpoint, summary-tab
formula/formatting builder, auto-date population, and a one-time historical migration.

**Local backup copies now live in `apps_script/` in this folder** — `attendance_core.gs`,
`lambda_integration.gs`, `migration.gs`, `auto_date_population.gs`,
`summary_tab_builder.gs` — purely so the scripts aren't lost if the Sheet itself is ever
lost and a new one needs to be rebuilt from scratch. **They are backups, not the live
copy**: if you edit code in the Apps Script editor, those changes don't automatically flow
back here, and vice versa. Keep them in sync manually after any change on either side, or
they'll silently drift apart.

### Data model
**Raw Log tab** — one row per (week, congregation, metric) submission:

| Column | Meaning |
|---|---|
| `week_start_date` | The Sunday this row belongs to (via `getWeekStart()` — buckets any timestamp to the most recent Sunday on/before it) |
| `congregation` | One of the 11 names in `CONGREGATIONS` |
| `metric` | `"IP"` (in-person) or `"YT"` (YouTube viewers) |
| `value` | The number |
| `source` | `"form"` \| `"lambda"` \| `"manual"` \| `"migration"` |
| `submitted_at`, `submitter_email`, `flag`, `notes` | Bookkeeping — `flag` is `""`, `"duplicate"`, or `"non_numeric"` |
`logAttendance()` is the single write path every source goes through. It flags (rather than overwrites) a duplicate submission for the same week+congregation+metric, so two conflicting numbers both stay visible for a human to reconcile — nothing silently gets overwritten.

**Summary tab** — one row per week, pulling `SUMIFS`/`COUNTIFS` formulas from Raw Log per congregation, rolled up per campus (SJ / WG), plus a grand weekly total. A hidden helper sheet computes each column's trailing 4-week average (blending in the tail of the prior year's tab for weeks 1-4, so early-January weeks still get a real comparison baseline), and conditional formatting colors each cell on a Fibonacci-banded blue/orange scale based on how far it deviates from that trailing average.

### Who reports how

| Group | Congregations | YT source |
|---|---|---|
| Automated (Lambda) | SJ Mandarin, SJ English, WG English, WG Spanish (Nueva Vida) | Pushed automatically by `send_to_sheet()` |
| Manual YT | SJ Cantonese, SJ Joint, WG Joint | Reported on the form alongside IP |
| No YT at all | SJ/WG Children Ministry, WG Mandarin (New Spring), WG Arabic | N/A — no livestream |
In-person (`IP`) numbers for every congregation always come from the Google Form
(`onFormSubmit()` → `logCampus()` → `resolveCongregationName()` maps the form's short radio labels to the full congregation names).

### Lambda → Sheet handoff
`doPost()` is the Web App endpoint `handler.py`'s `send_to_sheet()` posts to. Expects:

```json
{
  "secret": "...",
  "results": [
    { "channel": "ms_channel", "date": "2026-07-05", "viewers": 42 }
  ]
}
```

`CHANNEL_TO_CONGREGATION` in that file maps the 4 Lambda channel keys to congregation names — it intentionally does **not** include Cantonese, SJ Joint, or WG Joint; those stay form-only by design. Each result gets routed through the same `logAttendance()` function the form uses, so duplicate/non-numeric handling is identical regardless of source.

### One-time migration
`migrateOldData()` pulls 2026 data from a previous spreadsheet (hardcoded `OLD_SPREADSHEET_ID`) into Raw Log, bypassing the normal validation since historical data is trusted as-is. It's idempotent (checks existing Raw Log rows before writing) but is meant to be run once — not part of ongoing operation.

### Auto-date population
`onEdit()` is a simple trigger (no manual trigger setup needed) that watches cell `A1` on
every tab. Type a year in there (e.g. duplicating the sheet for 2028) and column B
auto-fills with that year's actual Sunday dates.

## How to add a new automated channel
Follow these steps in order — skipping the Sheet-side steps just means the channel automates on YouTube but its viewer counts never show up in the attendance tracker.
1. **Generate credentials for the new Google account.** Run `pip install google-auth-oauthlib google-api-python-client`, then `python setup_credentials.py`, and complete the OAuth login for the account that owns the new channel. This prints a refresh token and a persistent stream ID to the terminal and saves them to `credentials.json`.
2. **Add the new env vars in Lambda.** In Lambda → Configuration → Environment variables, add a new `<PREFIX>_REFRESH_TOKEN` and `<PREFIX>_STREAM_ID` pair (e.g. `KM_REFRESH_TOKEN`, `KM_STREAM_ID`), using the values from step 1. Pick a short, unique prefix that isn't already used by `MS_`/`ES_`/`ES2_`/`SS_`.
3. **Upload a thumbnail to S3.** Add a new file under `<EVENTS_S3_BUCKET>/thumbnails/` (or point at an existing one if the new channel shares a thumbnail with another), following the existing naming convention (lowercase, language- or channel-based name, JPG/PNG, 1280×720 recommended, 2 MB max).
4. **Add an entry to the `CHANNELS` dict in `handler.py`.** This is the only code change needed. Give it a unique key (e.g. `km_channel`), and fill in: the YouTube channel ID, `refresh_token_env` / `stream_id_env` pointing at the env vars from step 2, the service start time, `thumbnail_s3_key` from step 3, the playlist ID to add broadcasts to, and title/description text in the channel's own language.
5. **Rebuild and redeploy the Lambda** using the Rebuild & deploy steps above.
6. **Test before relying on it.** Invoke with `{"channel": "km_channel", "dry_run": true}` first to confirm it resolves correctly with no live writes, then `{"channel": "km_channel"}` for a real single-channel run (no email is sent for single-channel runs, so check the response body / logs directly).
7. **If this channel should feed the attendance Sheet**, continue to the next section — a new entry in `CHANNELS` alone does not make its viewer counts show up in Raw Log.

## How to add a channel/congregation to the attendance Sheet automation
This is what actually gets a channel's viewer counts into Raw Log instead of someone typing them in by hand.
1. **Make sure the congregation exists in `CONGREGATIONS`.** Open the Apps Script editor (Extensions → Apps Script) on the attendance spreadsheet and confirm the congregation name is already listed in the `CONGREGATIONS` array. Add it if it's a brand-new congregation, matching the exact naming style already in use (this is what both the form and the summary tab key off of).
2. **Add a mapping entry in `CHANNEL_TO_CONGREGATION`.** In `lambda_integration.gs`, add a line pairing the new Lambda channel key (e.g. `km_channel`) to the exact congregation name from step 1. This is the only line that connects a `handler.py` channel to a row in the Sheet.
3. **Confirm `SHEET_WEBAPP_URL` and `SHEET_WEBAPP_SECRET` are already set in Lambda.** These are shared across all channels, so if the automation is already sending other channels' viewer counts successfully, nothing changes here — this step is only relevant if this is the very first channel being wired up.
4. **Redeploy the Apps Script Web App.** Any change inside the Apps Script project (including the `CHANNEL_TO_CONGREGATION` edit) requires Deploy → Manage deployments → create a new version, or the live `/exec` URL keeps serving the old code.
5. **Test end-to-end.** Run the Lambda with `{"channel": "km_channel"}` (no `dry_run`), then check the Raw Log tab for a new row with `source = "lambda"` and the correct congregation name and viewer count. If nothing shows up, check the Lambda's logs for the `sheet_sync` result first — a mismatched `SHEET_WEBAPP_SECRET` is the most common cause of a silent failure.
6. **Update the local backup too.** Step 2's edit happened in the live Apps Script editor — mirror the same change in `apps_script/lambda_integration.gs` in this folder so the backup doesn't drift from what's actually deployed.

---
## File inventory (this folder)

| File | What it is |
|---|---|
| `handler.py` | The Lambda function — source of truth for the YouTube automation |
| `setup_credentials.py` | Run locally, once per Google account, to generate refresh tokens + stream IDs |
| `client_secrets.json` | OAuth app credentials downloaded from Google Cloud — **secret** |
| `credentials.json` | Output of `setup_credentials.py` — refresh tokens + RTMP stream keys — **secret** |
| `credentials_for_lambda.json` | An older/separate credentials file — `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN` — **secret** |
| `stream_ids.json` | Persistent stream IDs/keys/RTMP URLs per channel — **secret**. Contains a `CS_STREAM_ID` entry for Cantonese even though it's not in `handler.py`'s `CHANNELS` — leftover from before Cantonese automation was found to be impossible, harmless to leave |
| `thumbnails/` | Local copies of the 3 thumbnail files also uploaded to S3 |
| `apps_script/` | Local backup copies of the 5 Google Apps Script files that actually run inside the attendance Sheet — **backups only**, see [Part B](#part-b--attendance-tracker-google-sheet--apps-script) for why they can drift from the live copy |
| `build/` | Generated by the rebuild step — vendored dependencies + a copy of `handler.py`, not source |
| `lambda_package.zip` | The last built deployment artifact |
| `venv/`, `create/`, `#/` | Local Python virtual environments (yes, one is literally named `#` — harmless, just clutter) — not part of the deployed system |
| `README.md` | The short, public-facing overview for anyone landing on the repo |
| `LICENSE` | MIT |
| `.gitignore` | Excludes all the secret files and bulk directories listed above from git |

## What changed since the PDFs (for anyone diffing against memory)
- Spanish (`ss_channel`) is **active**, not "pending" — it has a real `channel_id` in
  `CHANNELS`, not a `YOUR_SS_CHANNEL_ID` placeholder.
- Env vars renamed from `ACCT1-4_REFRESH_TOKEN` to per-channel `MS_/ES_/ES2_/SS_REFRESH_TOKEN`.
- `get_refresh_token.py` and `list_streams.py` were replaced by one script, `setup_credentials.py`.
- Thumbnail scheme changed from 2 files to 3, and — as of this update — renamed again to
  `mandarin.jpeg` / `english.jpg` / `spanish.jpeg` (previously `sjcac.jpeg` / `english.jpg` /
  `wG.jpeg`). Spanish's thumbnail moved to Spanish's own file rather than sharing Willow
  Glen's.
- New: the Google Sheet sync (`send_to_sheet()`, `SHEET_WEBAPP_URL`/`SHEET_WEBAPP_SECRET`) didn't exist in either PDF at all.
- Spanish's 7:00 PM start time is now confirmed correct (the `# ← confirm correct time` comment in `handler.py` has been removed).
- Schedule moved from Wednesday 5 AM PST to Tuesday 9 AM PST — **confirmed** against the live EventBridge rule (`yt-live-wednesday-trigger`, whose name is now stale but whose schedule is correct).
- Live chat's manual-toggle behavior was clarified: it must be turned off **every week per broadcast**, it does not persist like the Community Defaults setting for comments does — earlier drafts of this doc had that backwards.
- Fixed an internal inconsistency in `handler.py`'s own docstring: the environment-variable reference table listed `SES_REGION` as `us-east-2`, while the actual runtime default was `us-west-2` and a separate Known Issues note warned against `us-east-1`. All three now say `us-west-2`.
- The 5 Apps Script files (previously only pasted into chat) are now saved locally under `apps_script/` as a disaster-recovery backup, and two new runbook sections ("How to add a new automated channel" / "How to add a channel to the Sheet automation") were added to this doc.
- Cleaned up formatting damage this file had picked up along the way: a missing lead sentence at the very top, a mangled `### Manual-test-payloads` heading that broke its anchor link, and a stray empty table row in Quick Reference.
- Corrected a misattributed citation: issue [471770017](https://issuetracker.google.com/issues/471770017) is specifically "Disable/Enable Live Broadcast's Chat from API" — it only tracks the live-chat limitation. It had briefly also been cited under the Cantonese multi-channel-bind limitation, which is a separate, untracked issue.