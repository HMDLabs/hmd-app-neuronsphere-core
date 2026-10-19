"""Bundle and release catalog views (NERD009 SPEC001/004, NERD011 SPEC001/002/005).

Platform-wide reads: ``login_required`` only, nothing environment-scoped, nothing
cached for releases, and no premium URL named anywhere in the core templates.
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


BUNDLES = [
    {
        "bundle_name": "telemetry",
        "versions": ["0.2.0", "0.1.0"],
        "latest_version": "0.2.0",
        "summary": "OTel collector, ClickHouse and HyperDX.",
    }
]

BUNDLE_VERSION = {
    "bundle_name": "telemetry",
    "version": "0.2.0",
    "source_repo_class_name": "hmd-bundle-core",
    "source_repo_class_version": "0.2.0",
    "config_schema": {
        "type": "object",
        "properties": {"retention_days": {"type": "integer"}},
    },
    "default_configuration": {"retention_days": 7},
    "roles": {
        "collector": {
            "repo_class_name": "hmd-inf-otel-collector",
            "required": "true",
            "version_spec": "~= 0.1",
            "tag_selector": {"tier": "gold"},
        },
        "ingress": {
            "repo_class_name": "hmd-inf-eks-alb",
            "required": "false",
            "provision": "false",
            "resource": {
                "resource_namespace": "kubernetes.neuronsphere.io",
                "resource_definition_name": "ingress-controller",
                "version_spec": "~= 0.1",
            },
        },
    },
    "discovery": {"summary": "OTel collector, ClickHouse and HyperDX."},
}

RELEASES = [
    {
        "release_name": "telemetry",
        "kind": "bundle",
        "versions": ["0.2.0", "0.1.0"],
        "newest_by_status": {"verified": "0.2.0", "released": "0.1.0"},
        "newest_installed": "0.1.0",
    },
    {
        "release_name": "core",
        "kind": "platform",
        "versions": ["0.1.0"],
        "newest_by_status": {"released": "0.1.0"},
        "newest_installed": None,
    },
]

RELEASE_VERSION = {
    "release_name": "telemetry",
    "version": "0.2.0",
    "status": "verified",
    "evidence": {
        "method": "manual",
        "by": "alice",
        "note": "Ran the telemetry smoke test in dev.",
        "environment": "dev",
        "carried_forward": [],
    },
    "pins": {"hmd-inf-clickhouse": "0.2.7", "hmd-inf-otel-collector": "0.1.40"},
    "artifacts": [
        {
            "repo_class_name": "hmd-inf-otel-collector",
            "version": "0.1.40",
            "content_path": "repository:/otel/0.1.40/a.zip",
            "digest": "sha256:abc",
        }
    ],
    "notes": [
        {
            "repo_class_name": "hmd-inf-clickhouse",
            "from": "0.2.6",
            "to": "0.2.7",
            "lines": ["- fix: x"],
        }
    ],
    "install_report": {
        "installed": False,
        "entries": [
            {
                "repo_class_name": "hmd-inf-clickhouse",
                "version": "0.2.7",
                "status": "present",
            },
            {
                "repo_class_name": "hmd-inf-otel-collector",
                "version": "0.1.40",
                "status": "awaiting_replication",
            },
        ],
    },
    "includes": [{"release_name": "telemetry", "version": "0.2.0"}],
}


class FakeClient:
    def __init__(self):
        self.calls = []
        self.responses = {
            "list_bundles": FakeResponse(BUNDLES),
            "list_bundle_versions": FakeResponse([BUNDLE_VERSION]),
            "get_bundle_version": FakeResponse(BUNDLE_VERSION),
            "list_releases": FakeResponse(RELEASES),
            "list_release_versions": FakeResponse(
                [
                    {
                        "release_name": "telemetry",
                        "version": "0.2.0",
                        "status": "verified",
                        "installed": None,
                    },
                    {
                        "release_name": "telemetry",
                        "version": "0.1.0",
                        "status": "released",
                        "installed": True,
                    },
                ]
            ),
            "get_release_version": FakeResponse(RELEASE_VERSION),
            "release_install_status": FakeResponse(RELEASE_VERSION["install_report"]),
        }

    def __getattr__(self, name):
        if name not in self.responses:
            raise AttributeError(name)

        def call(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return self.responses[name]

        return call

    def names(self):
        return [c[0] for c in self.calls]


class CatalogTestCase(unittest.TestCase):
    def setUp(self):
        self.user = User.objects.create_user("viewer", password="pw")
        self.fake = FakeClient()
        patcher = mock.patch(
            "deployments.views.get_api_client_for_request", return_value=self.fake
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = Client()
        self.client.force_login(self.user)

    def body(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, url)
        return response.content.decode()


URLS = {
    "bundle_list": ("deployments:bundle_list", {}),
    "bundle_detail": ("deployments:bundle_detail", {"bundle_name": "telemetry"}),
    "bundle_version_detail": (
        "deployments:bundle_version_detail",
        {"bundle_name": "telemetry", "version": "0.2.0"},
    ),
    "release_list": ("deployments:release_list", {}),
    "release_version_detail": (
        "deployments:release_version_detail",
        {"release_name": "telemetry", "version": "0.2.0"},
    ),
    "release_install_status_partial": (
        "deployments:release_install_status_partial",
        {"release_name": "telemetry", "version": "0.2.0"},
    ),
}


class TestLoginOnly(CatalogTestCase):
    def test_anonymous_users_are_sent_to_login_and_nothing_is_fetched(self):
        for name, (route, kwargs) in URLS.items():
            with self.subTest(view=name):
                response = Client().get(reverse(route, kwargs=kwargs))
                self.assertEqual(response.status_code, 302)
        self.assertEqual(self.fake.calls, [])

    def test_a_logged_in_user_without_any_environment_grant_can_read_them(self):
        for name, (route, kwargs) in URLS.items():
            with self.subTest(view=name):
                self.assertEqual(
                    self.client.get(reverse(route, kwargs=kwargs)).status_code, 200
                )


class TestBundleViews(CatalogTestCase):
    def test_list_shows_bundles_with_latest_version_and_summary(self):
        body = self.body(reverse("deployments:bundle_list"))
        self.assertEqual(self.fake.names(), ["list_bundles"])
        self.assertIn("telemetry", body)
        self.assertIn("0.2.0", body)
        self.assertIn("OTel collector, ClickHouse and HyperDX.", body)
        self.assertIn(
            reverse("deployments:bundle_detail", kwargs={"bundle_name": "telemetry"}),
            body,
        )

    def test_list_search_filters_client_side(self):
        body = self.body(reverse("deployments:bundle_list") + "?search=zzz")
        self.assertNotIn(
            reverse("deployments:bundle_detail", kwargs={"bundle_name": "telemetry"}),
            body,
        )
        self.assertIn("No bundles found", body)

    def test_list_error_renders_a_message_not_a_500(self):
        self.fake.responses["list_bundles"] = FakeResponse(
            None, success=False, error="down"
        )
        body = self.body(reverse("deployments:bundle_list"))
        self.assertIn("down", body)

    def test_detail_lists_versions_linking_to_each(self):
        body = self.body(
            reverse("deployments:bundle_detail", kwargs={"bundle_name": "telemetry"})
        )
        self.assertEqual(self.fake.names(), ["list_bundle_versions"])
        self.assertIn(
            reverse(
                "deployments:bundle_version_detail",
                kwargs={"bundle_name": "telemetry", "version": "0.2.0"},
            ),
            body,
        )

    def test_version_detail_renders_the_role_table_and_config_schema(self):
        body = self.body(
            reverse(
                "deployments:bundle_version_detail",
                kwargs={"bundle_name": "telemetry", "version": "0.2.0"},
            )
        )
        self.assertEqual(
            self.fake.calls[0][0:2], ("get_bundle_version", ("telemetry",))
        )
        self.assertEqual(self.fake.calls[0][2], {"version": "0.2.0"})
        for text in (
            "hmd-inf-otel-collector",
            "~= 0.1",
            "kubernetes.neuronsphere.io/ingress-controller",
            "tier",
            "retention_days",
            "hmd-bundle-core",
        ):
            self.assertIn(text, body)

    def test_version_detail_error(self):
        self.fake.responses["get_bundle_version"] = FakeResponse(
            None, success=False, error="No version found for bundle telemetry : 9.9.9."
        )
        body = self.body(
            reverse(
                "deployments:bundle_version_detail",
                kwargs={"bundle_name": "telemetry", "version": "9.9.9"},
            )
        )
        self.assertIn("No version found for bundle telemetry : 9.9.9.", body)


class TestReleaseViews(CatalogTestCase):
    def test_list_distinguishes_bundle_and_platform_releases_and_shows_status(self):
        body = self.body(reverse("deployments:release_list"))
        self.assertEqual(self.fake.names(), ["list_releases"])
        self.assertIn("Platform", body)
        self.assertIn("Bundle", body)
        self.assertIn("verified", body)
        self.assertIn("released", body)
        self.assertIn(
            reverse(
                "deployments:release_version_detail",
                kwargs={"release_name": "telemetry", "version": "0.2.0"},
            ),
            body,
        )

    def _detail(self, **overrides):
        self.fake.responses["get_release_version"] = FakeResponse(
            {**RELEASE_VERSION, **overrides}
        )
        return self.body(
            reverse(
                "deployments:release_version_detail",
                kwargs={"release_name": "telemetry", "version": "0.2.0"},
            )
        )

    def test_detail_shows_evidence_note_pins_notes_and_arrival(self):
        body = self._detail()
        self.assertIn("Attested", body)
        self.assertIn("Ran the telemetry smoke test in dev.", body)
        self.assertIn("alice", body)
        self.assertIn("hmd-inf-otel-collector", body)
        self.assertIn("sha256:abc", body)
        self.assertIn("fix: x", body)
        self.assertIn("1 of 2", body)  # arrival summary
        self.assertIn(
            reverse(
                "deployments:release_install_status_partial",
                kwargs={"release_name": "telemetry", "version": "0.2.0"},
            ),
            body,
        )

    def test_carried_forward_pins_are_named_and_the_badge_is_never_verified(self):
        carried = [
            {
                "bundle": "telemetry",
                "role": "clickhouse",
                "repo_class_name": "hmd-inf-clickhouse",
                "version": "0.2.7",
                "from_release": "telemetry@0.1.0",
            }
        ]
        body = self._detail(
            status="released",
            evidence={"method": "manual", "note": "n", "carried_forward": carried},
        )
        self.assertIn("Partly attested", body)
        self.assertNotIn(">Verified<", body)
        self.assertIn("telemetry@0.1.0", body)
        self.assertIn("hmd-inf-clickhouse", body)

    def test_a_gated_apply_is_labelled_verified(self):
        body = self._detail(
            evidence={"change_set_deployment": "csd-1", "carried_forward": []}
        )
        self.assertIn("Verified", body)

    def test_platform_release_links_to_included_releases(self):
        body = self._detail(
            includes=[{"release_name": "telemetry", "version": "0.1.0"}],
            release_name="core",
        )
        self.assertIn(
            reverse(
                "deployments:release_version_detail",
                kwargs={"release_name": "telemetry", "version": "0.1.0"},
            ),
            body,
        )

    def test_arriving_install_polls_until_installed(self):
        body = self._detail()
        self.assertIn("hx-trigger", body)

        installed = {
            "installed": True,
            "entries": [{"repo_class_name": "a", "version": "1", "status": "present"}],
        }
        self.assertNotIn("hx-trigger", self._detail(install_report=installed))

    def test_status_partial_recomputes_and_stops_polling_once_installed(self):
        url = reverse(
            "deployments:release_install_status_partial",
            kwargs={"release_name": "telemetry", "version": "0.2.0"},
        )
        arriving = self.body(url)
        self.assertEqual(self.fake.calls[-1][0], "release_install_status")
        self.assertEqual(self.fake.calls[-1][2].get("refresh"), True)
        self.assertIn("hx-trigger", arriving)

        self.fake.responses["release_install_status"] = FakeResponse(
            {
                "installed": True,
                "entries": [
                    {"repo_class_name": "a", "version": "1", "status": "present"}
                ],
            }
        )
        self.assertNotIn("hx-trigger", self.body(url))

    def test_a_digest_mismatch_is_shown_as_blocked(self):
        self.fake.responses["release_install_status"] = FakeResponse(
            {
                "installed": False,
                "entries": [
                    {
                        "repo_class_name": "a",
                        "version": "1",
                        "status": "digest_mismatch",
                    }
                ],
            }
        )
        url = reverse(
            "deployments:release_install_status_partial",
            kwargs={"release_name": "telemetry", "version": "0.2.0"},
        )
        body = self.body(url)
        self.assertIn("Blocked", body)
        self.assertNotIn("hx-trigger", body)

    def test_detail_error_shows_the_service_sentence(self):
        self.fake.responses["get_release_version"] = FakeResponse(
            None, success=False, error="Release, nope, not found."
        )
        body = self.body(
            reverse(
                "deployments:release_version_detail",
                kwargs={"release_name": "nope", "version": "1.0.0"},
            )
        )
        self.assertIn("Release, nope, not found.", body)

    def test_core_pages_name_no_premium_url(self):
        for name in ("release_list", "release_version_detail"):
            route, kwargs = URLS[name]
            self.assertNotIn(
                "deployments_premium", self.body(reverse(route, kwargs=kwargs))
            )


class TestSidebar(CatalogTestCase):
    def test_entries_link_and_mark_the_active_section(self):
        body = self.body(reverse("deployments:bundle_list"))
        self.assertIn(reverse("deployments:bundle_list"), body)
        self.assertIn(reverse("deployments:release_list"), body)
        self.assertIn("Bundles", body)
        self.assertIn("Releases", body)


if __name__ == "__main__":
    unittest.main()
