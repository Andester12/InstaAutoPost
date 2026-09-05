"""
Second half of a reel run. The mp4 is already force-pushed to the `media`
branch, so it is live on raw.githubusercontent.com; this creates the REELS
container and publishes it.

Reels take far longer to process than images -- Meta transcodes the video --
so the poll window is minutes, not seconds. Meta's own guidance is to check
roughly once a minute for up to five.
"""

import json
import os
import sys
import time

import requests

from publish import wait_until_live

GRAPH = "https://graph.instagram.com/v21.0"
TIMEOUT = 90
POLL_SECONDS = 15
POLL_LIMIT = 24  # 6 minutes


def publish_reel(video_url, caption, ig_id, token):
    r = requests.post(
        f"{GRAPH}/{ig_id}/media",
        data={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "share_to_feed": "true",
            "access_token": token,
        },
        timeout=TIMEOUT,
    )
    if not r.ok:
        raise RuntimeError(f"Reel container creation failed: {r.status_code} {r.text}")
    container_id = r.json()["id"]
    print("Container:", container_id)

    for i in range(POLL_LIMIT):
        time.sleep(POLL_SECONDS)
        s = requests.get(
            f"{GRAPH}/{container_id}",
            params={"fields": "status_code,status", "access_token": token},
            timeout=TIMEOUT,
        ).json()
        status = s.get("status_code")
        print(f"  [{(i + 1) * POLL_SECONDS}s] {status}")
        if status == "FINISHED":
            break
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Container {status}: {s}")
    else:
        raise RuntimeError("Container never reached FINISHED within 6 minutes")

    r = requests.post(
        f"{GRAPH}/{ig_id}/media_publish",
        data={"creation_id": container_id, "access_token": token},
        timeout=TIMEOUT,
    )
    if not r.ok:
        raise RuntimeError(f"Reel publish failed: {r.status_code} {r.text}")
    return r.json()["id"]


def main():
    with open("pending_reel.json") as f:
        pending = json.load(f)

    url = pending["video_url"]
    if not wait_until_live(url):
        raise RuntimeError(f"Video URL never became reachable: {url}")
    print("Video live:", url)

    media_id = publish_reel(
        url, pending["caption"], os.environ["IG_USER_ID"], os.environ["IG_TOKEN"]
    )
    print("Published reel id:", media_id)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("FAILED:", e, file=sys.stderr)
        sys.exit(1)
