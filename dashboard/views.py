# -*- coding: utf-8 -*-
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.views.generic.base import TemplateView, View
from django.views.generic.detail import DetailView

from babybuddy.mixins import LoginRequiredMixin, PermissionRequiredMixin
from core.models import Child
from dashboard.card_registry import CARD_KEYS


class Dashboard(LoginRequiredMixin, TemplateView):
    # TODO: Use .card-deck in this template once BS4 is finalized.
    template_name = "dashboard/dashboard.html"

    # Show the overall dashboard or a child dashboard if one Child instance.
    def get(self, request, *args, **kwargs):
        children = Child.objects.count()
        if children == 0:
            return HttpResponseRedirect(reverse("babybuddy:welcome"))
        elif children == 1:
            return HttpResponseRedirect(
                reverse("dashboard:dashboard-child", args={Child.objects.first().slug})
            )
        return super(Dashboard, self).get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(Dashboard, self).get_context_data(**kwargs)
        context["objects"] = Child.objects.all().order_by(
            "last_name", "first_name", "id"
        )
        return context


class ChildDashboard(PermissionRequiredMixin, DetailView):
    model = Child
    permission_required = ("core.view_child",)
    template_name = "dashboard/child.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        settings = self.request.user.settings
        # Cards to actually render (visible only, user order).
        context["dashboard_cards"] = settings.resolve_dashboard_cards()
        # Full set (incl. hidden) for the edit UI.
        context["dashboard_cards_all"] = settings.resolve_dashboard_cards(
            include_hidden=True
        )
        return context


class ChildDashboardEdit(PermissionRequiredMixin, View):
    """
    Persist a user's dashboard card preferences: visibility (show/hide) and
    order (reorder).

    Accepts a POST with:
    - ``cards``  = the card keys that should be visible (checkbox values).
    - ``order``  = comma-separated card keys giving the desired order (from the
      reorder controls). Optional/partial: unknown keys are dropped and any
      known card missing from it is appended in its current order, so the view
      degrades gracefully if JavaScript is unavailable.
    """

    permission_required = ("core.view_child",)

    def post(self, request, *args, **kwargs):
        child = Child.objects.get(slug=kwargs["slug"])
        settings = request.user.settings

        visible_keys = set(request.POST.getlist("cards")) & set(CARD_KEYS)

        # Build the ordered key list from the posted order, de-duplicated and
        # filtered to known cards.
        order = []
        seen = set()
        for key in request.POST.get("order", "").split(","):
            key = key.strip()
            if key in CARD_KEYS and key not in seen:
                seen.add(key)
                order.append(key)
        # Append any known cards not present in the posted order, preserving
        # their current relative order (forward-compat / no-JS fallback).
        for entry in settings.resolve_dashboard_cards(include_hidden=True):
            if entry["key"] not in seen:
                seen.add(entry["key"])
                order.append(entry["key"])

        settings.dashboard_cards = [
            {"key": key, "visible": key in visible_keys} for key in order
        ]
        settings.save()

        return HttpResponseRedirect(
            reverse("dashboard:dashboard-child", args={child.slug})
        )
