"""One-off: work out how this Gemini credential must be presented, and which
models it can call. Newer AI Studio keys (AQ.* format) are rejected as a
?key= query param and want a header instead."""
import os

import requests

key = os.environ["GEMINI_KEY"]
lines = [f"key prefix: {key[:6]}  len: {len(key)}", ""]

modes = {
    "query ?key=":        (dict(params={"key": key}), {}),
    "header x-goog-api-key": (dict(), {"x-goog-api-key": key}),
    "header Bearer":      (dict(), {"Authorization": f"Bearer {key}"}),
}

working = []
for ver in ("v1beta", "v1"):
    for label, (kw, hdr) in modes.items():
        try:
            r = requests.get(
                f"https://generativelanguage.googleapis.com/{ver}/models",
                headers=hdr, timeout=60, **kw)
            if r.ok:
                names = [m["name"] for m in r.json().get("models", [])
                         if "generateContent" in m.get("supportedGenerationMethods", [])]
                lines.append(f"OK   {ver} via {label}  -> {len(names)} models")
                working.append((ver, label, names))
            else:
                msg = r.json().get("error", {}).get("message", r.text)[:90]
                lines.append(f"FAIL {ver} via {label}  -> {r.status_code} {msg}")
        except Exception as e:
            lines.append(f"FAIL {ver} via {label}  -> {type(e).__name__} {e}")

if working:
    ver, label, names = working[0]
    lines += ["", f"--- models available on {ver} via {label} ---"] + names

body = "\n".join(lines).replace(key, "<GEMINI_KEY>")
requests.post(
    f"https://api.github.com/repos/{os.environ['REPO']}/issues",
    headers={"Authorization": f"Bearer {os.environ['GH_TOKEN']}",
             "Accept": "application/vnd.github+json"},
    json={"title": "diag: auth shape", "body": f"```\n{body}\n```"},
    timeout=60,
)
print(body)
