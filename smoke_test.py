"""
Smoke test: full upload + verify round trip.

Generates a synthetic GPX track, uploads it to Strava, waits for
processing, and confirms it appears server-side. Use to validate
the full pipeline before running a real bulk import.

Note: Strava removed DELETE from the public API, so the test
activity must be deleted manually from the web UI after running.
"""

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from auth import get_client

GPX_PATH = Path(__file__).parent / "_smoke_test.gpx"


def make_gpx():
    # 5 GPS points in Central Park NYC. Neutral public location so the
    # test activity is anonymous if cleanup is missed.
    start_lat = 40.7829
    start_lon = -73.9654
    start_time = datetime(2010, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    points = []
    for i in range(5):
        lat = start_lat
        lon = start_lon + (i * 0.00005)
        t = start_time.replace(second=i * 6)
        points.append(
            f'      <trkpt lat="{lat:.6f}" lon="{lon:.6f}">'
            f'<time>{t.strftime("%Y-%m-%dT%H:%M:%SZ")}</time>'
            f'</trkpt>'
        )
    gpx = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<gpx version="1.1" creator="throwback-smoke-test" '
        'xmlns="http://www.topografix.com/GPX/1/1">\n'
        '  <trk>\n'
        '    <name>SMOKE_TEST_DELETE_ME</name>\n'
        '    <type>walking</type>\n'
        '    <trkseg>\n'
        + "\n".join(points)
        + '\n    </trkseg>\n'
        '  </trk>\n'
        '</gpx>\n'
    )
    GPX_PATH.write_text(gpx)


def main():
    print("Generating synthetic GPX...")
    make_gpx()
    print(f"  -> {GPX_PATH}")

    print("Authenticating...")
    client = get_client()

    print("Uploading...")
    with open(GPX_PATH, "rb") as f:
        uploader = client.upload_activity(
            activity_file=f,
            data_type="gpx",
            name="SMOKE_TEST_DELETE_ME",
            description="Pipeline validation; will be deleted manually.",
            activity_type="walk",
        )

    print("Polling until processed...")
    for i in range(60):
        uploader.poll()
        if uploader.is_complete:
            break
        time.sleep(1)
        print(f"  [{i+1}s] status: {uploader.status}", end="\r")

    print()
    if not uploader.activity_id:
        print(f"FAILED: upload did not complete. error: {uploader.error}")
        sys.exit(1)

    activity_id = uploader.activity_id
    print(f"Uploaded as activity {activity_id}")
    print(f"  URL: https://www.strava.com/activities/{activity_id}")

    print("Fetching to verify it exists server-side...")
    activity = client.get_activity(activity_id)
    print(f"  Confirmed: name='{activity.name}', type={activity.type}")

    print("\nManual cleanup: delete the test activity in the Strava web UI:")
    print(f"  https://www.strava.com/activities/{activity_id}")
    print("  (Edit -> Delete Activity)")

    GPX_PATH.unlink()
    print("\nSmoke test PASSED. Pipeline is ready for a real bulk run.")


if __name__ == "__main__":
    main()
