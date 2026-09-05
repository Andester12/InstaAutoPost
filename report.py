"""Setup-time diagnostics: post the run log to the repo's issues.

Exists because the GitHub Actions log blob host is unreachable from the
environment this was configured in. Safe to delete once the bot is trusted.
"""
import json
import os
import pathlib

import requests

log = pathlib.Path("debug/last_run.log")
text = log.read_text()[-55000:] if log.exists() else "(no log file produced)"

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
