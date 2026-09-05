"""One-off: find which image-generation API shape this key actually accepts,
and what dimensions come back."""
import base64
import io
import os

import requests
from PIL import Image

KEY = os.environ["GEMINI_KEY"]
H = {"x-goog-api-key": KEY, "Content-Type": "application/json"}
PROMPT = "A minimalist penthouse terrace overlooking a hazy coastline at golden hour, warm travertine, editorial photography, no text"
lines = []


def note(label, ok, detail=""):
    lines.append(f"{'OK  ' if ok else 'FAIL'} {label}  {detail}")


def probe_image(raw, label):
    try:
        im = Image.open(io.BytesIO(raw))
        note(label, True, f"{im.size[0]}x{im.size[1]} {im.format} {len(raw)//1024}KB")
    except Exception as e:
        note(label, False, f"decoded but not an image: {e}")


for model in ("gemini-2.5-flash-image", "nano-banana-pro-preview", "gemini-3.1-flash-image"):
    # A: generateContent + imageConfig aspect ratio
    for label, cfg in (
        ("A generateContent+imageConfig", {"responseModalities": ["IMAGE"],
                                           "imageConfig": {"aspectRatio": "9:16"}}),
        ("B generateContent bare", {"responseModalities": ["IMAGE"]}),
    ):
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers=H, timeout=120,
                json={"contents": [{"parts": [{"text": PROMPT}]}], "generationConfig": cfg},
            )
            if not r.ok:
                note(f"{model} {label}", False, f"{r.status_code} {r.text[:120]}")
                continue
            parts = r.json()["candidates"][0]["content"]["parts"]
            blob = next((p for p in parts if "inlineData" in p or "inline_data" in p), None)
            if not blob:
                note(f"{model} {label}", False, f"no inlineData; keys={[list(p) for p in parts]}")
                continue
            d = blob.get("inlineData") or blob.get("inline_data")
            probe_image(base64.b64decode(d["data"]), f"{model} {label}")
        except Exception as e:
            note(f"{model} {label}", False, f"{type(e).__name__} {e}")

# C: newer interactions endpoint
try:
    r = requests.post(
        "https://generativelanguage.googleapis.com/v1beta/interactions",
        headers=H, timeout=120,
        json={"model": "gemini-2.5-flash-image",
              "input": [{"type": "text", "text": PROMPT}],
              "response_format": {"type": "image", "aspect_ratio": "9:16"}},
    )
    note("C interactions endpoint", r.ok, f"{r.status_code} {r.text[:200]}")
except Exception as e:
    note("C interactions endpoint", False, f"{type(e).__name__} {e}")

body = "\n".join(lines).replace(KEY, "<KEY>")
print(body)
requests.post(
    f"https://api.github.com/repos/{os.environ['REPO']}/issues",
    headers={"Authorization": f"Bearer {os.environ['GH_TOKEN']}",
             "Accept": "application/vnd.github+json"},
    json={"title": "diag: image api", "body": f"```\n{body}\n```"}, timeout=60)
