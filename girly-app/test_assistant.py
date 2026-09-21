"""Tests for the companion service's knowledge base and AI layer."""

import json
import os
import unittest
from unittest import mock

import assistant.server as companion

# The companion loads .env at import, so a developer with a real key would
# otherwise have this suite make live API calls. Strip the AI keys for the run;
# tests that want a provider patch it back in themselves.
AI_ENV_VARS = ("GEMINI_API_KEY", "ANTHROPIC_API_KEY", "GIRLY_AI_API_KEY",
               "GIRLY_AI_PROVIDER", "GIRLY_AI_MODEL", "GIRLY_AI_API_URL")
_saved_env = {}


def setUpModule():
    for name in AI_ENV_VARS:
        if name in os.environ:
            _saved_env[name] = os.environ.pop(name)


def tearDownModule():
    os.environ.update(_saved_env)


class KnowledgeBaseTests(unittest.TestCase):
    def test_core_topics_still_match(self):
        r = companion.respond("how do I soothe cramps?", {})
        self.assertIn("cramps", r["reply"].lower())

    def test_new_menstrual_topics(self):
        cases = [
            ("what exactly is a period and why do we have them?", "uterus"),
            ("I think I have a yeast infection", "yeast"),
            ("it burns when I pee", "urinary"),
            ("what is PCOS?", "pcos"),
        ]
        for question, needle in cases:
            with self.subTest(question=question):
                r = companion.respond(question, {})
                self.assertIn(needle, r["reply"].lower())

    def test_new_health_topics(self):
        cases = [
            ("how much water should I drink every day?", "hydrat"),
            ("what foods should I eat more of?", "iron"),
            ("I feel so stressed about exams", "stress"),
            ("how do I deal with acne on my chin?", "acne"),
        ]
        for question, needle in cases:
            with self.subTest(question=question):
                r = companion.respond(question, {})
                self.assertIn(needle, r["reply"].lower())

    def test_new_hygiene_topics(self):
        cases = [
            ("how often should I shower?", "shower"),
            ("should I use an intimate wash down there?", "self-cleaning"),
            ("why do my feet smell so much?", "feet"),
            ("is it better to shave my legs with or against the hair?", "razor"),
            ("my armpits sweat a lot, what deodorant works?", "deodorant"),
        ]
        for question, needle in cases:
            with self.subTest(question=question):
                r = companion.respond(question, {})
                self.assertIn(needle, r["reply"].lower())

    def test_safety_topics_flag_doctor(self):
        for question in (
            "I think my friend has an eating disorder",
            "a tampon was left in too long, could it be toxic shock?",
            "could I be pregnant?",
        ):
            with self.subTest(question=question):
                r = companion.respond(question, {})
                self.assertTrue(r["doctor"])

    def test_pregnancy_question_gets_pregnancy_answer(self):
        r = companion.respond("could I be pregnant?", {})
        self.assertIn("pregnancy is possible", r["reply"].lower())

    def test_fallback_when_nothing_matches_and_no_ai(self):
        with mock.patch.object(companion, "ai_provider", return_value=""):
            r = companion.respond("what is the airspeed velocity of an unladen swallow?", {})
        self.assertIn(r["reply"], companion.FALLBACK_REPLIES)


class RoutingTests(unittest.TestCase):
    """The AI answers by default; the knowledge base covers crises and offline."""

    def test_ai_answers_a_general_question(self):
        calls = []
        with mock.patch.object(companion, "ai_provider", return_value="gemini"), \
             mock.patch.object(companion, "ai_api_key", return_value="test-key"), \
             mock.patch.object(
                 companion.urllib.request, "urlopen",
                 side_effect=lambda *a, **k: calls.append(1) or FakeResponse(GEMINI_BODY),
             ):
            r = companion.respond("how do I treat a blister on my heel?", {})
        self.assertEqual(len(calls), 1)
        self.assertIn("AI answer", r["reply"])

    def test_crisis_topics_never_reach_the_ai(self):
        for question in (
            "I want to kill myself",
            "I think I have an eating disorder",
            "a tampon was left in too long, could it be toxic shock?",
            "could I be pregnant?",
        ):
            with self.subTest(question=question):
                calls = []
                with mock.patch.object(companion, "ai_provider", return_value="gemini"), \
                     mock.patch.object(companion, "ai_api_key", return_value="test-key"), \
                     mock.patch.object(
                         companion.urllib.request, "urlopen",
                         side_effect=lambda *a, **k: calls.append(1) or FakeResponse(GEMINI_BODY),
                     ):
                    r = companion.respond(question, {})
                self.assertEqual(calls, [])
                self.assertTrue(r["doctor"])

    def test_ambiguous_words_are_not_escalated(self):
        # "depressed" and "binge" stay in the ordinary bank so a neighbouring
        # topic can claim them; only the explicit language is a crisis.
        r = companion.respond("I'm sad and depressed about exams", {})
        self.assertNotIn("crisis line", r["reply"].lower())
        r = companion.respond("I binge on chocolate before my period", {})
        self.assertNotIn("body image", r["reply"].lower())

    def test_gemini_block_falls_through_to_the_knowledge_base(self):
        # No candidates is how Gemini reports a safety block.
        with mock.patch.object(companion, "ai_provider", return_value="gemini"), \
             mock.patch.object(companion, "ai_api_key", return_value="test-key"), \
             mock.patch.object(
                 companion.urllib.request, "urlopen",
                 return_value=FakeResponse({"promptFeedback": {"blockReason": "SAFETY"}}),
             ):
            r = companion.respond("how do I soothe cramps?", {})
        self.assertIn("cramps", r["reply"].lower())


class GuardTests(unittest.TestCase):
    """Broad symptom words must not swallow questions about other body parts."""

    def test_unrelated_body_parts_do_not_get_the_cramps_answer(self):
        for question in ("my ear hurts", "my tooth hurts", "pain in my knee",
                         "a cut on my finger hurts", "my back hurts from sitting"):
            with self.subTest(question=question):
                r = companion.respond(question, {"phase": "follicular", "cycle_day": 8})
                self.assertNotIn("uterus", r["reply"].lower())

    def test_cycle_questions_still_reach_the_cramps_topic(self):
        for question in ("how do I soothe cramps?", "my back hurts with my period",
                         "period pain is bad today"):
            with self.subTest(question=question):
                r = companion.respond(question, {"phase": "follicular", "cycle_day": 8})
                self.assertIn("uterus", r["reply"].lower())

    def test_cold_sore_is_not_a_cold(self):
        r = companion.respond("i have a cold sore", {})
        self.assertNotIn("run down", r["reply"].lower())
        # the genuine article still matches
        r = companion.respond("i have a cold and a runny nose", {})
        self.assertIn("run down", r["reply"].lower())


class GreetingTests(unittest.TestCase):
    def test_greeting_gets_simple_hello(self):
        for hello in ("hi", "hello there", "hey!", "good morning"):
            with self.subTest(hello=hello):
                r = companion.respond(hello, {"name": "Maya Lin", "phase": "menstrual"})
                self.assertIn("Maya", r["reply"])
                self.assertEqual(r["tips"], [])
                self.assertFalse(r["doctor"])

    def test_greeting_has_no_extra_information(self):
        # phase footers must not be attached to a plain greeting
        r = companion.respond("hello", {"name": "Maya", "phase": "menstrual"})
        self.assertNotIn("Cozy rest", r["reply"])
        r = companion.respond("hi", {"name": "Maya", "phase": "luteal", "days_until_period": 3})
        self.assertNotIn("next period is estimated", r["reply"])

    def test_greeting_mixed_with_question_still_answers_the_question(self):
        r = companion.respond("hey, how do I soothe cramps?", {"name": "Maya"})
        self.assertIn("cramps", r["reply"].lower())

    def test_greeting_does_not_call_the_ai(self):
        calls = []
        with mock.patch.object(companion, "ai_provider", return_value="gemini"), \
             mock.patch.object(companion, "ai_api_key", return_value="test-key"), \
             mock.patch.object(
                 companion.urllib.request, "urlopen",
                 side_effect=lambda *a, **k: calls.append(1) or FakeResponse(GEMINI_BODY),
             ):
            companion.respond("hello", {"name": "Maya"})
        self.assertEqual(calls, [])

    def test_pure_greeting_detection(self):
        for hello in ("hi", "hello there", "hey!", "good morning", "how are you?"):
            with self.subTest(hello=hello):
                self.assertTrue(companion.is_pure_greeting(hello))
        for not_greeting in ("hey, I have cramps", "hi, is discharge normal?",
                             "hello, what is PCOS?"):
            with self.subTest(msg=not_greeting):
                self.assertFalse(companion.is_pure_greeting(not_greeting))


class ParseAiReplyTests(unittest.TestCase):
    def test_plain_json(self):
        out = companion.parse_ai_reply(
            json.dumps({"reply": "Drink water", "tips": ["sip often"], "doctor": False})
        )
        self.assertEqual(out["reply"], "Drink water")
        self.assertEqual(out["tips"], ["sip often"])
        self.assertFalse(out["doctor"])

    def test_json_wrapped_in_prose(self):
        out = companion.parse_ai_reply(
            'Here you go: {"reply": "Rest up", "tips": ["sleep"], "doctor": true} — hope that helps!'
        )
        self.assertEqual(out["reply"], "Rest up")
        self.assertTrue(out["doctor"])

    def test_plain_prose(self):
        out = companion.parse_ai_reply("Just a plain, warm answer.")
        self.assertEqual(out["reply"], "Just a plain, warm answer.")
        self.assertEqual(out["tips"], [])

    def test_empty(self):
        self.assertIsNone(companion.parse_ai_reply("   "))

    def test_tips_capped_at_three(self):
        out = companion.parse_ai_reply(
            json.dumps({"reply": "r", "tips": ["a", "b", "c", "d", "e"], "doctor": False})
        )
        self.assertEqual(len(out["tips"]), 3)


class FakeResponse:
    def __init__(self, body):
        self._body = body

    def read(self):
        return json.dumps(self._body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


AI_JSON = json.dumps({"reply": "AI answer", "tips": ["tip 1"], "doctor": True})


def gemini_body(text=AI_JSON):
    """A Gemini generateContent response carrying `text` as the model output."""
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def anthropic_body(text=AI_JSON):
    return {"content": [{"type": "text", "text": text}]}


GEMINI_BODY = gemini_body()


class ProviderTests(unittest.TestCase):
    def set_env(self, **env):
        clean = {k: "" for k in ("GIRLY_AI_PROVIDER", "GIRLY_AI_API_KEY", "GEMINI_API_KEY",
                                 "ANTHROPIC_API_KEY", "GIRLY_AI_MODEL", "GIRLY_AI_API_URL")}
        clean.update(env)
        return mock.patch.dict(companion.os.environ, clean, clear=False)

    def test_no_keys_means_no_provider(self):
        with self.set_env():
            self.assertEqual(companion.ai_provider(), "")
            self.assertFalse(companion.ai_enabled())
            self.assertEqual(companion.ai_api_key(), "")

    def test_gemini_key_selects_gemini(self):
        with self.set_env(GEMINI_API_KEY="g-key"):
            self.assertEqual(companion.ai_provider(), "gemini")
            self.assertEqual(companion.ai_api_key(), "g-key")
            self.assertEqual(companion.ai_model(), companion.PROVIDERS["gemini"]["model"])

    def test_anthropic_key_selects_anthropic(self):
        with self.set_env(ANTHROPIC_API_KEY="a-key"):
            self.assertEqual(companion.ai_provider(), "anthropic")
            self.assertEqual(companion.ai_model(), "claude-sonnet-5")

    def test_gemini_wins_when_both_keys_present(self):
        with self.set_env(GEMINI_API_KEY="g-key", ANTHROPIC_API_KEY="a-key"):
            self.assertEqual(companion.ai_provider(), "gemini")

    def test_provider_can_be_forced(self):
        with self.set_env(GEMINI_API_KEY="g-key", ANTHROPIC_API_KEY="a-key",
                          GIRLY_AI_PROVIDER="anthropic"):
            self.assertEqual(companion.ai_provider(), "anthropic")
            self.assertEqual(companion.ai_api_key(), "a-key")

    def test_model_override_wins(self):
        with self.set_env(GEMINI_API_KEY="g-key", GIRLY_AI_MODEL="gemini-3.8-flash"):
            self.assertEqual(companion.ai_model(), "gemini-3.8-flash")

    def test_gemini_url_carries_the_model(self):
        with self.set_env(GEMINI_API_KEY="g-key"):
            self.assertIn(companion.PROVIDERS["gemini"]["model"], companion.ai_api_url())

    def test_url_override_wins(self):
        with self.set_env(GEMINI_API_KEY="g-key", GIRLY_AI_API_URL="https://proxy.test/v1"):
            self.assertEqual(companion.ai_api_url(), "https://proxy.test/v1")


class AiLayerTests(unittest.TestCase):
    def test_ask_ai_returns_none_without_key(self):
        with mock.patch.object(companion, "ai_provider", return_value=""):
            self.assertIsNone(companion.ask_ai("anything", {}))

    def test_gemini_request_shape_and_parsing(self):
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["headers"] = req.headers
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return FakeResponse(gemini_body())

        with mock.patch.object(companion, "ai_provider", return_value="gemini"), \
             mock.patch.object(companion, "ai_api_key", return_value="g-key"), \
             mock.patch.object(companion.urllib.request, "urlopen", side_effect=fake_urlopen):
            expected_url = companion.ai_api_url()
            out = companion.ask_ai("why is the sky blue?", {"cycle_day": 14, "phase": "ovulatory"})

        self.assertEqual(out["reply"], "AI answer")
        self.assertTrue(out["doctor"])
        self.assertEqual(captured["url"], expected_url)
        self.assertIn(companion.PROVIDERS["gemini"]["model"], captured["url"])
        self.assertEqual(captured["headers"]["X-goog-api-key"], "g-key")
        # the system prompt travels as systemInstruction, not as a turn
        self.assertIn("Girly", captured["body"]["systemInstruction"]["parts"][0]["text"])
        self.assertNotIn("model", captured["body"])
        prompt = captured["body"]["contents"][0]["parts"][0]["text"]
        self.assertEqual(captured["body"]["contents"][0]["role"], "user")
        self.assertIn("Day 14", prompt)
        self.assertIn("why is the sky blue?", prompt)
        self.assertTrue(captured["body"]["generationConfig"]["responseMimeType"] == "application/json")

    def test_anthropic_request_shape_and_parsing(self):
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["headers"] = req.headers
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return FakeResponse(anthropic_body())

        with mock.patch.object(companion, "ai_provider", return_value="anthropic"), \
             mock.patch.object(companion, "ai_api_key", return_value="a-key"), \
             mock.patch.object(companion.urllib.request, "urlopen", side_effect=fake_urlopen):
            out = companion.ask_ai("why is the sky blue?", {"cycle_day": 14, "phase": "ovulatory"})

        self.assertEqual(out["reply"], "AI answer")
        self.assertEqual(captured["headers"]["X-api-key"], "a-key")
        self.assertEqual(captured["body"]["system"], companion.AI_SYSTEM_PROMPT)
        self.assertIn("Day 14", captured["body"]["messages"][0]["content"])
        self.assertIn("why is the sky blue?", captured["body"]["messages"][0]["content"])

    def test_gemini_safety_block_returns_none(self):
        with mock.patch.object(companion, "ai_provider", return_value="gemini"), \
             mock.patch.object(companion, "ai_api_key", return_value="g-key"), \
             mock.patch.object(
                 companion.urllib.request, "urlopen",
                 return_value=FakeResponse({"promptFeedback": {"blockReason": "SAFETY"}}),
             ):
            self.assertIsNone(companion.ask_ai("anything", {}))

    def test_ask_ai_returns_none_on_network_error(self):
        def boom(req, timeout=None):
            raise OSError("no network")

        with mock.patch.object(companion, "ai_provider", return_value="gemini"), \
             mock.patch.object(companion, "ai_api_key", return_value="g-key"), \
             mock.patch.object(companion.urllib.request, "urlopen", side_effect=boom):
            self.assertIsNone(companion.ask_ai("anything", {}))

    def test_ask_ai_returns_none_on_garbage_response(self):
        with mock.patch.object(companion, "ai_provider", return_value="gemini"), \
             mock.patch.object(companion, "ai_api_key", return_value="g-key"), \
             mock.patch.object(
                 companion.urllib.request, "urlopen",
                 return_value=FakeResponse({"candidates": [{"content": {}}]}),
             ):
            self.assertIsNone(companion.ask_ai("anything", {}))

    def test_respond_uses_ai_for_unmatched_questions(self):
        with mock.patch.object(companion, "ai_provider", return_value="gemini"), \
             mock.patch.object(companion, "ai_api_key", return_value="g-key"), \
             mock.patch.object(
                 companion.urllib.request, "urlopen",
                 return_value=FakeResponse(gemini_body(
                     json.dumps({"reply": "Here's your answer", "tips": [], "doctor": False}))),
             ):
            r = companion.respond("what is the airspeed velocity of an unladen swallow?", {})

        self.assertIn("Here's your answer", r["reply"])
        self.assertIn("educational insights", r["disclaimer"])

    def test_ai_is_the_primary_source_even_for_known_topics(self):
        # Gemini-first by design: with a key configured, the keyword bank no
        # longer intercepts questions it happens to have a canned answer for.
        calls = []
        with mock.patch.object(companion, "ai_provider", return_value="gemini"), \
             mock.patch.object(companion, "ai_api_key", return_value="g-key"), \
             mock.patch.object(
                 companion.urllib.request, "urlopen",
                 side_effect=lambda *a, **k: calls.append(1) or FakeResponse(gemini_body()),
             ):
            r = companion.respond("how do I soothe cramps?", {})
        self.assertEqual(len(calls), 1)
        self.assertEqual(r["reply"], "AI answer")


if __name__ == "__main__":
    unittest.main()
