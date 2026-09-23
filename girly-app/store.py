"""Girly 🌸 — JSON persistence, models, and demo seed data.

Python port of store.go. Users, sessions, and audit entries are plain dicts
with exactly the same JSON keys the Go version wrote, so an existing
data/girly.json keeps working unchanged.
"""

import json
import os
import threading
import time
from datetime import date, datetime, timedelta, timezone

import remote
from auth import hash_password, random_token
from cycle import today_str

AUDIT_LIMIT = 100
CHAT_LIMIT = 100  # companion turns kept per user, newest wins

# How long the mirror worker waits for a burst of saves to settle before pushing
# one combined copy, and how many times it retries a failed push. One request can
# save three times over (register: add_user + log_audit + create_session), so
# coalescing is what keeps this inside a free tier's command allowance.
REMOTE_FLUSH_DELAY = 1.5
REMOTE_RETRIES = 3


def _read_local(path):
    """The on-disk store, or None if there isn't a usable one."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def day_log(date, flow="", moods=None, symptoms=None, note=""):
    """Build a log entry dict, dropping empty fields (Go's omitempty)."""
    entry = {"date": date}
    if flow:
        entry["flow"] = flow
    if moods:
        entry["moods"] = list(moods)
    if symptoms:
        entry["symptoms"] = list(symptoms)
    if note:
        entry["note"] = note
    return entry


def _merge_unique(a, b):
    out = list(a)
    for v in b:
        if v not in out:
            out.append(v)
    return out


def _now_rfc3339():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Store:
    def __init__(self, path):
        self.mu = threading.Lock()
        self.path = path
        self.users = []
        self.sessions = []
        self.audit = []
        self.next_id = 1
        # Remote mirroring. `_push_allowed` starts False and is only ever set by a
        # boot pull that actually succeeded — see load().
        self._push_allowed = False
        self._dirty = threading.Event()
        self._sync_lock = threading.Lock()
        self._worker = None

    # ---- Persistence ----

    @classmethod
    def load(cls, path):
        s = cls(path)
        data = None
        adopted = False

        if remote.configured():
            # The remote copy is the durable one; the local file is a per-container
            # cache that Render throws away. Read the remote first, and record
            # whether that read *worked* — a failure here must not be mistaken for
            # "nothing stored", or this boot's seed would overwrite a good copy
            # that was merely unreachable.
            data, ok = remote.pull()
            s._push_allowed = ok
            adopted = bool(data and data.get("users"))
            if not adopted:
                data = None

        if data is None:
            data = _read_local(path)

        if data:
            s.users = data.get("users", [])
            s.sessions = data.get("sessions", [])
            s.audit = data.get("audit", [])

        for u in s.users:
            try:
                s.next_id = max(s.next_id, int(u.get("id", 0)) + 1)
            except ValueError:
                pass
        if not s.users:
            s._seed()
            s.save()
        elif adopted:
            s._write_local()  # refresh the cache from the durable copy

        if remote.configured():
            s._start_sync()
        return s

    def save(self):
        self._write_local()
        if self._push_allowed:
            self._dirty.set()

    def _write_local(self):
        data = {"users": self.users, "sessions": self.sessions, "audit": self.audit}
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)

    # ---- Remote mirror ----
    #
    # Pushing has to happen off the request thread. Every mutating method below
    # calls save() *while holding self.mu*, so a network call inside save() would
    # hold the app's only lock across a ten-second timeout and freeze everything.
    # One worker thread, fed by an Event, keeps pushes off the lock and serialises
    # them so the newest copy always lands last.

    def _start_sync(self):
        with self._sync_lock:
            if self._worker is None:
                self._worker = threading.Thread(
                    target=self._sync_loop, daemon=True, name="girly-remote"
                )
                self._worker.start()

    def _snapshot(self):
        """Serialise under the lock. Handing the worker live lists would let a
        concurrent write mutate them mid-encode."""
        with self.mu:
            return json.dumps(
                {"users": self.users, "sessions": self.sessions, "audit": self.audit},
                ensure_ascii=False,
            )

    def _sync_loop(self):
        while True:
            self._dirty.wait()
            time.sleep(REMOTE_FLUSH_DELAY)  # let a burst collapse into one push
            self._dirty.clear()
            for attempt in range(REMOTE_RETRIES):
                if remote.push(self._snapshot()):
                    break
                time.sleep(2**attempt)
            else:
                print("[girly] could not mirror the store to the remote copy")

    # ---- Mutations (all lock internally) ----

    def add_user(self, user):
        with self.mu:
            user["id"] = str(self.next_id)
            self.next_id += 1
            self.users.append(user)
            return self.save()

    def user_by_email(self, email):
        with self.mu:
            for u in self.users:
                if u.get("email") == email:
                    return u
        return None

    def user_by_id(self, id):
        with self.mu:
            for u in self.users:
                if u.get("id") == id:
                    return u
        return None

    def update_user(self, id, fn):
        with self.mu:
            for u in self.users:
                if u.get("id") == id:
                    fn(u)
                    return self.save()
        return None

    def delete_user(self, id):
        with self.mu:
            self.users = [u for u in self.users if u.get("id") != id]
            # drop their sessions too
            self.sessions = [s for s in self.sessions if s.get("user_id") != id]
            return self.save()

    def create_session(self, token, user_id):
        with self.mu:
            self.sessions.append(
                {"token": token, "user_id": user_id, "created_at": today_str()}
            )
            return self.save()

    def user_for_token(self, token):
        with self.mu:
            for sess in self.sessions:
                if sess.get("token") == token:
                    for u in self.users:
                        if u.get("id") == sess.get("user_id"):
                            return u
        return None

    def revoke_sessions(self, user_id):
        with self.mu:
            self.sessions = [s for s in self.sessions if s.get("user_id") != user_id]
            return self.save()

    def revoke_sessions_except(self, user_id, keep_token):
        """Drop all of a user's sessions except one (used after a password
        change, so the device making the change stays signed in)."""
        with self.mu:
            self.sessions = [
                s
                for s in self.sessions
                if s.get("user_id") != user_id or s.get("token") == keep_token
            ]
            return self.save()

    def revoke_session_by_token(self, token):
        with self.mu:
            self.sessions = [s for s in self.sessions if s.get("token") != token]
            return self.save()

    def count_sessions(self, user_id):
        with self.mu:
            return sum(1 for s in self.sessions if s.get("user_id") == user_id)

    def log_audit(self, actor, action, detail):
        with self.mu:
            self.audit.append(
                {"time": _now_rfc3339(), "actor": actor, "action": action, "detail": detail}
            )
            # keep the most recent 100 entries
            self.audit = self.audit[-AUDIT_LIMIT:]
            self.save()

    # ---- Cycle log helpers ----

    def add_period_start(self, user_id, date_str):
        def fn(u):
            starts = u.setdefault("period_starts", [])
            if date_str not in starts:
                starts.append(date_str)
                starts.sort()
            # new period start implies tracking mode
            u["mode"] = "tracking"

        return self.update_user(user_id, fn)

    def upsert_log(self, user_id, log):
        """Merge a daily log entry with anything already stored for that date."""

        def fn(u):
            logs = u.setdefault("logs", [])
            for existing in logs:
                if existing.get("date") == log["date"]:
                    if log.get("flow"):
                        existing["flow"] = log["flow"]
                    existing["moods"] = _merge_unique(existing.get("moods", []), log.get("moods", []))
                    existing["symptoms"] = _merge_unique(
                        existing.get("symptoms", []), log.get("symptoms", [])
                    )
                    if log.get("note"):
                        existing["note"] = log["note"]
                    return
            logs.append(log)
            logs.sort(key=lambda l: l.get("date", ""))

        return self.update_user(user_id, fn)

    # ---- Companion chat history ----
    #
    # One dict per exchange, so trimming can never separate a question from the
    # answer it got. Stored on the user record; a file written before this
    # existed simply has no "chats" key, which every reader tolerates.

    def append_chat(self, user_id, turn):
        def fn(u):
            chats = u.setdefault("chats", [])
            chats.append(turn)
            del chats[:-CHAT_LIMIT]  # keep the newest CHAT_LIMIT turns

        return self.update_user(user_id, fn)

    def clear_chats(self, user_id):
        def fn(u):
            u["chats"] = []

        return self.update_user(user_id, fn)

    # ---- Seed ----

    def _seed(self):
        now = date.today()

        def d(days_ago):
            return (now - timedelta(days=days_ago)).strftime("%Y-%m-%d")

        def new_user(name, email, password, dob, bio_sex, mode, role, period_len, starts=None, logs=None):
            salt = random_token(16)
            return {
                "name": name,
                "email": email,
                "salt": salt,
                "password_hash": hash_password(password, salt),
                "dob": dob,
                "bio_sex": bio_sex,
                "mode": mode,
                "role": role,
                "period_length": period_len,
                "period_starts": list(starts or []),
                "logs": list(logs or []),
                "created_at": d(30),
            }

        maya = new_user(
            "Maya Lin", "maya@example.com", "password123", "2005-04-12", "female",
            "tracking", "user", 5,
            [d(80), d(52), d(23)],  # last start 23 days ago → Day 24
            [
                day_log(d(1), moods=["Calm"], symptoms=["Tender breasts"]),
                day_log(d(23), "medium", moods=["Tired"], symptoms=["Cramps"]),
                day_log(d(22), "heavy", symptoms=["Cramps", "Backache"]),
                day_log(d(21), "medium"),
                day_log(d(20), "light"),
                day_log(d(19), "spotting"),
            ],
        )

        chloe = new_user(
            "Chloe Vance", "chloe.v@example.com", "password123", "2012-08-30",
            "prefer_not_to_say", "learn", "user", 5,
        )

        sarah = new_user(
            "Sarah Jenkins", "sarah.j@example.com", "password123", "1998-11-02", "female",
            "tracking", "user", 6,
            [d(64), d(35), d(6)],
            [day_log(d(6), "medium"), day_log(d(5), "heavy")],
        )

        elena = new_user(
            "Elena Rostova", "elena.r@example.com", "password123", "2001-02-17", "female",
            "tracking", "user", 4,
            [d(75), d(47), d(19)],
            [day_log(d(19), "light")],
        )

        # No seeded operator on purpose. There used to be one — admin@girly.app
        # with a password printed in the README — which meant anyone who found
        # the repo could sign in and reset or delete any account. The admin role
        # now follows the address in GIRLY_ADMIN_EMAIL (see handlers.py), so the
        # console starts empty until that account registers.
        self.users = [maya, chloe, sarah, elena]
        for i, u in enumerate(self.users):
            u["id"] = str(i + 1)
        self.next_id = 5
        self.audit = [
            {
                "time": _now_rfc3339(),
                "actor": "system",
                "action": "seed",
                "detail": "Demo member directory initialised with 4 accounts.",
            }
        ]
