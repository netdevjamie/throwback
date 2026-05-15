# throwback

Bulk-imports a full Garmin Connect history into Strava. Handles the messy parts of a GDPR data export: filters the ~94% of files that are background telemetry rather than workouts, refreshes OAuth tokens on demand, treats Strava's server-side duplicate detection as success, logs every file's outcome so re-runs skip already-uploaded activities, and stays under the 200 req / 15 min API rate limit.

Built when I switched from Garmin to Strava as my primary fitness platform and discovered that the only sane way to move ~1,000 historical activities is to write the tool yourself.

## Pipeline

```
Garmin GDPR export (a single ZIP, hundreds of MB)
        │
        ▼   unzip outer + nested UploadedFiles_*.zip
fit_staging/   ~16,000 raw FIT files (workouts + monitoring + sleep + ...)
        │
        ▼   filter_activities.py  (reads each FIT's file_id header)
activities_to_upload/   ~1,000 actual workout files
        │
        ▼   upload.py  (rate-limited, resumable, dedup-aware)
Strava
```

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install stravalib python-dotenv fitparse
cp .env.template .env   # fill in STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET
.venv/bin/python do_oauth.py   # browser OAuth, writes tokens to .env
.venv/bin/python check_auth.py # confirm auth works
.venv/bin/python smoke_test.py # round-trip with a synthetic GPX in Central Park
```

Create the API app at https://www.strava.com/settings/api. Set
**Authorization Callback Domain** to `localhost`. Use `app_icon.png`
from this repo if Strava asks for an icon during setup.

## Running an import

After requesting a [Garmin GDPR data export](https://www.garmin.com/en-US/account/datamanagement/exportdata/), wait for the
download email (typically 1–14 days), then:

```bash
# 1. Pull the FIT files out of the nested archives
unzip Garmin_Download.zip "DI_CONNECT/DI-Connect-Uploaded-Files/*.zip" -d /tmp/garmin/
mkdir -p fit_staging && cd fit_staging
unzip -oq /tmp/garmin/DI_CONNECT/DI-Connect-Uploaded-Files/UploadedFiles_0-_Part1.zip
unzip -oq /tmp/garmin/DI_CONNECT/DI-Connect-Uploaded-Files/UploadedFiles_0-_Part2.zip
cd ..

# 2. Filter to real activities only (drops sleep/HR/monitoring data)
.venv/bin/python filter_activities.py fit_staging/ activities_to_upload/

# 3. Bulk upload
.venv/bin/python upload.py activities_to_upload/
```

The upload script logs every result to `uploads_log.jsonl`. Killing the
script mid-run and restarting is safe; previously-uploaded files are
skipped on the next pass. Strava's daily upload limit is generous but
finite — a 1,000-activity history finishes in ~85 minutes at the default
5-second pacing.

## Files

| File | Purpose |
|---|---|
| `auth.py` | Shared token refresh + Client construction |
| `do_oauth.py` | One-time OAuth: opens browser, captures token via localhost:8000 |
| `check_auth.py` | Sanity check: refresh token + fetch athlete profile |
| `smoke_test.py` | Round-trip validation: uploads a synthetic GPX, verifies, then prompts manual delete |
| `filter_activities.py` | Reads FIT file headers and keeps only `file_type == 'activity'` |
| `upload.py` | Bulk uploader with dedup, resume, and rate-limit handling |
| `.env.template` | Credential placeholders. The real `.env` is gitignored. |
| `app_icon.png` | Plain orange icon for the Strava API app form |

## Notes on quirks

- **Strava removed `DELETE` from the public API.** Test activities have to
  be deleted manually in the Strava web UI.
- **The GDPR export download link expires in ~3 days.** Treat the email as urgent.
- **Garmin's export bundles a lot more than activities** — sleep, HR,
  weight scale, body battery, training readiness, step monitoring. The
  `file_id` message in each FIT identifies the kind of file; only those
  with `type == 'activity'` are real workouts.
- **Duplicates aren't errors.** Strava de-duplicates by activity start
  time and device, so re-uploading already-synced activities is
  expected and the script treats it as success.

## License

MIT — see [LICENSE](LICENSE).
