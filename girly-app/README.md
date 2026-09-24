# Girly 🌸 — Menstrual Cycle Tracker

A private, reassuring cycle companion built from the Stitch design export
(`../stitch_girly_menstrual_cycle_tracker/`) with **Python, JavaScript, CSS
and HTML** — no frameworks, no external dependencies (standard library only).

## Quick start

```bash
cd girly-app
python3 server.py
```

Then open **http://localhost:8080**.

The single `server.py` process runs everything: it serves the frontend and
REST API on port 8080 and starts the companion service
(`assistant/server.py`) in a background thread on port 3000.

## The companion (assistant)

The chat answers questions across three areas, all offline by default:

- **Menstrual health** — cycle basics, first periods, cramps, PMS/PMDD, PCOS,
  endometriosis, discharge, infections, pregnancy & contraception, TSS, …
- **General health** — sleep, stress, nutrition, hydration, weight, skin,
  puberty, fever, supplements, …
- **Personal hygiene** — showering, intimate care, body odour, shaving, hair,
  dental, feet, nails, handwashing, …

Plain greetings ("hi", "hello") get a simple hello back — no extra info
attached. Everything else goes to Gemini, so the companion can answer
questions no keyword list anticipated:

```bash
export GEMINI_API_KEY=AIza...    # https://aistudio.google.com/apikey (free tier)
python3 server.py
```

Provider selection, in order:

1. `GIRLY_AI_PROVIDER` — `gemini` or `anthropic`, if you want to be explicit
2. `GEMINI_API_KEY` → Gemini (default `gemini-3.1-flash-lite`)
3. `ANTHROPIC_API_KEY` → Anthropic (default `claude-sonnet-5`)
4. `GIRLY_AI_API_KEY` → whichever `GIRLY_AI_PROVIDER` names, else Gemini

The default is Flash-**Lite**, not full Flash. On the free tier the full Flash
line is heavily 503-saturated — `gemini-2.5-flash` now 404s outright for new keys
(*"no longer available to new users"*) and every current `*-flash` variant
measured 0–2 successes out of 3, one taking 27.6s. Flash-Lite answered 3/3 at
under 2s, and ~4s with the real system prompt and JSON mode. If you have billing
enabled, raise it with `GIRLY_AI_MODEL=gemini-3.6-flash`.

`GIRLY_AI_MODEL` overrides the model and `GIRLY_AI_API_URL` the endpoint
(the Gemini URL takes a `{model}` placeholder). Deploying on Render? Set the
key under the service's **Environment** tab.

The built-in topic bank is not dead weight — it's the fallback, and it's
load-bearing in three places:

- **Crisis and urgent-care topics** (self-harm, disordered eating, toxic shock
  syndrome, possible pregnancy) are answered from the bank *before* the AI is
  consulted, so they stay deterministic, work with no network, and never get
  improvised.
- **Offline** — with no key, or when the network is down, the bank answers.
- **Safety blocks** — Gemini may decline a legitimate sexual-health question.
  When it does, the request falls through to the bank rather than going silent.

With no key the companion stays fully offline and answers from the built-in
topics only. With a key, the user's question and minimal cycle context (day
and phase — never names or logs) are sent to the AI service.

## Demo accounts

| Email | Password | Notes |
|---|---|---|
| `maya@example.com` | `password123` | Tracking mode, 3 cycles of history |
| `chloe.v@example.com` | `password123` | Learn mode (no period yet) |

The admin console has no demo login. The `admin` role follows the address in
`GIRLY_ADMIN_EMAIL` (default `edachejohnekoja@gmail.com`), so registering that
address is what creates the operator account.

## What's inside

```
girly-app/
├── server.py             # entrypoint: routing + static serving + companion thread
├── store.py              # JSON persistence, models, demo seed
├── remote.py             # optional off-box copy of the store (see below)
├── auth.py               # PBKDF2-SHA256 password hashing, session tokens
├── handlers.py           # REST API (auth, logs, predictions, admin, chat proxy)
├── cycle.py              # cycle-day / phase / fertile-window prediction math
├── mailer.py             # optional SMTP for admin password resets
├── test_cycle.py         # prediction & store tests (python -m unittest)
├── test_assistant.py     # companion knowledge base & AI-layer tests
├── assistant/
│   └── server.py         # Python companion (knowledge base, optional AI layer, /health)
├── web/
│   ├── index.html        # registration & onboarding + sign-in
│   ├── tracker.html      # cycle ring, stats, phase calendar, quick-log sheets
│   ├── learn.html        # education modules, first-period prep, ask bar
│   ├── assistant.html    # chat with the companion
│   ├── profile.html      # profile picture, cover photo, change password, sign out
│   ├── admin.html        # stats bento, system health, member directory, audit
│   ├── css/girly.css     # design system (tokens, pills, cards, dark mode)
│   ├── js/*.js           # vanilla JS per page + shared helpers
│   └── assets/logo.svg
├── data/girly.json       # created & seeded automatically on first run
└── PROGRESS.md           # build progress tracker
```

## How predictions work

- Girly averages the gaps between your logged period starts (clamped to
  21–45 days; falls back to 28) → **average cycle length**
- Your current **cycle day** counts from your latest logged start
- **Next period** = latest start + average cycle length, shown with a ±2 day
  prediction window on the calendar
- **Ovulation** ≈ 14 days before the projected next period; the **fertile
  window** spans the 5 days before that plus ovulation day

## Where the data lives

Accounts, cycle logs and companion chats live in one JSON store — locally that is
`data/girly.json`. On a host that throws its filesystem away after every deploy,
restart and idle spin-down (Render's free plan, for instance) that file does not
survive, and **every registered account is erased**: the next sign-in fails with
"incorrect email or password" because the account is gone, not because the
password is wrong.

Set these two to keep the durable copy in a hosted key-value store instead:

| Variable | |
|---|---|
| `GIRLY_REMOTE_URL` | REST endpoint of an [Upstash](https://upstash.com) Redis database |
| `GIRLY_REMOTE_TOKEN` | that database's token |

The store is restored from it at boot and mirrored to it after each change —
coalesced, so a burst of writes costs one request rather than one per write. A
push that fails never fails the user's request, and if the boot read fails the app
keeps working locally but **refuses to mirror**, so a seed can't land on top of a
copy it simply couldn't reach. With both variables unset nothing leaves the
machine, which is how local development runs.

Uploaded attachments are *not* mirrored — they stay on the local disk and are lost
with it.

Passwords are hashed with PBKDF2-SHA256 (12,000 iterations). Sessions are HttpOnly
cookies. Delete the data file + restart to reset everything.

*Girly gives estimates based on learned cycle patterns and is not medical
advice.*
