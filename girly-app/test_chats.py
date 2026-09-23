"""Companion chat history — run with `python -m unittest test_chats.py`."""

import json
import os
import tempfile
import unittest

from store import CHAT_LIMIT, Store


def mk_turn(n):
    """A stored exchange. n keeps questions and answers matched, so a test can
    check that a question never ends up beside someone else's answer."""
    return {
        "time": "2026-09-23T21:00:00Z",
        "question": f"q{n}",
        "attachments": [],
        "reply": f"a{n}",
        "tips": [],
        "doctor": False,
    }


class ChatHistoryTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "girly.json")
        self.store = Store.load(self.path)  # seeds the demo accounts

    def tearDown(self):
        self.dir.cleanup()

    def user(self, n=1):
        return self.store.user_by_id(str(n))

    def test_turns_come_back_in_order(self):
        for i in range(3):
            self.store.append_chat("1", mk_turn(i))
        chats = self.user()["chats"]
        self.assertEqual([c["question"] for c in chats], ["q0", "q1", "q2"])
        self.assertEqual([c["reply"] for c in chats], ["a0", "a1", "a2"])

    def test_history_survives_a_reload(self):
        self.store.append_chat("1", mk_turn(0))
        reloaded = Store.load(self.path)
        self.assertEqual(reloaded.user_by_id("1")["chats"][0]["question"], "q0")

    def test_cap_keeps_the_newest_turns_whole(self):
        for i in range(CHAT_LIMIT + 5):
            self.store.append_chat("1", mk_turn(i))
        chats = self.user()["chats"]
        self.assertEqual(len(chats), CHAT_LIMIT)
        self.assertEqual(chats[0]["question"], "q5")  # oldest five dropped
        self.assertEqual(chats[-1]["question"], f"q{CHAT_LIMIT + 4}")
        # a surviving question still sits beside its own answer
        for c in chats:
            self.assertEqual(c["reply"], "a" + c["question"][1:])

    def test_clearing_only_touches_that_user(self):
        self.store.append_chat("1", mk_turn(0))
        self.store.append_chat("2", mk_turn(0))
        self.store.clear_chats("1")
        self.assertEqual(self.user(1).get("chats"), [])
        self.assertEqual(len(self.user(2)["chats"]), 1)

    def test_a_store_written_before_chat_history_still_works(self):
        # An older girly.json has no "chats" key on any user. Reading must not
        # blow up, and the first append has to create the list.
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)
        for u in data["users"]:
            u.pop("chats", None)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        store = Store.load(self.path)
        self.assertIsNone(store.user_by_id("1").get("chats"))
        store.append_chat("1", mk_turn(0))
        self.assertEqual(len(store.user_by_id("1")["chats"]), 1)

    def test_an_unknown_user_is_a_no_op(self):
        for u in self.store.users:
            self.assertNotEqual(u.get("id"), "999")
        self.assertIsNone(self.store.append_chat("999", mk_turn(0)))
        self.assertIsNone(self.store.clear_chats("999"))


if __name__ == "__main__":
    unittest.main()
