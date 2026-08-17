# -*- coding: utf-8 -*-
import zoneinfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext_lazy

from rest_framework.authtoken.models import Token


class Settings(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    dashboard_refresh_rate = models.DurationField(
        verbose_name=_("Refresh rate"),
        help_text=_(
            "If supported by browser, the dashboard will only refresh when visible, and also when receiving focus."
        ),
        blank=True,
        null=True,
        default=timezone.timedelta(minutes=1),
        choices=[
            (None, _("disabled")),
            (
                timezone.timedelta(minutes=1),
                ngettext_lazy("%(minutes)d minute", "%(minutes)d minutes", 1)
                % {"minutes": 1},
            ),
            (
                timezone.timedelta(minutes=2),
                ngettext_lazy("%(minutes)d minute", "%(minutes)d minutes", 2)
                % {"minutes": 2},
            ),
            (
                timezone.timedelta(minutes=3),
                ngettext_lazy("%(minutes)d minute", "%(minutes)d minutes", 3)
                % {"minutes": 3},
            ),
            (
                timezone.timedelta(minutes=4),
                ngettext_lazy("%(minutes)d minute", "%(minutes)d minutes", 4)
                % {"minutes": 4},
            ),
            (
                timezone.timedelta(minutes=5),
                ngettext_lazy("%(minutes)d minute", "%(minutes)d minutes", 5)
                % {"minutes": 5},
            ),
            (
                timezone.timedelta(minutes=10),
                ngettext_lazy("%(minutes)d minute", "%(minutes)d minutes", 10)
                % {"minutes": 10},
            ),
            (
                timezone.timedelta(minutes=15),
                ngettext_lazy("%(minutes)d minute", "%(minutes)d minutes", 15)
                % {"minutes": 15},
            ),
            (
                timezone.timedelta(minutes=30),
                ngettext_lazy("%(minutes)d minute", "%(minutes)d minutes", 30)
                % {"minutes": 30},
            ),
        ],
    )
    dashboard_hide_empty = models.BooleanField(
        verbose_name=_("Hide Empty Dashboard Cards"), default=False, editable=True
    )
    dashboard_hide_age = models.DurationField(
        verbose_name=_("Hide data older than"),
        help_text=_(
            "This setting controls which data will be shown " "in the dashboard."
        ),
        blank=True,
        null=True,
        default=None,
        choices=[
            (None, _("show all data")),
            (
                timezone.timedelta(days=1),
                ngettext_lazy("%(days)d day", "%(days)d days", 1) % {"days": 1},
            ),
            (
                timezone.timedelta(days=2),
                ngettext_lazy("%(days)d day", "%(days)d days", 2) % {"days": 2},
            ),
            (
                timezone.timedelta(days=3),
                ngettext_lazy("%(days)d day", "%(days)d days", 3) % {"days": 3},
            ),
            (
                timezone.timedelta(weeks=1),
                ngettext_lazy("%(weeks)d week", "%(weeks)d weeks", 1) % {"weeks": 1},
            ),
            (
                timezone.timedelta(weeks=4),
                ngettext_lazy("%(weeks)d week", "%(weeks)d weeks", 4) % {"weeks": 4},
            ),
        ],
    )
    language = models.CharField(
        choices=settings.LANGUAGES,
        default=settings.LANGUAGE_CODE,
        max_length=255,
        verbose_name=_("Language"),
    )
    timezone = models.CharField(
        choices=sorted(
            tuple(zip(zoneinfo.available_timezones(), zoneinfo.available_timezones()))
        ),
        default=timezone.get_default_timezone_name(),
        max_length=100,
        verbose_name=_("Timezone"),
    )
    pagination_count = models.PositiveIntegerField(
        choices=[
            (10, _("%(count)d Per Page") % {"count": 10}),
            (25, _("%(count)d Per Page") % {"count": 25}),
            (50, _("%(count)d Per Page") % {"count": 50}),
            (100, _("%(count)d Per Page") % {"count": 100}),
            (250, _("%(count)d Per Page") % {"count": 250}),
            (0, _("Show All")),
        ],
        default=25,
        verbose_name=_("Items Per Page"),
    )
    dashboard_cards = models.JSONField(
        blank=True,
        null=True,
        default=None,
        verbose_name=_("Dashboard cards"),
        help_text=_(
            "Per-user dashboard card visibility and order. A list of "
            '{"key": <card key>, "visible": <bool>} entries. When empty, all '
            "cards are shown in their default order."
        ),
    )

    def __str__(self):
        return str(format_lazy(_("{user}'s Settings"), user=self.user))

    def api_key(self, reset=False):
        """
        Get or create an API key for the associated user.
        :param reset: If True, delete the existing key and create a new one.
        :return: The user's API key.
        """
        if reset:
            Token.objects.get(user=self.user).delete()
        return Token.objects.get_or_create(user=self.user)[0]

    @property
    def dashboard_refresh_rate_milliseconds(self):
        """
        Convert seconds to milliseconds to be used in a Javascript setInterval
        function call.
        :return: the refresh rate in milliseconds or None.
        """
        if self.dashboard_refresh_rate:
            return self.dashboard_refresh_rate.seconds * 1000
        return None

    def resolve_dashboard_cards(self, include_hidden=False):
        """
        Merge the user's stored ``dashboard_cards`` preferences with the
        canonical card registry to produce the ordered list of cards to render.

        - Stored entries are honoured for order and visibility.
        - Unknown/stale keys in stored prefs are dropped.
        - Registry cards the user has never seen (not in stored prefs) are
          appended, visible, so upstream additions appear automatically.

        :param include_hidden: when True, hidden cards are included (each dict
            carries a ``visible`` flag) — used by the edit UI. When False,
            only visible cards are returned — used for rendering.
        :return: list of dicts: {"key", "label", "template", "func", "visible"}.
        """
        # Imported here to avoid a circular import at module load time.
        from dashboard.card_registry import (
            CARD_REGISTRY,
            CARD_REGISTRY_BY_KEY,
            card_func_name,
            card_template,
        )

        prefs = self.dashboard_cards or []
        seen = set()
        resolved = []

        def _entry(key, visible):
            registry_entry = CARD_REGISTRY_BY_KEY[key]
            return {
                "key": key,
                "label": registry_entry["label"],
                "template": card_template(key),
                "func": card_func_name(key),
                "visible": visible,
            }

        # Honour stored order/visibility, skipping unknown keys.
        for pref in prefs:
            if not isinstance(pref, dict):
                continue
            key = pref.get("key")
            if key not in CARD_REGISTRY_BY_KEY or key in seen:
                continue
            seen.add(key)
            resolved.append(_entry(key, bool(pref.get("visible", True))))

        # Append registry cards the user has never configured (forward-compat).
        for registry_entry in CARD_REGISTRY:
            key = registry_entry["key"]
            if key not in seen:
                seen.add(key)
                resolved.append(_entry(key, True))

        if not include_hidden:
            resolved = [entry for entry in resolved if entry["visible"]]
        return resolved


@receiver(post_save, sender=get_user_model())
def create_user_settings(sender, instance, created, **kwargs):
    if created:
        Settings.objects.create(user=instance)


@receiver(post_save, sender=get_user_model())
def save_user_settings(sender, instance, **kwargs):
    instance.settings.save()
