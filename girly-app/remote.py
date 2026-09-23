"""Optional off-box copy of the store.

Render's free plan cannot attach a persistent disk, so `data/girly.json` is thrown
away on every deploy, restart and idle spin-down. When that happens `Store.load`
finds no users and re-seeds the demo accounts — which is why an account registered
on the live site vanishes and its next sign-in fails with "incorrect email or
password" even though the password is right.

Setting `GIRLY_REMOTE_URL` (and `GIRLY_REMOTE_TOKEN`) keeps the durable copy in a
hosted key-value store instead, and restores from it at boot. Upstash Redis is the
intended backend: its REST API is plain HTTPS with a Bearer token, so this stays
standard library only, like the rest of the app.

Unset, every function here is a no-op and the app behaves exactly as it did before.
"""

import json
import os
import urllib.error
import urllib.request

KEY = "girly:store"  # one key holds the whole store
TIMEOUT = 10

# Upstash rejects bodies over 10 MB. Refuse well before that so a store that
# somehow grows too large fails once, here, rather than on every single save.
MAX_BYTES = 8 * 1024 * 1024

# What urlopen raises when the network, the host or the response is bad. Kept in
# one place because both directions must treat all of them as "just a failure".
_ERRORS = (urllib.error.HTTPError, urllib.error.URLError, OSError, TimeoutError, ValueError)


def configured():
    """True when a remote copy is set up. Everything else keys off this."""
    return bool(os.environ.get("GIRLY_REMOTE_URL"))


def _post(command):
    """Run one Redis command over the REST API."""
    req = urllib.request.Request(
        os.environ["GIRLY_REMOTE_URL"],
        data=json.dumps(command).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + os.environ.get("GIRLY_REMOTE_TOKEN", ""),
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def pull():
    """Fetch the stored copy as `(data, ok)`.

    `ok` is False only when the request itself failed, which is deliberately not
    the same as "nothing is stored yet". The caller needs that distinction: a
    read we could not complete must not be mistaken for an empty store, or the
    seed this boot writes would overwrite a copy that was merely unreachable.
    """
    if not configured():
        return None, True
    try:
        body = _post(["GET", KEY])
    except _ERRORS:
        return None, False
    raw = body.get("result") if isinstance(body, dict) else None
    if not raw:
        return None, True  # genuinely nothing stored yet
    try:
        data = json.loads(raw)
    except ValueError:
        return None, False  # stored value is not the JSON we wrote
    return (data, True) if isinstance(data, dict) else (None, False)


def push(payload_json):
    """Mirror the store. Best-effort — a failed mirror must never fail a request.

    Takes the already-serialised store rather than a dict so the caller can do the
    encoding while it still holds the store lock (see `Store._snapshot`).
    """
    if not configured():
        return True
    if len(payload_json.encode("utf-8")) > MAX_BYTES:
        print("[girly] store is too large to mirror — skipping this push")
        return False
    try:
        _post(["SET", KEY, payload_json])
        return True
    except _ERRORS:
        return False
