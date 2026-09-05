"""One-off: ask Gemini which models this key can actually call."""
import os

import requests

key = os.environ["GEMINI_KEY"]
lines = []
for ver in ("v1beta", "v1"):
    try:
        r = requests.get(
            f"https://generativelanguage.googleapis.com/{ver}/models",
            params={"key": key}, timeout=60,
        )
        if r.ok:
            for m in r.json().get("models", []):
                if "generateContent" in m.get("supportedGenerationMethods", []):
                    lines.append(f"{ver}: {m['name']}")
        else:
            lines.append(f"{ver}: HTTP {r.status_code} {r.text[:200]}")
    except Exception as e:
        lines.append(f"{ver}: {type(e).__name__} {e}")

body = "\n".join(lines) or "(nothing returned)"
body = body.replace(key, "<GEMINI_KEY>")
requests.post(
    f"https://api.github.com/repos/{os.environ['REPO']}/issues",
    headers={"Authorization": f"Bearer {os.environ['GH_TOKEN']}",
             "Accept": "application/vnd.github+json"},
    json={"title": "diag: available models", "body": f"```\n{body}\n```"},
    timeout=60,
)
print(body)
