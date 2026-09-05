"""Delete generated images older than KEEP_DAYS so the repo doesn't grow forever."""

import datetime
import pathlib

KEEP_DAYS = 60
cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=KEEP_DAYS)

removed = 0
for p in pathlib.Path("posts").glob("*.jpg"):
    try:
        stamp = datetime.datetime.strptime(p.stem, "%Y%m%d-%H%M").replace(
            tzinfo=datetime.timezone.utc
        )
    except ValueError:
        continue  # not one of ours
    if stamp < cutoff:
        p.unlink()
        removed += 1

print(f"Removed {removed} old images")
