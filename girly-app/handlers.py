"""Girly 🌸 — REST API (auth, logs, predictions, admin, chat proxy).

Python port of handlers.go. The App class holds all endpoint logic; the HTTP
plumbing (routing, static files) lives in server.py.
"""

import base64
import json
import os
import re
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from http.cookies import SimpleCookie

from auth import hash_password, password_policy_error, random_token, verify_password
from cycle import build_calendar, compute_cycle, parse_date, parse_month, today_str
from mailer import load_smtp_config, send_reset_email
from store import day_log

SESSION_COOKIE = "girly_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 30  # 30 days
BODY_LIMIT = 1 << 20  # 1 MiB

VALID_FLOW = {"spotting", "light", "medium", "heavy"}


class ApiError(Exception):
    """Raise anywhere in a handler to short-circuit into a JSON error reply."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def public_user(u):
    return {
        "id": u.get("id", ""),
        "name": u.get("name", ""),
        "email": u.get("email", ""),
        "mode": u.get("mode", ""),
        "role": u.get("role", ""),
        "period_length": u.get("period_length", 0),
        "created_at": u.get("created_at", ""),
        "avatar": u.get("avatar", ""),
    }


# Who may open the admin console. There is no account-creation path for admins —
# the role follows the address, so an ordinary signup with this email becomes the
# operator. Overridable so a fork doesn't have to edit code.
DEFAULT_ADMIN_EMAIL = "edachejohnekoja@gmail.com"


def admin_emails():
    """The admin addresses, lowercased. Comma-separated, so a fork can name several."""
    raw = os.environ.get("GIRLY_ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL)
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def role_for_email(email):
    """The role a signup with this address gets. Note the app does not verify
    email addresses, so this is first-come-first-served."""
    return "admin" if (email or "").strip().lower() in admin_emails() else "user"


# data:image/png;base64,…. — the profile picture is stored inline in the user
# record (the frontend resizes uploads to a 256px JPEG before sending).
AVATAR_DATA_URL = re.compile(r"^data:image/(png|jpeg|gif|webp);base64,([A-Za-z0-9+/=]+)$")
AVATAR_MAX_BYTES = 512 * 1024  # 512 KiB decoded

# Chat attachments: photos and documents uploaded to the store.
ATTACHMENT_TYPES = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "application/pdf",
    "text/plain",
    "text/markdown",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
ATTACHMENT_MAX_BYTES = 4 * 1024 * 1024  # 4 MiB decoded
ATTACHMENT_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class App:
    def __init__(self, store, assistant_url, data_dir):
        self.store = store
        self.assistant_url = assistant_url
        self.data_dir = data_dir  # for optional smtp.json / llm_key.txt

    # ---- Session helpers ----

    def current_user(self, headers):
        cookie = SimpleCookie()
        cookie.load(headers.get("Cookie", ""))
        morsel = cookie.get(SESSION_COOKIE)
        if morsel is None or not morsel.value:
            return None
        return self.store.user_for_token(morsel.value)

    def _session_cookie(self, token, max_age):
        return (
            f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={max_age}"
        )

    def set_session(self, user_id):
        token = random_token(24)
        self.store.create_session(token, user_id)
        return self._session_cookie(token, SESSION_MAX_AGE)

    def clear_session(self, headers):
        cookie = SimpleCookie()
        cookie.load(headers.get("Cookie", ""))
        morsel = cookie.get(SESSION_COOKIE)
        if morsel is not None and morsel.value:
            if self.store.user_for_token(morsel.value):
                self.store.revoke_session_by_token(morsel.value)
        return self._session_cookie("", 0)

    def require_user(self, headers):
        u = self.current_user(headers)
        if u is None:
            raise ApiError(401, "not signed in")
        return u

    def require_admin(self, headers):
        u = self.require_user(headers)
        if u.get("role") != "admin":
            raise ApiError(403, "admin access required")
        return u

    # ---- Auth ----

    def api_register(self, body, query, headers):
        name = (body.get("name") or "").strip()
        email = (body.get("email") or "").strip().lower()
        password = body.get("password") or ""
        if not name or not email or len(password) < 8:
            raise ApiError(
                400, "name, email and a password of at least 8 characters are required"
            )
        policy = password_policy_error(password)
        if policy:
            raise ApiError(400, policy)
        if self.store.user_by_email(email):
            raise ApiError(409, "an account with that email already exists")

        # Validate the date of birth: a real date, age 8–120.
        dob = parse_date(body.get("dob") or "")
        if dob is None:
            raise ApiError(400, "please provide a valid date of birth")
        age = date.today().year - dob.year
        if age < 8 or age > 120:
            raise ApiError(400, "date of birth must give an age between 8 and 120")

        u = {
            "name": name,
            "email": email,
            "dob": body.get("dob", ""),
            "bio_sex": body.get("bio_sex", ""),
            "mode": "learn",
            "role": role_for_email(email),
            "period_length": body.get("period_length") or 5,
            "period_starts": [],
            "logs": [],
            "created_at": today_str(),
        }
        if body.get("period_status") == "started":
            u["mode"] = "tracking"
            if parse_date(body.get("last_period_date") or ""):
                u["period_starts"] = [body["last_period_date"]]
        u["salt"] = random_token(16)
        u["password_hash"] = hash_password(password, u["salt"])
        self.store.add_user(u)
        self.store.log_audit(u["email"], "register", f"New account created ({u['mode']} mode)")
        cookie = self.set_session(u["id"])
        return 201, public_user(u), [("Set-Cookie", cookie)]

    def api_login(self, body, query, headers):
        email = (body.get("email") or "").strip().lower()
        u = self.store.user_by_email(email)
        if u is None or not verify_password(
            body.get("password") or "", u.get("salt", ""), u.get("password_hash", "")
        ):
            raise ApiError(401, "incorrect email or password")

        # The address is what grants the console, so signing in also repairs the
        # stored role: an account registered before this rule existed is promoted,
        # and one whose address has since been dropped from GIRLY_ADMIN_EMAIL is
        # demoted. Either way the env var stays the source of truth.
        want = role_for_email(u.get("email", ""))
        if want != u.get("role"):

            def fn(x):
                x["role"] = want

            self.store.update_user(u["id"], fn)

        cookie = self.set_session(u["id"])
        self.store.log_audit(u["email"], "login", "Session opened")
        return 200, public_user(u), [("Set-Cookie", cookie)]

    def api_logout(self, body, query, headers):
        cookie = self.clear_session(headers)
        return 200, {"ok": True}, [("Set-Cookie", cookie)]

    def api_me(self, body, query, headers):
        u = self.require_user(headers)
        return 200, {"user": public_user(u), "cycle": compute_cycle(u)}, []

    def _session_token(self, headers):
        cookie = SimpleCookie()
        cookie.load(headers.get("Cookie", ""))
        morsel = cookie.get(SESSION_COOKIE)
        return morsel.value if morsel is not None else ""

    # ---- Profile ----

    def api_profile_avatar(self, body, query, headers):
        """Set (or clear) the signed-in user's profile picture. The body carries
        a data:image/...;base64 URL produced by the frontend's resizer; an
        empty string removes the picture."""
        u = self.require_user(headers)
        avatar = body.get("avatar", "")
        if avatar:
            m = AVATAR_DATA_URL.match(avatar)
            if not m:
                raise ApiError(400, "avatar must be a data URL (png, jpeg, gif, or webp)")
            try:
                decoded = base64.b64decode(m.group(2))
            except (ValueError, TypeError):
                raise ApiError(400, "avatar must be a data URL (png, jpeg, gif, or webp)")
            if len(decoded) > AVATAR_MAX_BYTES:
                raise ApiError(400, "that picture is too large — please try a smaller one")
        self.store.update_user(u["id"], lambda us: us.update(avatar=avatar))
        self.store.log_audit(
            u["email"], "avatar_change", "Profile picture " + ("updated" if avatar else "removed")
        )
        return 200, {"ok": True, "avatar": avatar}, []

    def api_profile_password(self, body, query, headers):
        """Change the signed-in user's password. Other sessions are revoked;
        the device making the change stays signed in."""
        u = self.require_user(headers)
        current = body.get("current_password") or ""
        new = body.get("new_password") or ""
        if not verify_password(current, u.get("salt", ""), u.get("password_hash", "")):
            raise ApiError(401, "your current password is incorrect")
        if len(new) < 8:
            raise ApiError(400, "the new password must be at least 8 characters")
        policy = password_policy_error(new)
        if policy:
            raise ApiError(400, "the " + policy)

        salt = random_token(16)
        pw_hash = hash_password(new, salt)

        def fn(usr):
            usr["salt"] = salt
            usr["password_hash"] = pw_hash

        self.store.update_user(u["id"], fn)
        self.store.revoke_sessions_except(u["id"], self._session_token(headers))
        self.store.log_audit(u["email"], "password_change", "Password changed by user")
        return 200, {"ok": True}, []

    # ---- Chat attachments ----

    def api_attachments(self, body, query, headers):
        """Store an uploaded photo/document for the signed-in user and return
        the metadata (plus the URL it's served from) for the chat bubble."""
        u = self.require_user(headers)
        name = (body.get("name") or "file").strip()[:120]
        content_type = body.get("content_type") or ""
        data_b64 = body.get("data") or ""
        if content_type not in ATTACHMENT_TYPES:
            raise ApiError(400, "attachments can be photos (png, jpeg, gif, webp) or documents (pdf, txt, md, doc, docx)")
        try:
            raw = base64.b64decode(data_b64)
        except (ValueError, TypeError):
            raise ApiError(400, "invalid file data")
        if not raw:
            raise ApiError(400, "the file is empty")
        if len(raw) > ATTACHMENT_MAX_BYTES:
            raise ApiError(400, "files must be 4 MB or smaller")

        safe_name = ATTACHMENT_SAFE_NAME.sub("_", name) or "file"
        fname = f"{random_token(8)}_{safe_name}"
        dir_path = os.path.join(self.data_dir, "attachments", u["id"])
        os.makedirs(dir_path, exist_ok=True)
        with open(os.path.join(dir_path, fname), "wb") as f:
            f.write(raw)

        attachment = {
            "name": name,
            "type": content_type,
            "size": len(raw),
            "url": f"/api/attachments/{u['id']}/{fname}",
        }
        self.store.log_audit(u["email"], "attachment", f"Uploaded '{name}' for the assistant")
        return 201, {"ok": True, "attachment": attachment}, []

    # ---- Logging ----

    def api_logs(self, body, query, headers):
        u = self.require_user(headers)
        log_date = body.get("date") or today_str()
        if parse_date(log_date) is None:
            raise ApiError(400, "invalid date")
        flow = body.get("flow") or ""
        if flow and flow not in VALID_FLOW:
            raise ApiError(400, "flow must be spotting, light, medium or heavy")
        entry = day_log(
            log_date,
            flow=flow,
            moods=body.get("moods") or [],
            symptoms=body.get("symptoms") or [],
            note=body.get("note") or "",
        )
        self.store.upsert_log(u["id"], entry)
        return 201, {"ok": True}, []

    def api_period(self, body, query, headers):
        u = self.require_user(headers)
        log_date = body.get("date") or today_str()
        if parse_date(log_date) is None:
            raise ApiError(400, "invalid date")
        self.store.add_period_start(u["id"], log_date)
        flow = body.get("flow") or ""
        self.store.upsert_log(u["id"], day_log(log_date, flow=flow if flow in VALID_FLOW else ""))
        self.store.log_audit(u["email"], "log_period", f"Period start recorded for {log_date}")
        return 201, {"ok": True}, []

    def api_mode(self, body, query, headers):
        u = self.require_user(headers)
        mode = body.get("mode") or ""
        if mode not in ("tracking", "learn"):
            raise ApiError(400, "mode must be tracking or learn")
        if mode == "tracking":
            log_date = body.get("last_period_date") or today_str()
            self.store.add_period_start(u["id"], log_date)
        else:
            self.store.update_user(u["id"], lambda us: us.update(mode="learn"))
        self.store.log_audit(u["email"], "mode_switch", f"Switched to {mode} mode")
        updated = self.store.user_by_id(u["id"]) or u
        return 200, public_user(updated), []

    # ---- Dashboard / calendar ----

    def _month_from_query(self, query):
        month = date.today()
        m = query.get("month", [""])[0]
        if m:
            parsed = parse_month(m)
            if parsed:
                month = parsed
        return month

    def api_dashboard(self, body, query, headers):
        u = self.require_user(headers)
        month = self._month_from_query(query)
        summary = compute_cycle(u)
        return (
            200,
            {
                "user": public_user(u),
                "cycle": summary,
                "calendar": build_calendar(u, summary, month),
                "month": month.strftime("%Y-%m"),
                "logs": u.get("logs") or [],
            },
            [],
        )

    def api_calendar(self, body, query, headers):
        u = self.require_user(headers)
        month = self._month_from_query(query)
        return (
            200,
            {
                "calendar": build_calendar(u, compute_cycle(u), month),
                "month": month.strftime("%Y-%m"),
            },
            [],
        )

    # ---- Chat (proxied to the Python companion service) ----

    def api_chat(self, body, query, headers):
        u = self.require_user(headers)
        message = (body.get("message") or "").strip()
        if not message:
            raise ApiError(400, "message is required")

        summary = compute_cycle(u)
        attachments = [
            {
                "name": str(a.get("name", "file"))[:120],
                "url": str(a.get("url", "")),
                "type": str(a.get("type", "")),
            }
            for a in (body.get("attachments") or [])[:5]
            if isinstance(a, dict)
        ]
        payload = json.dumps(
            {
                "message": message,
                "context": {
                    "name": u.get("name", ""),
                    "mode": u.get("mode", ""),
                    "cycle_day": summary["cycle_day"],
                    "phase": summary["phase"],
                    "phase_label": summary["phase_label"],
                    "days_until_period": summary["days_until_period"],
                    "next_period_date": summary["next_period_date"],
                    "attachments": attachments,
                },
            }
        ).encode("utf-8")

        req = urllib.request.Request(
            self.assistant_url + "/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                status = resp.status
                reply = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            status = err.code
            try:
                reply = json.loads(err.read().decode("utf-8"))
            except (ValueError, OSError):
                reply = {"error": "companion service error"}
        except (urllib.error.URLError, OSError, TimeoutError):
            raise ApiError(
                502, "the companion service is unreachable — is assistant/server.py running?"
            )

        # Only a real answer is worth remembering. A companion error is not an
        # answer, and storing it would replay it as one.
        if 200 <= status < 300:
            answer = reply if isinstance(reply, dict) else {}
            self.store.append_chat(
                u["id"],
                {
                    "time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "question": message,
                    "attachments": attachments,
                    "reply": answer.get("reply", ""),
                    "tips": answer.get("tips") or [],
                    "doctor": bool(answer.get("doctor")),
                },
            )
        return status, reply, []

    def api_chat_history(self, body, query, headers):
        """Everything said so far between this user and the companion."""
        u = self.require_user(headers)
        return 200, {"turns": u.get("chats") or []}, []

    def api_chat_clear(self, body, query, headers):
        u = self.require_user(headers)
        self.store.clear_chats(u["id"])
        self.store.log_audit(u["email"], "chat", "Cleared their companion conversation")
        return 200, {"ok": True}, []

    # ---- Admin ----

    def _assistant_up(self):
        try:
            with urllib.request.urlopen(self.assistant_url + "/health", timeout=5) as resp:
                return resp.status == 200
        except (urllib.error.URLError, OSError, TimeoutError):
            return False

    def api_admin_stats(self, body, query, headers):
        self.require_admin(headers)
        with self.store.mu:
            registered = len(self.store.users)
            sessions = len(self.store.sessions)
            learn = sum(1 for u in self.store.users if u.get("mode") == "learn")
            tracking = registered - learn

        # Ask the Python companion for its health, mirroring the admin
        # "System Health" panel.
        python_up = self._assistant_up()

        return (
            200,
            {
                "registered": registered,
                "active_sessions": sessions,
                "learn_mode": learn,
                "tracking_mode": tracking,
                "registered_today": 0,
                "services": [
                    {
                        "name": "Python API Server",
                        "detail": "girly-app · stdlib http.server · port 8080",
                        "status": "running",
                    },
                    {
                        "name": "Python Companion Service",
                        "detail": "assistant/server.py · port 3000",
                        "status": "running" if python_up else "offline",
                    },
                    {
                        "name": "JSON Persistent Store",
                        "detail": "data/girly.json · PBKDF2 credentials",
                        "status": "running",
                    },
                ],
                "python_up": python_up,
            },
            [],
        )

    def api_admin_users(self, body, query, headers):
        self.require_admin(headers)
        with self.store.mu:
            users = [dict(u) for u in self.store.users]
            sessions = list(self.store.sessions)

        session_count = {}
        for sess in sessions:
            session_count[sess.get("user_id")] = (
                session_count.get(sess.get("user_id"), 0) + 1
            )

        out = [
            {
                "id": u.get("id", ""),
                "name": u.get("name", ""),
                "email": u.get("email", ""),
                "mode": u.get("mode", ""),
                "role": u.get("role", ""),
                "active": session_count.get(u.get("id"), 0) > 0,
                "sessions": session_count.get(u.get("id"), 0),
                "created_at": u.get("created_at", ""),
            }
            for u in users
        ]
        return 200, {"users": out}, []

    def _admin_target(self, body):
        target = self.store.user_by_email((body.get("email") or "").strip().lower())
        if target is None:
            raise ApiError(404, "no account with that email")
        return target

    def api_admin_reset(self, body, query, headers):
        admin = self.require_admin(headers)
        target = self._admin_target(body)

        temp = "girly_" + random_token(4)
        salt = random_token(16)
        pw_hash = hash_password(temp, salt)

        def fn(u):
            u["salt"] = salt
            u["password_hash"] = pw_hash

        self.store.update_user(target["id"], fn)
        self.store.revoke_sessions(target["id"])

        # Email the temp password when SMTP is configured; the admin always
        # gets it in the response as a fallback channel.
        emailed = False
        cfg = load_smtp_config(self.data_dir)
        if cfg is not None:
            err = send_reset_email(cfg, target["email"], temp)
            if err is None:
                emailed = True
            else:
                print(f"[girly] reset email to {target['email']} failed: {err}")

        self.store.log_audit(
            admin["email"],
            "password_reset",
            "Temporary password dispatched for "
            + target["email"]
            + (" (emailed)" if emailed else " (shown to admin)"),
        )
        return 200, {"ok": True, "temp_password": temp, "emailed": emailed}, []

    def api_admin_revoke(self, body, query, headers):
        admin = self.require_admin(headers)
        target = self._admin_target(body)
        self.store.revoke_sessions(target["id"])
        self.store.log_audit(
            admin["email"], "revoke_sessions", f"All sessions revoked for {target['email']}"
        )
        return 200, {"ok": True}, []

    def api_admin_delete(self, body, query, headers):
        admin = self.require_admin(headers)
        target = self._admin_target(body)
        if target["id"] == admin["id"]:
            raise ApiError(400, "you cannot delete your own admin account")
        self.store.delete_user(target["id"])
        self.store.log_audit(
            admin["email"], "delete_account", f"Identity record purged for {target['email']}"
        )
        return 200, {"ok": True}, []

    def api_admin_audit(self, body, query, headers):
        self.require_admin(headers)
        with self.store.mu:
            entries = list(reversed(self.store.audit))  # newest first
        return 200, {"audit": entries}, []

    def api_admin_telemetry(self, body, query, headers):
        """Exports aggregate counts only — no health data, ever."""
        self.require_admin(headers)
        with self.store.mu:
            registered = len(self.store.users)
            sessions = len(self.store.sessions)
            learn = sum(1 for u in self.store.users if u.get("mode") == "learn")
            tracking = registered - learn
        return (
            200,
            {
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "registered": registered,
                "active_sessions": sessions,
                "tracking_mode": tracking,
                "learn_mode": learn,
                "privacy_audit": "Counts only. No cycle, symptom, or chat data included.",
            },
            [],
        )
