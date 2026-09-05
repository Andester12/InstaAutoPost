"""
Refresh the long-lived Instagram token and write the new value back into the
repo's Actions Secrets, so the next run picks it up automatically.

A long-lived token can be refreshed once it is >24h old and not yet expired.
Each refresh buys another 60 days. If it ever goes 60 days without a refresh it
expires permanently and you must redo the OAuth flow by hand -- which is the
one thing that would break "set it and forget it". Run this monthly, not on
day 59.

Env vars required:
  IG_TOKEN  current long-lived token
  GH_PAT    fine-grained PAT with "Secrets: read and write" on this repo
  GH_REPO   "username/repo"
"""

import base64
import os
import sys

import requests
from nacl import encoding, public

TIMEOUT = 60


def refresh(token):
    r = requests.get(
        "https://graph.instagram.com/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": token},
        timeout=TIMEOUT,
    )
    if not r.ok:
        raise RuntimeError(f"Refresh failed: {r.status_code} {r.text}")
    data = r.json()
    print(f"New token valid for ~{int(data['expires_in']) // 86400} days")
    return data["access_token"]


def update_secret(repo, pat, name, value):
    headers = {
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    key = requests.get(
        f"https://api.github.com/repos/{repo}/actions/secrets/public-key",
        headers=headers,
        timeout=TIMEOUT,
    )
    key.raise_for_status()
    key = key.json()

    sealed = public.SealedBox(
        public.PublicKey(key["key"].encode(), encoding.Base64Encoder())
    ).encrypt(value.encode())

    r = requests.put(
        f"https://api.github.com/repos/{repo}/actions/secrets/{name}",
        headers=headers,
        json={
            "encrypted_value": base64.b64encode(sealed).decode(),
            "key_id": key["key_id"],
        },
        timeout=TIMEOUT,
    )
    if r.status_code not in (201, 204):
        raise RuntimeError(f"Secret update failed: {r.status_code} {r.text}")


def main():
    new_token = refresh(os.environ["IG_TOKEN"])
    update_secret(os.environ["GH_REPO"], os.environ["GH_PAT"], "IG_TOKEN", new_token)
    print("IG_TOKEN secret updated.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("FAILED:", e, file=sys.stderr)
        sys.exit(1)
