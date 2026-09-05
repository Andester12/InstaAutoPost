"""
Generate one post (image + caption) with free AI and publish it to Instagram.

Env vars required:
  IG_TOKEN    long-lived Instagram user access token
  IG_USER_ID  your Instagram professional account id
  GEMINI_KEY  Google AI Studio key (free tier)
  GH_REPO     "username/repo"  -> used to build the public raw image URL
"""

import base64
import datetime
import io
import json
import os
import pathlib
import sys
import time
import urllib.parse

import requests
from PIL import Image

GRAPH = "https://graph.instagram.com/v21.0"
POSTS_DIR = pathlib.Path("posts")
TIMEOUT = 90


def load_config():
    with open("config.json") as f:
        return json.load(f)


MODELS = [
    "gemini-2.5-flash",        # stable, generous free tier
    "gemini-flash-latest",     # alias, tracks whatever is current
    "gemini-3.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-flash-lite-latest",
]


def generate_text(topic, style, gemini_key):
    """Ask Gemini for a scene description + caption. Returns (scene, caption).

    The key goes in a header, never the query string: requests puts the full
    URL into its exception messages, and those get logged.

    Model names are tried in order because Google retires them on a rolling
    basis -- a hardcoded name is a guaranteed future 404.
    """
    prompt = (
        f"You write content for an Instagram account about: {topic}\n"
        f"Visual style: {style}\n\n"
        "The image and the caption do different jobs. The image is pure "
        "atmosphere. The caption carries the substance.\n\n"
        "Invent ONE new post. Reply with exactly two blocks separated by |||\n"
        "Block 1: a single-sentence image-generation prompt describing an "
        "aesthetic scene or object in the visual style above - something that "
        "photographs well. Never describe charts, graphs, diagrams, screens, "
        "numbers, logos, faces, or any text appearing in the image.\n"
        "Block 2: an Instagram caption, 2-3 sentences, explaining ONE concrete "
        "economic idea connected to what is pictured, then 5 relevant hashtags. "
        "Explain how something works. Never give financial advice, never "
        "recommend buying or selling anything, never promise or imply returns, "
        "and never invent statistics, percentages, prices or dates - if you do "
        "not know a figure, describe the mechanism without numbers.\n"
        "Return nothing else. No markdown, no labels, no preamble."
    )
    headers = {"x-goog-api-key": gemini_key, "Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 1.0},
    }

    errors = []
    raw = None
    for model in MODELS:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent"
        )
        # Free tier returns 503/429 under load often enough that one attempt
        # is not a fair test of a model.
        for attempt in range(4):
            try:
                r = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
            except requests.RequestException as e:
                # timeouts and connection resets are as transient as a 503
                if attempt < 3:
                    time.sleep(10 * (attempt + 1))
                    continue
                errors.append(f"{model}: {type(e).__name__} after 4 tries")
                break
            if r.status_code in (429, 500, 503):
                if attempt < 3:
                    time.sleep(10 * (attempt + 1))
                    continue
                errors.append(f"{model}: {r.status_code} after 4 tries")
                break
            if r.status_code == 404:
                errors.append(f"{model}: 404 (retired or unavailable)")
                break
            if not r.ok:
                # never echo r.url -- it is clean now, but stay defensive
                raise RuntimeError(
                    f"Gemini {model} -> HTTP {r.status_code}: {r.text[:300]}"
                )
            raw = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            break
        if raw is not None:
            break
    if raw is None:
        raise RuntimeError("No usable Gemini model. Tried: " + "; ".join(errors))

    if "|||" not in raw:
        raise ValueError(f"Model did not use the separator. Got: {raw[:300]}")
    scene, caption = raw.split("|||", 1)
    return scene.strip(), caption.strip()


def _fit(raw, path, width, height):
    """Force exact output dimensions.

    Instagram rejects feed images outside roughly 4:5 to 1.91:1, and reels
    want 9:16, so whatever the generator returns gets centre-cropped to the
    target rather than trusted.
    """
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    target = width / height
    have = im.width / im.height
    if have > target:                      # too wide -> crop sides
        new_w = int(im.height * target)
        left = (im.width - new_w) // 2
        im = im.crop((left, 0, left + new_w, im.height))
    elif have < target:                    # too tall -> crop top/bottom
        new_h = int(im.width / target)
        top = (im.height - new_h) // 2
        im = im.crop((0, top, im.width, top + new_h))
    im = im.resize((width, height), Image.LANCZOS)
    im.save(path, "JPEG", quality=90)


def _gemini_image(scene, path, key, width, height, model):
    """Nano Banana. Requires billing -- image models have no free tier."""
    ratio = "9:16" if height > width else ("1:1" if height == width else "16:9")
    headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
    body = {"contents": [{"parts": [{"text": scene}]}]}

    for cfg in (
        {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": ratio}},
        {"responseModalities": ["IMAGE"]},
    ):
        r = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent",
            headers=headers, json={**body, "generationConfig": cfg}, timeout=TIMEOUT,
        )
        if r.status_code == 400:
            continue                        # imageConfig unsupported -> try bare
        if not r.ok:
            raise RuntimeError(f"{model} -> HTTP {r.status_code}: {r.text[:200]}")
        parts = r.json()["candidates"][0]["content"]["parts"]
        blob = next((p.get("inlineData") or p.get("inline_data")
                     for p in parts if "inlineData" in p or "inline_data" in p), None)
        if not blob:
            raise RuntimeError(f"{model} returned no image data")
        _fit(base64.b64decode(blob["data"]), path, width, height)
        return
    raise RuntimeError(f"{model} rejected both request shapes")


def _pollinations_image(scene, path, width, height):
    """Free, unauthenticated, rate limited under load."""
    url = (
        "https://image.pollinations.ai/prompt/"
        + urllib.parse.quote(scene)
        + f"?width={width}&height={height}&nologo=true"
    )
    for attempt in range(3):
        r = requests.get(url, timeout=TIMEOUT)
        if r.ok and r.headers.get("content-type", "").startswith("image/"):
            _fit(r.content, path, width, height)
            return
        time.sleep(20)  # anonymous tier is rate limited
    raise RuntimeError("Image generation failed after 3 attempts")


def generate_image(scene, path, width=1080, height=1080, cfg=None, gemini_key=None):
    """Gemini if configured and paid for, Pollinations otherwise.

    Gemini failures fall back rather than killing the run: a lapsed card or a
    quota change should degrade the images, not stop the account posting.
    """
    cfg = cfg or {}
    if cfg.get("image_provider") == "gemini" and gemini_key:
        try:
            _gemini_image(scene, path, gemini_key, width, height,
                          cfg.get("image_model", "gemini-2.5-flash-image"))
            print("Image via Gemini:", cfg.get("image_model"))
            return
        except Exception as e:
            print(f"Gemini image failed ({e}); falling back to Pollinations")
    _pollinations_image(scene, path, width, height)
    print("Image via Pollinations")


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
    generate_image(scene, POSTS_DIR / name, cfg=cfg,
                   gemini_key=os.environ["GEMINI_KEY"])
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
