# -*- coding: utf-8 -*-
from django.test import TestCase
from django.test import Client as HttpClient
from django.contrib.auth import get_user_model
from django.core.management import call_command

from faker import Faker

from core.models import Child
from dashboard.card_registry import CARD_KEYS


class ViewsTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        super(ViewsTestCase, cls).setUpClass()
        fake = Faker()
        call_command("migrate", verbosity=0)

        cls.c = HttpClient()

        fake_user = fake.simple_profile()
        cls.credentials = {
            "username": fake_user["username"],
            "password": fake.password(),
        }
        cls.user = get_user_model().objects.create_user(
            is_superuser=True, **cls.credentials
        )

        cls.c.login(**cls.credentials)

    def test_dashboard_views(self):
        page = self.c.get("/dashboard/")
        self.assertEqual(page.url, "/welcome/")

        call_command("fake", verbosity=0, children=1, days=1)
        child = Child.objects.first()
        page = self.c.get("/dashboard/")
        self.assertEqual(page.url, "/children/{}/dashboard/".format(child.slug))

        page = self.c.get("/dashboard/")
        self.assertEqual(page.url, "/children/{}/dashboard/".format(child.slug))
        # Test the actual child dashboard (including cards).
        # TODO: Test cards more granularly.
        page = self.c.get("/children/{}/dashboard/".format(child.slug))
        self.assertEqual(page.status_code, 200)

        Child.objects.create(
            first_name="Second", last_name="Child", birth_date="2000-01-01"
        )
        page = self.c.get("/dashboard/")
        self.assertEqual(page.status_code, 200)


class EditableDashboardTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        fake = Faker()
        call_command("migrate", verbosity=0)

        cls.child = Child.objects.create(
            first_name="Test", last_name="Child", birth_date="2020-01-01"
        )

        cls.creds = {"username": "parent1", "password": fake.password()}
        cls.user = get_user_model().objects.create_user(is_superuser=True, **cls.creds)
        cls.creds2 = {"username": "parent2", "password": fake.password()}
        cls.user2 = get_user_model().objects.create_user(
            is_superuser=True, **cls.creds2
        )

    def setUp(self):
        self.c = HttpClient()
        self.c.login(**self.creds)
        self.url = "/children/{}/dashboard/".format(self.child.slug)
        self.edit_url = "/children/{}/dashboard/edit/".format(self.child.slug)

    def test_default_all_cards_visible_in_default_order(self):
        cards = self.user.settings.resolve_dashboard_cards()
        self.assertEqual([c["key"] for c in cards], CARD_KEYS)
        page = self.c.get(self.url)
        self.assertContains(page, 'id="card-toggle-medication_last"')
        # Default: none stored yet.
        self.assertIsNone(self.user.settings.dashboard_cards)

    def test_hiding_a_card_persists_and_removes_it_from_render(self):
        visible = [k for k in CARD_KEYS if k != "medication_last"]
        page = self.c.post(self.edit_url, {"cards": visible}, follow=True)
        self.assertEqual(page.status_code, 200)

        self.user.settings.refresh_from_db()
        stored = {c["key"]: c["visible"] for c in self.user.settings.dashboard_cards}
        self.assertFalse(stored["medication_last"])
        self.assertTrue(stored["feeding_last"])

        resolved = self.user.settings.resolve_dashboard_cards()
        self.assertNotIn("medication_last", [c["key"] for c in resolved])

        # The medication card template renders a known heading; confirm it is
        # gone from the page while another card remains.
        page = self.c.get(self.url)
        rendered_keys = [c["key"] for c in page.context["dashboard_cards"]]
        self.assertNotIn("medication_last", rendered_keys)
        self.assertIn("feeding_last", rendered_keys)

    def test_dashboards_are_independent_per_user(self):
        # user hides medication_last.
        visible = [k for k in CARD_KEYS if k != "medication_last"]
        self.c.post(self.edit_url, {"cards": visible}, follow=True)

        # user2 is unaffected.
        c2 = HttpClient()
        c2.login(**self.creds2)
        resolved2 = self.user2.settings.resolve_dashboard_cards()
        self.assertIn("medication_last", [c["key"] for c in resolved2])
        self.assertIsNone(self.user2.settings.dashboard_cards)

    def test_unknown_stored_keys_are_ignored_and_new_cards_appended(self):
        # Simulate stale prefs: an obsolete key + a subset missing newer cards.
        self.user.settings.dashboard_cards = [
            {"key": "obsolete_card", "visible": True},
            {"key": "feeding_last", "visible": False},
        ]
        self.user.settings.save()

        resolved = self.user.settings.resolve_dashboard_cards(include_hidden=True)
        keys = [c["key"] for c in resolved]
        self.assertNotIn("obsolete_card", keys)
        # feeding_last honoured (hidden) and kept first.
        self.assertEqual(keys[0], "feeding_last")
        self.assertFalse(resolved[0]["visible"])
        # Every registry card still present (new ones appended, visible).
        self.assertEqual(set(keys), set(CARD_KEYS))
        self.assertTrue(
            next(c for c in resolved if c["key"] == "medication_last")["visible"]
        )

    def test_reorder_persists_and_is_respected_in_render(self):
        # Move medication_last and breastfeeding to the front.
        new_order = ["medication_last", "breastfeeding"] + [
            k for k in CARD_KEYS if k not in ("medication_last", "breastfeeding")
        ]
        page = self.c.post(
            self.edit_url,
            {"cards": CARD_KEYS, "order": ",".join(new_order)},
            follow=True,
        )
        self.assertEqual(page.status_code, 200)

        self.user.settings.refresh_from_db()
        stored_order = [c["key"] for c in self.user.settings.dashboard_cards]
        self.assertEqual(stored_order, new_order)

        # Render order (visible cards) follows the stored order.
        rendered = [c["key"] for c in page.context["dashboard_cards"]]
        self.assertEqual(rendered[:2], ["medication_last", "breastfeeding"])
        self.assertEqual(rendered, new_order)

    def test_reorder_and_hide_together(self):
        new_order = ["sleep_last"] + [k for k in CARD_KEYS if k != "sleep_last"]
        visible = [k for k in CARD_KEYS if k != "medication_last"]
        self.c.post(
            self.edit_url,
            {"cards": visible, "order": ",".join(new_order)},
            follow=True,
        )
        self.user.settings.refresh_from_db()
        stored = self.user.settings.dashboard_cards
        self.assertEqual([c["key"] for c in stored], new_order)
        by_key = {c["key"]: c["visible"] for c in stored}
        self.assertFalse(by_key["medication_last"])
        self.assertTrue(by_key["sleep_last"])
        # Hidden card absent from render, order otherwise preserved.
        resolved = [c["key"] for c in self.user.settings.resolve_dashboard_cards()]
        self.assertEqual(resolved[0], "sleep_last")
        self.assertNotIn("medication_last", resolved)

    def test_partial_order_appends_missing_keys(self):
        # Simulate a no-JS / partial submission: only two keys in `order`.
        self.c.post(
            self.edit_url,
            {"cards": CARD_KEYS, "order": "breastfeeding,statistics"},
            follow=True,
        )
        self.user.settings.refresh_from_db()
        stored_order = [c["key"] for c in self.user.settings.dashboard_cards]
        # Posted keys first, then the rest in their default order.
        self.assertEqual(stored_order[:2], ["breastfeeding", "statistics"])
        self.assertEqual(set(stored_order), set(CARD_KEYS))
        self.assertEqual(len(stored_order), len(CARD_KEYS))
