"""Setup-time diagnostics: post the run log to the repo's issues.

Exists because the GitHub Actions log blob host is unreachable from the
environment this was configured in. Safe to delete once the bot is trusted.

Secrets are scrubbed before posting: tracebacks from `requests` embed the
full request URL, which for Gemini includes ?key=<API key>.
"""
import os
import pathlib
import re

import requests

log = pathlib.Path("debug/last_run.log")
text = log.read_text()[-55000:] if log.exists() else "(no log file produced)"

# 1. blank out the literal secret values
for var in ("GEMINI_KEY", "IG_TOKEN", "IG_USER_ID", "GH_TOKEN"):
    val = os.environ.get(var)
    if val and len(val) > 6:
        text = text.replace(val, f"<{var}>")

# 2. belt and braces: any key=/access_token= query param, whatever its value
text = re.sub(r"([?&](?:key|access_token|client_secret)=)[^\s&\"']+", r"\1<redacted>", text)

r = requests.post(
    f"https://api.github.com/repos/{os.environ['REPO']}/issues",
    headers={
        "Authorization": f"Bearer {os.environ['GH_TOKEN']}",
        "Accept": "application/vnd.github+json",
    },
    json={"title": f"run log {os.environ['RUNID']}", "body": f"```\n{text}\n```"},
    timeout=60,
)
print("issue:", r.json().get("number", r.text[:300]))
