"""
Second half of the daily run. Reads pending.json (written by post.py, image
already committed and served from raw.githubusercontent.com) and publishes it.

Split from post.py on purpose: Meta cURLs the image from a public URL, so the
file must be pushed to GitHub before this runs.
"""

import json
import os
import sys
import time

import requests

from post import publish

TIMEOUT = 90


def wait_until_live(url, tries=10, delay=15):
    """raw.githubusercontent.com can lag a few seconds behind the push."""
    for _ in range(tries):
        try:
            r = requests.head(url, timeout=30, allow_redirects=True)
            if r.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(delay)
    return False


def main():
    with open("pending.json") as f:
        pending = json.load(f)

    url = pending["image_url"]
    if not wait_until_live(url):
        raise RuntimeError(f"Image URL never became reachable: {url}")

    media_id = publish(
        url, pending["caption"], os.environ["IG_USER_ID"], os.environ["IG_TOKEN"]
    )
    print("Published media id:", media_id)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("FAILED:", e, file=sys.stderr)
        sys.exit(1)
