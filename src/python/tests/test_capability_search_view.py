"""The capability search partial on the Repo Classes page (NERD004 SPEC005).

A catalog read, not environment-scoped: ``login_required`` only, one
``search_discovery`` call per request, and none at all until the user has
typed a query or picked a kind -- the empty form must not fetch the whole
catalog on page load.
"""
import unittest
from unittest import mock

from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse


class FakeResponse:
    def __init__(self, data=None, success=True, error=None):
        self.success = success
        self.data = data
        self.error = error


class FakeClient:
    def __init__(self, response=None):
        self.calls = []
        self.response = response or FakeResponse(
            {"items": [], "total": 0, "limit": 50, "offset": 0}
        )

    def search_discovery(self, **kwargs):
        self.calls.append(("search_discovery", kwargs))
        return self.response

    def list_repo_classes(self):
        self.calls.append(("list_repo_classes", {}))
        return FakeResponse([])


ENVELOPE = {
    "items": [
        {
            "repo_class_name": "hmd-cli-monitoring",
            "version": "1.2.0",
            "summary": "Ships log retention.",
            "score": 3,
            "matched_fields": ["capability.name"],
            "capabilities": [
                {
                    "name": "hmd monitoring rotate-logs",
                    "kind": "cli_command",
                    "description": "Rotates log files.",
                    "location": "src/python/monitoring/cli.py:40",
                }
            ],
            "entry_points": [],
            "related_docs": [],
            "capability_count": 1,
        }
    ],
    "total": 1,
    "limit": 50,
    "offset": 0,
}


class CapabilitySearchViewTests(unittest.TestCase):
    def setUp(self):
        self.user = User.objects.create_user("viewer", password="pw")
        self.fake = FakeClient(FakeResponse(ENVELOPE))
        patcher = mock.patch(
            "deployments.views.get_api_client_for_request", return_value=self.fake
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = Client()
        self.client.force_login(self.user)
        self.url = reverse("deployments:capability_search")

    @staticmethod
    def _body(response) -> str:
        return response.content.decode()

    def test_requires_login(self):
        response = Client().get(self.url + "?q=logs")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.fake.calls, [])

    def test_empty_form_makes_no_backend_call(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.fake.calls, [])
        self.assertNotIn("<table", self._body(response))

    def test_query_and_kind_reach_the_backend_once_and_render_rows(self):
        response = self.client.get(self.url + "?q=rotate&kind=cli_command&page=2")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.fake.calls), 1)
        name, kwargs = self.fake.calls[0]
        self.assertEqual(name, "search_discovery")
        self.assertEqual(kwargs["q"], "rotate")
        self.assertEqual(kwargs["kind"], "cli_command")
        self.assertEqual(kwargs["limit"], 50)
        self.assertEqual(kwargs["offset"], 50)

        body = self._body(response)
        self.assertIn("hmd monitoring rotate-logs", body)
        self.assertIn("src/python/monitoring/cli.py:40", body)
        self.assertIn(
            reverse(
                "deployments:repo_class_version_detail",
                kwargs={"repo_class_name": "hmd-cli-monitoring", "version": "1.2.0"},
            ),
            body,
        )

    def test_unknown_kind_is_rejected_without_a_backend_call(self):
        response = self.client.get(self.url + "?kind=bogus")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.fake.calls, [])
        self.assertIn("Unknown capability kind", self._body(response))

    def test_backend_failure_renders_an_error_not_a_500(self):
        self.fake.response = FakeResponse(None, success=False, error="down")
        response = self.client.get(self.url + "?q=x")
        self.assertEqual(response.status_code, 200)
        self.assertIn("down", self._body(response))

    def test_repo_class_list_passes_kind_options(self):
        response = self.client.get(reverse("deployments:repo_class_list"))
        self.assertEqual(response.status_code, 200)
        body = self._body(response)
        for kind in ("endpoint", "cli_command", "function", "class", "operation"):
            self.assertIn(f'value="{kind}"', body)
        self.assertIn(self.url, body)


if __name__ == "__main__":
    unittest.main()
