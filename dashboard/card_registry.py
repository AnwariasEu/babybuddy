# -*- coding: utf-8 -*-
"""
Single source of truth for the per-child dashboard cards.

Each entry describes an available card:
    key       - stable identifier, persisted in Settings.dashboard_cards
    label     - human-readable name shown in the "edit dashboard" UI
    template  - the card partial rendered for this card
    func      - the inclusion-tag function (in dashboard.templatetags.cards)
                that computes the card's context; all accept (context, child)

The list order is the default dashboard order. Adding a card upstream is a
matter of appending an entry here; users who have never seen it will get it
appended to their dashboard automatically (see Settings.resolve_dashboard_cards).
"""

from django.utils.translation import gettext_lazy as _

# NOTE: order here mirrors the historic hardcoded order in
# dashboard/templates/dashboard/child.html.
CARD_REGISTRY = [
    {"key": "timer_list", "label": _("Active Timers")},
    {"key": "feeding_last", "label": _("Last Feeding")},
    {"key": "diaperchange_last", "label": _("Last Diaper Change")},
    {"key": "pumping_last", "label": _("Last Pumping")},
    {"key": "pumping_recent", "label": _("Recent Pumping")},
    {"key": "sleep_last", "label": _("Last Sleep")},
    {"key": "medication_last", "label": _("Last Medication")},
    {"key": "feeding_last_method", "label": _("Last Feeding Method")},
    {"key": "feeding_recent", "label": _("Recent Feeding")},
    {"key": "statistics", "label": _("Statistics")},
    {"key": "sleep_recent", "label": _("Recent Sleep")},
    {"key": "sleep_naps_day", "label": _("Today's Naps")},
    {"key": "tummytime_day", "label": _("Today's Tummy Time")},
    {"key": "diaperchange_types", "label": _("Diaper Change Types")},
    {"key": "breastfeeding", "label": _("Breastfeeding")},
]

# Derived lookups.
CARD_KEYS = [entry["key"] for entry in CARD_REGISTRY]
CARD_REGISTRY_BY_KEY = {entry["key"]: entry for entry in CARD_REGISTRY}


def card_func_name(key):
    """The templatetag/function name that computes a card's context."""
    return "card_{}".format(key)


def card_template(key):
    """The partial template rendered for a card."""
    return "cards/{}.html".format(key)
