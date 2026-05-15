"""
Filter raw FIT files into a clean upload set.

Garmin's GDPR export bundles every uploaded file: workout activities
mixed with monitoring data (sleep, HR, steps), weight-scale readings,
and other non-activity records. This script reads the file_id header
of each FIT and keeps only those with type='activity'.

Usage:
    .venv/bin/python filter_activities.py <staging_dir> <out_dir>
"""

import argparse
import os
import shutil
from collections import Counter
from pathlib import Path

from fitparse import FitFile


def file_type(path: Path) -> str:
    try:
        ff = FitFile(str(path))
        for msg in ff.get_messages("file_id"):
            return str(msg.get_value("type"))
    except Exception as e:
        return f"__error__:{type(e).__name__}"
    return "__no_file_id__"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("staging", help="Directory of raw FIT files from Garmin export")
    ap.add_argument("out", help="Output directory for activity-only FIT files")
    ap.add_argument("--copy", action="store_true",
                    help="Copy files instead of symlinking (default: relative symlink)")
    args = ap.parse_args()

    staging = Path(args.staging).expanduser()
    out = Path(args.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)

    fits = sorted(p for p in staging.iterdir() if p.suffix.lower() == ".fit")
    print(f"Scanning {len(fits)} files in {staging}...")

    types = Counter()
    activities = []
    for i, p in enumerate(fits, 1):
        t = file_type(p)
        types[t] += 1
        if t == "activity":
            activities.append(p)
        if i % 1000 == 0:
            print(f"  [{i}/{len(fits)}]")

    print("\nFile type breakdown:")
    for t, n in types.most_common():
        print(f"  {t:25s} {n}")

    error_count = sum(n for t, n in types.items() if t.startswith("__error__"))
    if error_count:
        print(f"\nNote: {error_count} files could not be parsed and were skipped.")

    print(f"\nKeeping {len(activities)} activity files. Linking into {out}...")
    for src in activities:
        dst = out / src.name
        if dst.exists():
            continue
        if args.copy:
            shutil.copy2(src, dst)
        else:
            # Relative symlink so moving the staging tree doesn't break links.
            rel = Path(os.path.relpath(src.resolve(), dst.parent.resolve()))
            dst.symlink_to(rel)

    print(f"Done. {len(activities)} files ready in {out}")


if __name__ == "__main__":
    main()
