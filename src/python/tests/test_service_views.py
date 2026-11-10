"""The service view browser (NERD007): discovery, permission filtering, the
proxy, and the pages.

A deployed service publishes a ``ui.neuronsphere.io/view-set`` Resource
(hmd-ms-deployment NERD0003); the browser lists those per environment, shows
each caller only the views their groups allow, and proxies the partials with
the caller's own token. Nothing here talks to a network: the deployment client
and the upstream HTTP transport are fakes.
"""

import json
import unittest
from unittest import mock

import httpx
import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, override_settings

from deployments.models import UserEnvironmentPermission
from deployments.services.api_client import APIResponse
from ns_service_views import discovery, permissions, proxy
from ns_service_views.discovery import VIEW_SET_TAG, ServiceViews

READER = "Dev Ms Identity Reader"
ADMIN = "Dev Ms Identity Admin"

IDENTITY = {
    "resource_name": "ms-identity-svc-aaa-views",
    "output": {
        "service": "hmd-ms-identity",
        "instance": "ms-identity",
        "version": "0.2.1",
        "base_url": "https://ms-identity.example.com",
        "auth_mode": "passthrough",
        "views": [
            {
                "id": "users-list",
                "title": "Users",
                "path": "/views/users",
                "required_permissions": ["identity.read"],
                "group": "Identity > People",
                "order": 10,
                "icon": "users",
            },
            {
                "id": "users-create",
                "title": "Create user",
                "path": "/views/users/new",
                "required_permissions": ["identity.admin"],
                "group": "Identity > People",
                "order": 20,
            },
        ],
        "group_permissions": {
            READER: ["identity.read"],
            ADMIN: ["identity.read", "identity.admin"],
        },
    },
}


class FakeClient:
    def __init__(self, by_environment=None, failing=()):
        self.by_environment = by_environment or {"dev": [IDENTITY]}
        self.failing = set(failing)
        self.selector_calls = []

    def find_resources_by_selector(self, tags, environment=None):
        self.selector_calls.append((dict(tags), environment))
        if environment in self.failing:
            return APIResponse(success=False, data=None, error="boom", status_code=500)
        return APIResponse(success=True, data=self.by_environment.get(environment, []))


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


# -- discovery ------------------------------------------------------------------


def test_discovery_selects_view_sets_by_tag_in_the_environment():
    client = FakeClient()
    services = discovery.discover(client, "dev")

    assert client.selector_calls == [({VIEW_SET_TAG[0]: VIEW_SET_TAG[1]}, "dev")]
    (svc,) = services
    assert svc.instance == "ms-identity"
    assert svc.base_url == "https://ms-identity.example.com"
    assert [v["id"] for v in svc.views] == ["users-list", "users-create"]


def test_malformed_view_sets_and_views_are_skipped_not_fatal():
    bad_set = {"resource_name": "x", "output": {"service": "x"}}
    bad_view = json.loads(json.dumps(IDENTITY))
    bad_view["output"]["views"].append({"id": "no-path", "title": "No path"})
    bad_view["output"]["views"].append(
        {"id": "outside", "title": "Outside", "path": "/api/users"}
    )
    services = discovery.discover(FakeClient({"dev": [bad_set, bad_view]}), "dev")

    (svc,) = services
    assert [v["id"] for v in svc.views] == ["users-list", "users-create"]


def test_a_failing_query_is_an_empty_inventory():
    assert discovery.discover(FakeClient(failing={"dev"}), "dev") == []


def test_inventory_is_cached_per_environment_and_can_be_invalidated():
    client = FakeClient()
    discovery.inventory(client, "dev")
    discovery.inventory(client, "dev")
    assert len(client.selector_calls) == 1

    discovery.invalidate("dev")
    discovery.inventory(client, "dev")
    assert len(client.selector_calls) == 2


# -- permissions -----------------------------------------------------------------

# The same cases hmd-lib-auth's permissions_for is tested against: the GUI's
# copy and the services' must resolve identically (NERD007 SPEC005).
PARITY = [
    ([READER, ADMIN], {"identity.read", "identity.admin"}),
    (["Prod Analyst", "Everyone"], set()),
    (["dev ms identity admin", "Dev Ms Identity"], set()),
    ([], set()),
    (None, set()),
    (READER, {"identity.read"}),
]


@pytest.mark.parametrize("groups, expected", PARITY)
def test_permissions_for_matches_hmd_lib_auth(groups, expected):
    assert (
        permissions.permissions_for(groups, IDENTITY["output"]["group_permissions"])
        == expected
    )


def _svc():
    return ServiceViews.from_output(IDENTITY["output"])


def test_reader_sees_only_the_views_their_groups_allow():
    visible = permissions.visible_views(_svc(), [READER], enforce=True)
    assert [v["id"] for v in visible] == ["users-list"]


def test_admin_sees_every_view():
    visible = permissions.visible_views(_svc(), [ADMIN], enforce=True)
    assert [v["id"] for v in visible] == ["users-list", "users-create"]


def test_without_sso_nothing_is_filtered():
    # As a service skips its check under AUTHORIZATION=NONE locally.
    visible = permissions.visible_views(_svc(), [], enforce=False)
    assert [v["id"] for v in visible] == ["users-list", "users-create"]


# -- proxy helpers ----------------------------------------------------------------


def test_asset_tags_are_stripped_from_partials():
    html = '<div>ok</div><script src="x.js"></script><SCRIPT>alert(1)</SCRIPT>'
    html += '<link rel="stylesheet" href="y.css"><style>.a{}</style><p>end</p>'
    assert proxy.strip_asset_tags(html) == "<div>ok</div><p>end</p>"


# -- pages and the proxy, through Django -------------------------------------------


class ServiceViewsTestCase(unittest.TestCase):
    def setUp(self):
        self.user = User.objects.create_user("pat", password="pw")
        UserEnvironmentPermission.objects.create(
            user=self.user, environment="dev", role="viewer"
        )
        self.outsider = User.objects.create_user("outsider", password="pw")
        self.fake = FakeClient()
        self.groups = [READER]
        self.upstream_requests = []
        self.upstream = lambda request: httpx.Response(
            200, html="<ul><li>ada</li></ul><script>x()</script>"
        )

        for target in (
            "ns_service_views.views.get_api_client_for_request",
            "deployments.context_processors.get_api_client_for_request",
        ):
            p = mock.patch(target, return_value=self.fake)
            p.start()
            self.addCleanup(p.stop)
        for target in (
            "deployments.context_processors.get_user_environments",
            "ns_service_views.views.get_user_environments",
        ):
            p = mock.patch(target, return_value=["dev"])
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch(
            "ns_service_views.views.user_groups", side_effect=lambda user: self.groups
        )
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch(
            "ns_service_views.views.user_bearer_token", return_value="user-token"
        )
        p.start()
        self.addCleanup(p.stop)

        def handler(request):
            self.upstream_requests.append(request)
            return self.upstream(request)

        p = mock.patch.object(
            proxy, "transport", side_effect=lambda: httpx.MockTransport(handler)
        )
        p.start()
        self.addCleanup(p.stop)

        self.client = Client()
        self.client.force_login(self.user)

    # pages

    @override_settings(SERVICE_VIEWS_ENFORCE_PERMISSIONS=True)
    def test_service_list_shows_services_with_a_visible_view(self):
        response = self.client.get("/services/dev/")
        assert response.status_code == 200
        assert b"ms-identity" in response.content
        assert b"Users" in response.content

    @override_settings(SERVICE_VIEWS_ENFORCE_PERMISSIONS=True)
    def test_service_page_lists_only_visible_views_and_has_the_mount_point(self):
        response = self.client.get("/services/dev/ms-identity/")
        body = response.content.decode()
        assert response.status_code == 200
        assert 'id="ns-service-view"' in body
        assert "Users" in body
        assert "Create user" not in body
        assert 'hx-get="/services/dev/ms-identity/views/users"' in body

    def test_pages_require_environment_access(self):
        self.client.force_login(self.outsider)
        assert self.client.get("/services/dev/").status_code == 403
        assert self.client.get("/services/dev/ms-identity/").status_code == 403
        assert (
            self.client.get("/services/dev/ms-identity/views/users").status_code == 403
        )

    def test_unknown_service_page_is_404(self):
        assert self.client.get("/services/dev/nope/").status_code == 404

    # proxy

    @override_settings(SERVICE_VIEWS_ENFORCE_PERMISSIONS=True)
    def test_proxy_forwards_with_the_users_token_and_strips_assets(self):
        response = self.client.get("/services/dev/ms-identity/views/users?page=2")

        assert response.status_code == 200
        assert response["X-NS-Service"] == "ms-identity"
        assert response.content.decode() == "<ul><li>ada</li></ul>"
        (sent,) = self.upstream_requests
        assert str(sent.url) == "https://ms-identity.example.com/views/users?page=2"
        assert sent.headers["Authorization"] == "Bearer user-token"

    @override_settings(SERVICE_VIEWS_ENFORCE_PERMISSIONS=True)
    def test_proxy_forwards_posted_forms(self):
        self.groups = [ADMIN]
        self.client.post(
            "/services/dev/ms-identity/views/users/new", {"email": "a@b.c"}
        )

        (sent,) = self.upstream_requests
        assert sent.method == "POST"
        assert b"email=a%40b.c" in sent.content

    @override_settings(SERVICE_VIEWS_ENFORCE_PERMISSIONS=True)
    def test_proxy_refuses_a_view_the_users_groups_do_not_allow(self):
        response = self.client.get("/services/dev/ms-identity/views/users/new")

        assert response.status_code == 403
        assert b"identity.admin" in response.content
        assert self.upstream_requests == []

    def test_proxy_refuses_paths_the_inventory_does_not_list(self):
        for path in (
            "/services/dev/ms-identity/views/secret",
            "/services/dev/elsewhere/views/users",
        ):
            assert self.client.get(path).status_code == 404
        assert self.upstream_requests == []

    def test_oversized_responses_are_refused(self):
        self.upstream = lambda request: httpx.Response(
            200, html="x" * (proxy.MAX_RESPONSE_BYTES + 1)
        )
        response = self.client.get("/services/dev/ms-identity/views/users")

        assert response.status_code == 502
        assert b"too large" in response.content

    def test_upstream_errors_become_fragments(self):
        self.upstream = lambda request: httpx.Response(500, text="boom")
        response = self.client.get("/services/dev/ms-identity/views/users")
        assert response.status_code == 502
        assert b"<html" not in response.content.lower()

        def unreachable(request):
            raise httpx.ConnectError("nope")

        self.upstream = unreachable
        response = self.client.get("/services/dev/ms-identity/views/users")
        assert response.status_code == 502
        assert b"unreachable" in response.content

    def test_service_403_and_404_pass_through(self):
        self.upstream = lambda request: httpx.Response(403, html="<p>no</p>")
        response = self.client.get("/services/dev/ms-identity/views/users")
        assert response.status_code == 403
        assert response.content == b"<p>no</p>"
