"""Authorization tests for the views that take an environment from the request.

These views accept an environment the caller names, rather than one derived from a
path they were routed to, so the only thing standing between a logged-in user and
another environment's BOM is an explicit check. Each is exercised three ways: a user
without the grant is refused, a user with it is not, and a superuser is not.

The denial *shape* is asserted too. ``access_denied.html`` extends ``base.html``, so
returning it to a fetch() or swapping it into an HTMX target would turn a correct 403
into a broken page.
"""
import json
import unittest
from unittest import mock

from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from deployments.models import ChangeSetDraft, UserEnvironmentPermission


class FakeResponse:
    def __init__(self, data=None, success=True, error=None):
        self.success = success
        self.data = data if data is not None else []
        self.error = error


class FakeClient:
    """Records what a view asked for, so "was the view reached" is observable."""

    def __init__(self):
        self.calls = []

    def _record(self, name, *args, **kwargs):
        self.calls.append(name)

    def get_deployment_bom(self, environment, *a, **k):
        self._record("get_deployment_bom")
        return FakeResponse([])

    def suggest_resource_dependencies(self, environment, *a, **k):
        self._record("suggest_resource_dependencies")
        return FakeResponse({})

    def compare_environments(self, from_env, to_env, *a, **k):
        self._record("compare_environments")
        return FakeResponse({})

    def list_resources(self, *a, **k):
        self._record("list_resources")
        return FakeResponse([])

    def find_resources_by_selector(self, *a, **k):
        self._record("find_resources_by_selector")
        return FakeResponse([])


class ViewAuthzTestCase(unittest.TestCase):
    """A granted user, an ungranted user, and a superuser, against a fake backend."""

    def setUp(self):
        self.granted = User.objects.create_user("granted", password="pw")
        UserEnvironmentPermission.objects.create(
            user=self.granted, environment="dev", role="viewer"
        )
        self.ungranted = User.objects.create_user("ungranted", password="pw")
        self.root = User.objects.create_superuser("root", password="pw")

        self.fake = FakeClient()
        patcher = mock.patch(
            "deployments.views.get_api_client_for_request", return_value=self.fake
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        # get_user_environments hits the same client; keep it off the network.
        env_patcher = mock.patch(
            "deployments.views.get_user_environments", return_value=["dev"]
        )
        env_patcher.start()
        self.addCleanup(env_patcher.stop)

    def client_for(self, user):
        client = Client()
        client.force_login(user)
        return client

    def draft_for(self, user):
        return ChangeSetDraft.objects.create(
            user=user, name="d", content=[], status=ChangeSetDraft.Status.DRAFT
        )


class TestEnvironmentScopedApis(ViewAuthzTestCase):
    """The five views that read a caller-named environment's data."""

    def urls_for(self, user):
        draft = self.draft_for(user)
        return {
            "api_search_instances": (
                reverse("deployments:api_search_instances") + "?q=abc&environment=prod"
            ),
            "api_search_instances_html": (
                reverse(
                    "deployments:api_search_instances_html",
                    kwargs={"draft_id": draft.pk},
                )
                + "?q=abc&environment=prod"
            ),
            "api_dep_candidates": (
                reverse("deployments:api_dep_candidates", kwargs={"draft_id": draft.pk})
                + "?environment=prod&role=db&repo_class=x"
            ),
            "api_repo_class_version_resources": (
                reverse("deployments:api_repo_class_version_resources")
                + "?repo_class_version_id=1&environment=prod"
            ),
            "changeset_bom_impact": (
                reverse(
                    "deployments:changeset_bom_impact", kwargs={"draft_id": draft.pk}
                )
                + "?environment=prod"
            ),
        }

    def test_an_ungranted_user_is_refused_by_every_one_of_them(self):
        client = self.client_for(self.ungranted)
        for name, url in self.urls_for(self.ungranted).items():
            with self.subTest(view=name):
                response = client.get(url)
                self.assertEqual(response.status_code, 403, name)
        # The refusal must land before any backend call is made.
        self.assertEqual(self.fake.calls, [])

    def test_a_granted_user_reaches_the_backend(self):
        UserEnvironmentPermission.objects.create(
            user=self.granted, environment="prod", role="viewer"
        )
        client = self.client_for(self.granted)
        for name, url in self.urls_for(self.granted).items():
            with self.subTest(view=name):
                response = client.get(url)
                self.assertEqual(response.status_code, 200, name)
        self.assertTrue(self.fake.calls)

    def test_a_superuser_is_not_refused(self):
        client = self.client_for(self.root)
        for name, url in self.urls_for(self.root).items():
            with self.subTest(view=name):
                self.assertEqual(client.get(url).status_code, 200, name)


class TestDenialShape(ViewAuthzTestCase):
    """A 403 the caller cannot parse is still a bug."""

    def test_the_json_api_refuses_in_json(self):
        client = self.client_for(self.ungranted)
        response = client.get(
            reverse("deployments:api_search_instances") + "?q=abc&environment=prod"
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertIn("prod", json.loads(response.content)["error"])

    def test_an_htmx_partial_refuses_with_a_fragment_not_a_page(self):
        draft = self.draft_for(self.ungranted)
        client = self.client_for(self.ungranted)
        response = client.get(
            reverse("deployments:api_dep_candidates", kwargs={"draft_id": draft.pk})
            + "?environment=prod&role=db"
        )
        self.assertEqual(response.status_code, 403)
        body = response.content.decode()
        self.assertIn("Access denied", body)
        # base.html would bring these; a fragment swapped into a div must not.
        self.assertNotIn("<html", body.lower())
        self.assertNotIn("<body", body.lower())


class TestMissingEnvironment(ViewAuthzTestCase):
    """Views that render a "pick an environment" hint must keep doing so."""

    def test_the_partials_defer_to_the_view_and_query_nothing(self):
        draft = self.draft_for(self.ungranted)
        client = self.client_for(self.ungranted)
        for url in (
            reverse(
                "deployments:api_search_instances_html", kwargs={"draft_id": draft.pk}
            )
            + "?q=abc",
            reverse("deployments:api_dep_candidates", kwargs={"draft_id": draft.pk})
            + "?role=db",
            reverse("deployments:changeset_bom_impact", kwargs={"draft_id": draft.pk}),
        ):
            with self.subTest(url=url):
                self.assertEqual(client.get(url).status_code, 200)
        self.assertEqual(self.fake.calls, [])

    def test_the_json_api_no_longer_falls_back_to_dev(self):
        # It used to default to environment="dev" and search an environment the
        # caller had not named.
        UserEnvironmentPermission.objects.create(
            user=self.ungranted, environment="dev", role="viewer"
        )
        client = self.client_for(self.ungranted)
        response = client.get(reverse("deployments:api_search_instances") + "?q=abc")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.fake.calls, [])


class TestEnvironmentCompare(ViewAuthzTestCase):
    """The compare pair, including the write that had no check at all."""

    def compare_url(self, from_env, to_env):
        return (
            reverse("deployments:environment_compare") + f"?from={from_env}&to={to_env}"
        )

    def test_the_read_reports_the_environment_it_refused(self):
        client = self.client_for(self.granted)
        response = client.get(self.compare_url("dev", "prod"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("target environment", response.content.decode())
        self.assertEqual(self.fake.calls, [])

    def test_a_superuser_compares_without_explicit_grants(self):
        client = self.client_for(self.root)
        response = client.get(self.compare_url("dev", "prod"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.fake.calls, ["compare_environments"])

    def test_the_changeset_write_refuses_an_unpermitted_source(self):
        client = self.client_for(self.granted)
        response = client.post(
            reverse("deployments:environment_compare_create_changeset"),
            {"from_env": "prod", "to_env": "dev", "name": "x", "selected": ["a"]},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.fake.calls, [])
        self.assertEqual(ChangeSetDraft.objects.filter(name="x").count(), 0)

    def test_the_changeset_write_refuses_an_unpermitted_target(self):
        client = self.client_for(self.granted)
        response = client.post(
            reverse("deployments:environment_compare_create_changeset"),
            {"from_env": "dev", "to_env": "prod", "name": "x", "selected": ["a"]},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.fake.calls, [])


class TestResourceList(ViewAuthzTestCase):
    def test_an_ungranted_environment_is_reported_and_not_queried(self):
        client = self.client_for(self.granted)
        response = client.get(
            reverse("deployments:resource_list") + "?environment=prod"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("don&#x27;t have view permission", response.content.decode())
        self.assertEqual(self.fake.calls, [])

    def test_a_superuser_queries_without_an_explicit_grant(self):
        client = self.client_for(self.root)
        response = client.get(
            reverse("deployments:resource_list") + "?environment=prod"
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("don&#x27;t have view permission", response.content.decode())
