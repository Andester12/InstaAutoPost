"""
Generate one post (image + caption) with free AI and publish it to Instagram.

Env vars required:
  IG_TOKEN    long-lived Instagram user access token
  IG_USER_ID  your Instagram professional account id
  GEMINI_KEY  Google AI Studio key (free tier)
  GH_REPO     "username/repo"  -> used to build the public raw image URL
"""

import datetime
import json
import os
import pathlib
import sys
import time
import urllib.parse

import requests

GRAPH = "https://graph.instagram.com/v21.0"
POSTS_DIR = pathlib.Path("posts")
TIMEOUT = 90


def load_config():
    with open("config.json") as f:
        return json.load(f)


def generate_text(topic, style, gemini_key):
    """Ask Gemini for a scene description + caption. Returns (scene, caption)."""
    prompt = (
        f"You write content for an Instagram account about: {topic}\n"
        f"Visual style: {style}\n\n"
        "Invent ONE new post. Reply with exactly two blocks separated by |||\n"
        "Block 1: a single-sentence image-generation prompt describing the visual. "
        "No text or words in the image.\n"
        "Block 2: an Instagram caption, 2-3 sentences, then 5 relevant hashtags.\n"
        "Return nothing else. No markdown, no labels, no preamble."
    )
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.0-flash:generateContent"
    )
    r = requests.post(
        url,
        params={"key": gemini_key},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 1.0},
        },
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    raw = r.json()["candidates"][0]["content"]["parts"][0]["text"]

    if "|||" not in raw:
        raise ValueError(f"Model did not use the separator. Got: {raw[:300]}")
    scene, caption = raw.split("|||", 1)
    return scene.strip(), caption.strip()


def generate_image(scene, path):
    """Free image generation, no API key needed."""
    url = (
        "https://image.pollinations.ai/prompt/"
        + urllib.parse.quote(scene)
        + "?width=1080&height=1080&nologo=true"
    )
    for attempt in range(3):
        r = requests.get(url, timeout=TIMEOUT)
        if r.ok and r.headers.get("content-type", "").startswith("image/"):
            path.write_bytes(r.content)
            return
        time.sleep(20)  # anonymous tier is rate limited
    raise RuntimeError("Image generation failed after 3 attempts")


def publish(image_url, caption, ig_id, token):
    """Two-step publish: create container, then publish it."""
    r = requests.post(
        f"{GRAPH}/{ig_id}/media",
        data={"image_url": image_url, "caption": caption, "access_token": token},
        timeout=TIMEOUT,
    )
    if not r.ok:
        raise RuntimeError(f"Container creation failed: {r.status_code} {r.text}")
    container_id = r.json()["id"]

    # Meta fetches the image asynchronously; wait for the container to be ready.
    for _ in range(12):
        time.sleep(5)
        s = requests.get(
            f"{GRAPH}/{container_id}",
            params={"fields": "status_code", "access_token": token},
            timeout=TIMEOUT,
        ).json()
        status = s.get("status_code")
        if status == "FINISHED":
            break
        if status == "ERROR":
            raise RuntimeError(f"Container errored: {s}")
    else:
        raise RuntimeError("Container never reached FINISHED")

    r = requests.post(
        f"{GRAPH}/{ig_id}/media_publish",
        data={"creation_id": container_id, "access_token": token},
        timeout=TIMEOUT,
    )
    if not r.ok:
        raise RuntimeError(f"Publish failed: {r.status_code} {r.text}")
    return r.json()["id"]


def main():
    cfg = load_config()
    token = os.environ["IG_TOKEN"]
    ig_id = os.environ["IG_USER_ID"]
    repo = os.environ["GH_REPO"]

    scene, caption = generate_text(cfg["topic"], cfg["style"], os.environ["GEMINI_KEY"])
    print("SCENE:", scene)
    print("CAPTION:", caption)

    POSTS_DIR.mkdir(exist_ok=True)
    name = f"{datetime.datetime.now(datetime.timezone.utc):%Y%m%d-%H%M}.jpg"
    generate_image(scene, POSTS_DIR / name)
    print("Image saved:", name)

    # The commit step in the workflow runs between here and publish.py's URL use,
    # so write the metadata out and let the workflow finish the job.
    with open("pending.json", "w") as f:
        json.dump(
            {
                "image_url": f"https://raw.githubusercontent.com/{repo}/main/posts/{name}",
                "caption": caption,
            },
            f,
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("FAILED:", e, file=sys.stderr)
        sys.exit(1)
