"""Admin access rules — run with `python -m unittest test_admin.py`."""

import os
import tempfile
import unittest
from unittest import mock

from handlers import DEFAULT_ADMIN_EMAIL, admin_emails, role_for_email
from store import Store


class RoleForEmailTests(unittest.TestCase):
    def test_the_default_address_is_the_admin(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GIRLY_ADMIN_EMAIL", None)
            self.assertEqual(role_for_email(DEFAULT_ADMIN_EMAIL), "admin")

    def test_an_ordinary_address_is_not_an_admin(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GIRLY_ADMIN_EMAIL", None)
            for email in ("maya@example.com", "someone@gmail.com", "", None):
                with self.subTest(email=email):
                    self.assertEqual(role_for_email(email), "user")

    def test_matching_ignores_case_and_padding(self):
        # The address is typed by hand into GIRLY_ADMIN_EMAIL and lowercased on
        # register, so the two must still meet in the middle.
        with mock.patch.dict(os.environ, {"GIRLY_ADMIN_EMAIL": "  Boss@Example.COM  "}):
            for typed in ("boss@example.com", "BOSS@EXAMPLE.COM", "  Boss@Example.com "):
                with self.subTest(typed=typed):
                    self.assertEqual(role_for_email(typed), "admin")

    def test_several_admins_can_be_named(self):
        with mock.patch.dict(os.environ, {"GIRLY_ADMIN_EMAIL": "a@x.com, b@y.com"}):
            self.assertEqual(admin_emails(), {"a@x.com", "b@y.com"})
            self.assertEqual(role_for_email("b@y.com"), "admin")
            self.assertEqual(role_for_email("c@z.com"), "user")

    def test_the_env_var_replaces_the_default_rather_than_adding_to_it(self):
        with mock.patch.dict(os.environ, {"GIRLY_ADMIN_EMAIL": "only@x.com"}):
            self.assertEqual(role_for_email("only@x.com"), "admin")
            self.assertEqual(role_for_email(DEFAULT_ADMIN_EMAIL), "user")

    def test_a_blank_env_var_names_nobody(self):
        # Otherwise an empty GIRLY_ADMIN_EMAIL on the host would quietly leave the
        # default address in charge.
        with mock.patch.dict(os.environ, {"GIRLY_ADMIN_EMAIL": "   ,  ,"}):
            self.assertEqual(admin_emails(), set())
            self.assertEqual(role_for_email(DEFAULT_ADMIN_EMAIL), "user")


class SeedTests(unittest.TestCase):
    def test_no_seeded_account_is_an_admin(self):
        # Regression guard. A seeded operator with a published password is how
        # admin@girly.app / admin123 ended up live on a public URL.
        with tempfile.TemporaryDirectory() as tmp:
            store = Store.load(os.path.join(tmp, "girly.json"))
        self.assertEqual([u for u in store.users if u.get("role") == "admin"], [])
        self.assertEqual([u for u in store.users if u.get("role") != "user"], [])

    def test_the_documented_demo_password_is_not_a_seeded_admin(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store.load(os.path.join(tmp, "girly.json"))
        emails = {u.get("email") for u in store.users}
        self.assertNotIn("admin@girly.app", emails)


if __name__ == "__main__":
    unittest.main()
