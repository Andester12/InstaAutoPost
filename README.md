# Zero-touch AI Instagram poster

Posts one AI-generated image + caption per day. Free: GitHub Actions (compute),
Pollinations (images), Gemini free tier (text), Instagram Graph API (publishing).

After setup you never log in again. The token renews itself monthly.

---

## Setup checklist

Tick these in order. Nothing later works if something earlier is skipped.

### A. Instagram side

- [ ] **A1.** Instagram account switched to **Professional** (Business or Creator).
      Settings → Account type and tools → Switch to professional account.
      Personal accounts cannot use the publishing API at all.
- [ ] **A2.** Decide your path. This repo uses **Instagram API with Instagram Login**
      (`graph.instagram.com`), which does *not* require a Facebook Page. If your
      account is already tied to a Facebook Page and you'd rather use that path,
      the endpoints change to `graph.facebook.com` and you also need Page
      Publishing Authorization completed.

### B. Meta developer app  [DONE]

- [x] **B1.** Account at `developers.facebook.com`.
- [x] **B2.** App created with use case **"Manage messaging and content on Instagram"**.
- [x] **B3.** Left menu -> **API setup with Instagram Login** (not Facebook Login;
      only one setup is allowed per app).
- [x] **B4.** App left in **Development mode**. App Review is only needed to post
      on behalf of *other people's* accounts, not your own.
- [ ] **B5.** VERIFY: permission `instagram_business_content_publish` is added.
      "Add all required permissions" only gives you `instagram_business_basic`
      and `instagram_business_manage_messages`. Publishing is NOT in that set and
      must be added by hand. Missing it is the single most common first-run
      failure.
- [ ] **B6.** Use the **Instagram app ID / Instagram app secret** from this page,
      NOT the App ID / App Secret on Settings -> Basic. They are different values
      and the wrong pair authenticates fine, then fails on every Instagram call.

Webhooks and Business login settings / redirect URLs are not needed for posting.
Skip both.

### C. Get the long-lived token

The **Generate access tokens -> Add account** button in the dashboard replaces
the manual OAuth authorize-URL flow. If you used it, you already have a token --
but it is short-lived. Exchange it now:

- [ ] **C1.** Exchange for a long-lived (60-day, self-refreshing) token:

      curl -X GET "https://graph.instagram.com/access_token\
      ?grant_type=ig_exchange_token\
      &client_secret=<INSTAGRAM_APP_SECRET>\
      &access_token=<DASHBOARD_TOKEN>"

      Save as `IG_TOKEN`.

- [ ] **C2.** Get your account id:

      curl -X GET "https://graph.instagram.com/v21.0/me\
      ?fields=user_id,username\
      &access_token=<LONG_LIVED_TOKEN>"

      Save `user_id` as `IG_USER_ID`.

Note: refreshing does not revoke the old token -- the previous one stays valid
until its own original expiry. To actually kill a token, remove and re-add the
account under Generate access tokens, or regenerate the app secret.

### D. Gemini key

- [ ] **D1.** `aistudio.google.com` → Get API key. Free tier, no card.

### E. GitHub

- [ ] **E1.** Create a **public** repo (public = free unlimited Actions minutes,
      and `raw.githubusercontent.com` serves your images publicly, which the
      Instagram API requires). Secrets stay private even in a public repo.
- [ ] **E2.** Push these files to the `main` branch.
- [ ] **E3.** Create a fine-grained PAT: Settings → Developer settings → Personal
      access tokens → Fine-grained. Scope it to this one repo, permission
      **Secrets: Read and write**. Expiry: max allowed (set a calendar reminder —
      this is the one credential that *cannot* self-renew).
- [ ] **E4.** Repo → Settings → Secrets and variables → Actions → add:
      - `IG_TOKEN` (from C3)
      - `IG_USER_ID` (from C2)
      - `GEMINI_KEY` (from D1)
      - `GH_PAT` (from E3)
- [ ] **E5.** Repo → Settings → Actions → General → Workflow permissions →
      **Read and write permissions**. Without this the image commit fails.
- [ ] **E6.** Edit `config.json` — set your topic and visual style. This is the
      single most important file for whether the account is worth following.

### F. Test before trusting it

- [ ] **F1.** Actions tab → *daily post* → **Run workflow**. Watch the log.
- [ ] **F2.** Confirm the post actually appeared on the account.
- [ ] **F3.** Actions tab → *refresh token* → **Run workflow**. Confirm the log
      says the secret was updated. Do this now, not in 59 days.
- [ ] **F4.** GitHub profile → Settings → Notifications → confirm "Actions:
      failed workflows only" email is on. This is your alarm.

Done. It runs on its own from here.

---

## How it runs

| Workflow | Cron | What it does |
|---|---|---|
| `post.yml` | daily 12:30 UTC | Gemini writes scene + caption → Pollinations renders the image → commit to `posts/` → publish via container + `media_publish` |
| `refresh.yml` | 1st of month | Refreshes the token, re-encrypts it, PUTs it back into `IG_TOKEN` |
| `cleanup.yml` | weekly | Deletes images older than 60 days |

The post job is split into two Python scripts on purpose. Meta fetches your
image from a public URL rather than accepting an upload, so the file has to be
committed and live on `raw.githubusercontent.com` *before* the publish call.

---

## Things that will eventually break it

None of these are code bugs. They're the cost of building on someone else's
platform.

1. **API version sunset.** `v21.0` is hardcoded in `post.py`. Meta ships a new
   version roughly quarterly and supports each for about two years. One-line fix,
   maybe yearly.
2. **Missed refresh window.** A long-lived token that goes 60 days without a
   refresh expires permanently and cannot be refreshed — you'd redo section C.
   The monthly cron gives you a 2x margin; don't stretch it.
3. **PAT expiry.** Fine-grained PATs always expire. Calendar reminder.
4. **Password change or account flag.** Invalidates the token instantly. Redo C.
5. **Rate limit.** Volume is capped in a rolling 24h window. One post a day is
   nowhere near it, but don't crank the cron to hourly.

Realistic expectation: months of genuine zero intervention, then a ten-minute fix
once or twice a year.

## One honest note on the content

The engineering here is the easy part. A fully unattended account posting generic
AI images gets almost no reach, because the algorithm reads low-effort repetitive
content exactly as it looks. The `config.json` topic is what decides whether this
is worth running. Narrow and genuinely useful beats broad and pretty.
