"""The extension seam (NERD0015): slots, extra apps, the client class.

The core must render every page with no extra app installed and reference
nothing premium; an extra app must be able to fill a slot with the page's
context plus its own.
"""
import os
import sys
import textwrap

from django.template import Context, Template
import unittest

from django.test import RequestFactory, override_settings

from deployments.services.auth import api_client_class
from deployments.services.api_client import DeploymentAPIClient
from deployments.templatetags.extension_slots import extension_slot, slot_templates


def _render(src, **ctx):
    return Template("{% load extension_slots %}" + src).render(Context(ctx))


class TestSlotsWithNoExtraApps(unittest.TestCase):
    def test_a_slot_nobody_fills_renders_nothing(self):
        self.assertEqual(_render('{% extension_slot "sidebar_nav" %}'), "")
        self.assertEqual(slot_templates("sidebar_nav"), [])

    def test_core_templates_reference_no_premium_url_names(self):
        root = os.path.join(os.path.dirname(__file__), "..", "deployments", "templates")
        premium = (
            "deployment_list",
            "deployment_detail",
            "deployment_logs",
            "deployment_dag_partial",
            "deployment_timeline_data",
            "deployment_step_logs",
            "dashboard_recent_deployments",
            "changeset_apply",
            "apply_modal.html",
            "log_viewer.html",
        )
        offenders = []
        for dirpath, _, files in os.walk(root):
            for name in files:
                text = open(os.path.join(dirpath, name), encoding="utf-8").read()
                for needle in premium:
                    if needle in text:
                        offenders.append((name, needle))
        self.assertEqual(offenders, [])

    def test_the_default_client_class_is_the_core_client(self):
        with override_settings(DEPLOYMENT_API_CLIENT_CLASS=""):
            self.assertIs(api_client_class(), DeploymentAPIClient)


class TestSlotsWithAnExtraApp(unittest.TestCase):
    """A throwaway extra app on disk: one slot template and a slots.context hook."""

    def setUp(self):
        import tempfile

        self.root = tempfile.mkdtemp()
        pkg = os.path.join(self.root, "fake_ext")
        os.makedirs(os.path.join(pkg, "templates", "fake_ext", "slots"))
        open(os.path.join(pkg, "__init__.py"), "w").close()
        with open(os.path.join(pkg, "slots.py"), "w") as fh:
            fh.write("def context(request):\n    return {'from_hook': 'hooked'}\n")
        with open(
            os.path.join(pkg, "templates", "fake_ext", "slots", "sidebar_nav.html"), "w"
        ) as fh:
            fh.write("<a>{{ from_hook }}:{{ page_value }}</a>")
        sys.path.insert(0, self.root)
        self.templates = [
            {
                "BACKEND": "django.template.backends.django.DjangoTemplates",
                "DIRS": [os.path.join(pkg, "templates")],
                "APP_DIRS": False,
                "OPTIONS": {"builtins": ["deployments.templatetags.extension_slots"]},
            }
        ]

    def tearDown(self):
        sys.path.remove(self.root)
        sys.modules.pop("fake_ext.slots", None)
        sys.modules.pop("fake_ext", None)

    def test_the_slot_renders_with_page_context_and_the_apps_hook(self):
        with override_settings(EXTRA_APPS=["fake_ext"], TEMPLATES=self.templates):
            html = Template('{% extension_slot "sidebar_nav" %}').render(
                Context({"page_value": "page", "request": RequestFactory().get("/")})
            )
        self.assertEqual(html, "<a>hooked:page</a>")

    def test_a_slot_the_app_does_not_ship_is_skipped(self):
        with override_settings(EXTRA_APPS=["fake_ext"], TEMPLATES=self.templates):
            html = Template('{% extension_slot "dashboard_cards" %}').render(
                Context({})
            )
        self.assertEqual(html, "")


class TestExtensionSections(unittest.TestCase):
    def test_an_extra_apps_prefix_maps_to_its_section(self):
        from deployments.context_processors import sidebar_context
        from unittest.mock import patch

        request = RequestFactory().get("/deployments/csd-1/")
        request.user = type("U", (), {"is_authenticated": True})()
        with override_settings(
            EXTENSION_SECTIONS={"deployments": "/deployments"}
        ), patch(
            "deployments.context_processors.get_api_client_for_request",
            return_value=None,
        ), patch(
            "deployments.context_processors.get_user_environments", return_value=[]
        ):
            self.assertEqual(sidebar_context(request)["active_section"], "deployments")
        with override_settings(EXTENSION_SECTIONS={}), patch(
            "deployments.context_processors.get_api_client_for_request",
            return_value=None,
        ), patch(
            "deployments.context_processors.get_user_environments", return_value=[]
        ):
            self.assertEqual(sidebar_context(request)["active_section"], "")
