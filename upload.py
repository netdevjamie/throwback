"""
Bulk upload activity files to Strava.

Usage:
    .venv/bin/python upload.py <dir_of_activity_files>
    .venv/bin/python upload.py --one <path/to/file.fit>     # smoke test

Behavior:
- Walks the directory for .fit / .fit.gz / .tcx / .tcx.gz / .gpx / .gpx.gz files.
- Refreshes the access token before starting (Strava expires them every 6h).
- Uploads one at a time, polls until processed.
- Strava rejects duplicates server-side; we record them and don't fail.
- Writes per-file results to uploads_log.jsonl so re-runs skip done files.
- Sleeps between uploads to stay under 200 req / 15 min.
- Short-term rate limit -> sleep 15 minutes.
- Long-term (daily) rate limit -> sleep until midnight UTC + 1 min.
"""

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from stravalib.exc import ActivityUploadFailed, RateLimitExceeded

from auth import get_client

LOG_PATH = Path(__file__).parent / "uploads_log.jsonl"
# Compound suffixes here are checked with str.endswith, not Path.suffix.
EXTS = {".fit", ".fit.gz", ".tcx", ".tcx.gz", ".gpx", ".gpx.gz"}
# Each upload also costs 1-3 poll requests + an auth refresh on startup;
# 5s outer pacing keeps the total well under Strava's 200 req / 15 min
# limit in practice. RateLimitExceeded triggers a 15-min backoff anyway.
SLEEP_BETWEEN_UPLOADS = 5


def already_done() -> set[str]:
    done = set()
    if LOG_PATH.exists():
        with LOG_PATH.open() as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if entry.get("status") in {"uploaded", "duplicate"}:
                        done.add(entry["file"])
                except json.JSONDecodeError:
                    pass
    return done


def log_result(entry: dict):
    with LOG_PATH.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def detect_data_type(path: Path) -> str:
    name = path.name.lower()
    for ext in (".fit.gz", ".tcx.gz", ".gpx.gz"):
        if name.endswith(ext):
            return ext.lstrip(".")
    return path.suffix.lower().lstrip(".")


def classify_rate_limit(msg: str) -> str:
    # Strava returns either "Short term API rate limit exceeded" (200 req / 15 min)
    # or "Long term API rate limit exceeded" (2000 req / day).
    if "long term" in msg.lower():
        return "rate_limited_daily"
    return "rate_limited"


def upload_one(client, path: Path) -> dict:
    data_type = detect_data_type(path)
    try:
        with open(path, "rb") as f:
            uploader = client.upload_activity(activity_file=f, data_type=data_type)
        for _ in range(60):
            uploader.poll()
            if uploader.is_complete:
                break
            time.sleep(1)
        if uploader.activity_id:
            return {"status": "uploaded", "activity_id": uploader.activity_id}
        return {"status": "pending", "note": "did not complete in 60s"}
    except ActivityUploadFailed as e:
        msg = str(e).lower()
        if "rate limit" in msg:
            return {"status": classify_rate_limit(msg), "error": str(e)}
        if "duplicate" in msg:
            return {"status": "duplicate", "error": str(e)}
        return {"status": "error", "error": str(e)}
    except RateLimitExceeded as e:
        return {"status": classify_rate_limit(str(e)), "error": str(e)}
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}


def seconds_until_utc_midnight() -> int:
    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return int((tomorrow - now).total_seconds())


def collect_files(root: Path) -> list[Path]:
    return sorted(
        p for p in root.rglob("*")
        if p.is_file() and any(p.name.lower().endswith(e) for e in EXTS)
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="Directory of activity files, or a single file with --one")
    ap.add_argument("--one", action="store_true", help="Treat target as a single file (smoke test)")
    ap.add_argument("--sleep", type=int, default=SLEEP_BETWEEN_UPLOADS)
    args = ap.parse_args()

    target = Path(args.target).expanduser()
    if not target.exists():
        sys.exit(f"Not found: {target}")

    files = [target] if args.one else collect_files(target)
    if not files:
        sys.exit(f"No activity files found under {target}")

    done = already_done()
    pending = [f for f in files if str(f) not in done]
    print(f"Found {len(files)} files. {len(done)} already done. {len(pending)} to upload.")

    print("Authenticating with Strava...")
    client = get_client()
    print("Authenticated.\n")

    counts = {"uploaded": 0, "duplicate": 0, "error": 0,
              "rate_limited": 0, "rate_limited_daily": 0, "pending": 0}
    i = 0
    while i < len(pending):
        path = pending[i]
        print(f"[{i+1}/{len(pending)}] {path.name}", end=" ... ", flush=True)
        result = upload_one(client, path)
        result["file"] = str(path)
        result["ts"] = time.time()
        log_result(result)
        counts[result["status"]] = counts.get(result["status"], 0) + 1
        print(result["status"])
        if result["status"] == "rate_limited_daily":
            wait_s = seconds_until_utc_midnight() + 60
            wake_at = datetime.now(timezone.utc) + timedelta(seconds=wait_s)
            print(f"Daily limit hit. Sleeping {wait_s//60} min "
                  f"(until {wake_at.strftime('%H:%M UTC')}). Retrying same file on wake.")
            time.sleep(wait_s)
            continue  # retry this file; the daily window has reset
        if result["status"] == "rate_limited":
            print("Short-term limit hit. Sleeping 15 min. Retrying same file on wake.")
            time.sleep(900)
            continue
        i += 1
        if i < len(pending):
            time.sleep(args.sleep)

    print("\n--- Summary ---")
    for k, v in counts.items():
        print(f"  {k}: {v}")
    print(f"\nFull log: {LOG_PATH}")


if __name__ == "__main__":
    main()
