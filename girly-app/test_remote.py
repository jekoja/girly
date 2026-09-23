"""The optional remote copy of the store — run with `python -m unittest test_remote.py`.

The point of these is the failure paths. A remote copy that is merely unreachable
must never be mistaken for an empty one, because the cost of that mistake is the
seed this boot writes landing on top of every real account.
"""

import json
import os
import tempfile
import time
import unittest
import urllib.error
from unittest import mock

import remote
import store
from store import Store

ENV = {"GIRLY_REMOTE_URL": "https://example.upstash.io", "GIRLY_REMOTE_TOKEN": "tok"}


def reply(payload):
    """A urlopen() stand-in: usable as a context manager, like the real one."""
    m = mock.MagicMock()
    m.__enter__.return_value.read.return_value = json.dumps(payload).encode("utf-8")
    return m


class CleanEnv(unittest.TestCase):
    """These tests are about what the env vars do, so start from none of them."""

    def setUp(self):
        self._saved = {
            k: os.environ.pop(k)
            for k in ("GIRLY_REMOTE_URL", "GIRLY_REMOTE_TOKEN")
            if k in os.environ
        }
        self.addCleanup(lambda: os.environ.update(self._saved))


class UnconfiguredTests(CleanEnv):
    def test_nothing_is_configured_without_the_url(self):
        self.assertFalse(remote.configured())
        self.assertEqual(remote.pull(), (None, True))
        self.assertTrue(remote.push("{}"))

    def test_no_request_is_made_at_all(self):
        # The whole module has to vanish when it isn't set up: local development
        # and the deploy both rely on that.
        with mock.patch.object(remote.urllib.request, "urlopen") as u:
            remote.pull()
            remote.push("{}")
        u.assert_not_called()


class PullTests(CleanEnv):
    def test_reads_back_a_stored_store(self):
        with mock.patch.dict(os.environ, ENV), mock.patch.object(
            remote.urllib.request,
            "urlopen",
            return_value=reply({"result": '{"users": [{"id": "1"}]}'}),
        ):
            self.assertEqual(remote.pull(), ({"users": [{"id": "1"}]}, True))

    def test_an_empty_store_is_not_an_error(self):
        with mock.patch.dict(os.environ, ENV), mock.patch.object(
            remote.urllib.request, "urlopen", return_value=reply({"result": None})
        ):
            self.assertEqual(remote.pull(), (None, True))

    def test_a_failed_request_says_so(self):
        failures = [
            urllib.error.URLError("down"),
            urllib.error.HTTPError("https://x", 500, "boom", {}, None),
            TimeoutError(),
            OSError(),
        ]
        for boom in failures:
            with self.subTest(boom=type(boom).__name__):
                with mock.patch.dict(os.environ, ENV), mock.patch.object(
                    remote.urllib.request, "urlopen", side_effect=boom
                ):
                    self.assertEqual(remote.pull(), (None, False))

    def test_unparseable_content_is_a_failure_not_an_empty_store(self):
        # Something stored that isn't the JSON we write is a real problem, and
        # reporting "empty" would invite the next boot to seed over it.
        with mock.patch.dict(os.environ, ENV), mock.patch.object(
            remote.urllib.request, "urlopen", return_value=reply({"result": "not json"})
        ):
            self.assertEqual(remote.pull(), (None, False))

    def test_json_that_is_not_an_object_is_a_failure(self):
        with mock.patch.dict(os.environ, ENV), mock.patch.object(
            remote.urllib.request, "urlopen", return_value=reply({"result": "[1, 2]"})
        ):
            self.assertEqual(remote.pull(), (None, False))


class PushTests(CleanEnv):
    def test_sends_a_set_command_and_reports_success(self):
        with mock.patch.dict(os.environ, ENV), mock.patch.object(
            remote.urllib.request, "urlopen", return_value=reply({"result": "OK"})
        ) as u:
            self.assertTrue(remote.push('{"users": []}'))
        req = u.call_args[0][0]
        self.assertEqual(
            json.loads(req.data.decode("utf-8")), ["SET", remote.KEY, '{"users": []}']
        )
        self.assertEqual(req.get_header("Authorization"), "Bearer tok")

    def test_a_failed_push_returns_false_instead_of_raising(self):
        # A mirror that is down must not fail the user's request.
        for boom in (urllib.error.URLError("down"), TimeoutError(), OSError()):
            with self.subTest(boom=type(boom).__name__):
                with mock.patch.dict(os.environ, ENV), mock.patch.object(
                    remote.urllib.request, "urlopen", side_effect=boom
                ):
                    self.assertFalse(remote.push("{}"))

    def test_an_oversized_store_is_refused_before_it_is_sent(self):
        with mock.patch.dict(os.environ, ENV), mock.patch.object(
            remote, "MAX_BYTES", 10
        ), mock.patch.object(remote.urllib.request, "urlopen") as u:
            self.assertFalse(remote.push("x" * 20))
        u.assert_not_called()


class StoreIntegrationTests(CleanEnv):
    """Store.load is where the two copies are reconciled."""

    def test_a_remote_copy_is_adopted_and_cached_locally(self):
        stored = {
            "users": [{"id": "7", "email": "kept@example.com", "role": "user"}],
            "sessions": [],
            "audit": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "girly.json")
            with mock.patch.dict(os.environ, ENV), mock.patch.object(
                remote, "pull", return_value=(stored, True)
            ), mock.patch.object(remote, "push", return_value=True):
                s = Store.load(path)

            self.assertEqual([u["email"] for u in s.users], ["kept@example.com"])
            self.assertEqual(s.next_id, 8)
            # and the container has a local cache again for the next restart
            with open(path, encoding="utf-8") as f:
                self.assertEqual(json.load(f)["users"][0]["email"], "kept@example.com")

    def test_a_remote_copy_beats_a_stale_local_file(self):
        stale = {"users": [{"id": "1", "email": "stale@example.com", "role": "user"}]}
        fresh = {"users": [{"id": "2", "email": "fresh@example.com", "role": "user"}]}
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "girly.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(stale, f)
            with mock.patch.dict(os.environ, ENV), mock.patch.object(
                remote, "pull", return_value=(fresh, True)
            ), mock.patch.object(remote, "push", return_value=True):
                s = Store.load(path)
        self.assertEqual([u["email"] for u in s.users], ["fresh@example.com"])

    def test_a_failed_boot_pull_never_pushes_over_the_real_copy(self):
        # The regression that matters: the read failed, so we do not know what is
        # up there. Seeding locally is fine; seeding over everyone's accounts is not.
        pushes = []
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, ENV), mock.patch.object(
                remote, "pull", return_value=(None, False)
            ), mock.patch.object(
                remote, "push", side_effect=lambda p: pushes.append(p) or True
            ), mock.patch.object(
                store, "REMOTE_FLUSH_DELAY", 0.05
            ):
                s = Store.load(os.path.join(tmp, "girly.json"))
                self.assertTrue(s.users)  # still seeded, so the app works
                s.log_audit("x", "test", "noise")
                time.sleep(0.4)
        self.assertEqual(pushes, [])

    def test_an_empty_remote_is_seeded_and_then_mirrored(self):
        pushes = []
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, ENV), mock.patch.object(
                remote, "pull", return_value=(None, True)
            ), mock.patch.object(
                remote, "push", side_effect=lambda p: pushes.append(p) or True
            ), mock.patch.object(
                store, "REMOTE_FLUSH_DELAY", 0.05
            ):
                s = Store.load(os.path.join(tmp, "girly.json"))
                self._wait_for(pushes)
        self.assertTrue(pushes, "the seed should have been mirrored")
        self.assertIn("maya@example.com", pushes[0])

    def test_a_burst_of_writes_is_coalesced(self):
        # One register already saves three times over. Pushing per save would
        # spend a free tier's command allowance for no gain.
        pushes = []
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, ENV), mock.patch.object(
                remote, "pull", return_value=(None, True)
            ), mock.patch.object(
                remote, "push", side_effect=lambda p: pushes.append(p) or True
            ), mock.patch.object(
                store, "REMOTE_FLUSH_DELAY", 0.15
            ):
                s = Store.load(os.path.join(tmp, "girly.json"))
                for _ in range(5):
                    s.log_audit("x", "test", "noise")
                self._wait_for(pushes)
                time.sleep(0.5)  # let any straggler pushes land
        self.assertTrue(pushes, "expected at least one push")
        self.assertLess(len(pushes), 5, f"not coalesced: {len(pushes)} pushes for 6 saves")

    @staticmethod
    def _wait_for(pushes, seconds=3.0):
        deadline = time.time() + seconds
        while not pushes and time.time() < deadline:
            time.sleep(0.02)


if __name__ == "__main__":
    unittest.main()
