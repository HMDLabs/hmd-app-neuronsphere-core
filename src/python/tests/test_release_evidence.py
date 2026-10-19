"""Tests and attestation behind a release version (NERD011 SPEC002).

Real ``evidence.tests`` / ``evidence.attestation`` always win. The demo stand-ins
appear only with ``RELEASE_DEMO_EVIDENCE`` on, are deterministic per release
version (so a publisher and a customer GUI show the same thing), and are always
marked as demo data.
"""
import unittest
from unittest import mock

from django.contrib.auth.models import User
from django.test import Client, override_settings
from django.urls import reverse

from deployments.services.release_evidence import release_evidence

RELEASED = {
    "release_name": "telemetry",
    "version": "2026.1009.3",
    "status": "released",
    "evidence": {
        "method": "manual",
        "by": "demo",
        "note": "smoke-tested in relpub",
        "environment": "relpub",
        "at": "2026-10-09T14:39:01+00:00",
    },
    "pins": {"hmd-inf-clickhouse": "0.2.0", "hmd-inf-otel-collector": "0.1.0"},
    "artifacts": [
        {"repo_class_name": "hmd-inf-clickhouse", "version": "0.2.0", "digest": None},
        {
            "repo_class_name": "hmd-inf-otel-collector",
            "version": "0.1.0",
            "digest": "sha256:abc",
        },
    ],
}


class TestReleaseEvidence(unittest.TestCase):
    @override_settings(RELEASE_DEMO_EVIDENCE=False)
    def test_nothing_is_invented_when_the_demo_flag_is_off(self):
        result = release_evidence(RELEASED)
        self.assertEqual(result["tests"], [])
        self.assertIsNone(result["attestation"])
        self.assertFalse(result["demo"])

    @override_settings(RELEASE_DEMO_EVIDENCE=True)
    def test_recorded_evidence_wins_over_the_demo(self):
        detail = {
            **RELEASED,
            "evidence": {
                **RELEASED["evidence"],
                "tests": [{"suite": "real", "passed": 2, "failed": 0, "skipped": 0}],
                "attestation": {"signed_by": "ci"},
            },
        }
        result = release_evidence(detail)
        self.assertFalse(result["demo"])
        self.assertEqual([t["suite"] for t in result["tests"]], ["real"])
        self.assertEqual(result["attestation"]["signed_by"], "ci")
        self.assertEqual(result["summary"]["passed"], 2)

    @override_settings(RELEASE_DEMO_EVIDENCE=True)
    def test_demo_has_a_suite_per_pin_plus_an_end_to_end_suite_all_passing(self):
        result = release_evidence(RELEASED)
        self.assertTrue(result["demo"])
        suites = [t["suite"] for t in result["tests"]]
        self.assertEqual(
            suites,
            [
                "hmd-inf-clickhouse 0.2.0 acceptance",
                "hmd-inf-otel-collector 0.1.0 acceptance",
                "telemetry end-to-end",
            ],
        )
        self.assertTrue(all(t["outcome"] == "passed" for t in result["tests"]))
        self.assertTrue(all(t["environment"] == "relpub" for t in result["tests"]))
        self.assertEqual(result["summary"]["failed"], 0)
        self.assertEqual(
            result["summary"]["passed"], sum(t["passed"] for t in result["tests"])
        )

    @override_settings(RELEASE_DEMO_EVIDENCE=True)
    def test_demo_is_deterministic_per_release_version(self):
        self.assertEqual(release_evidence(RELEASED), release_evidence(RELEASED))
        other = release_evidence({**RELEASED, "version": "2026.1009.4"})
        self.assertNotEqual(
            other["attestation"]["subject_digest"],
            release_evidence(RELEASED)["attestation"]["subject_digest"],
        )

    @override_settings(RELEASE_DEMO_EVIDENCE=True)
    def test_demo_attestation_signs_the_pins_by_whoever_cut_it(self):
        attestation = release_evidence(RELEASED)["attestation"]
        self.assertEqual(
            attestation["subject"], "release:/telemetry/2026.1009.3/release.json"
        )
        self.assertTrue(attestation["subject_digest"].startswith("sha256:"))
        self.assertEqual(attestation["signed_by"], "demo")
        self.assertEqual(attestation["verification"], "valid")
        self.assertEqual(
            [(m["repo_class_name"], m["version"]) for m in attestation["materials"]],
            [("hmd-inf-clickhouse", "0.2.0"), ("hmd-inf-otel-collector", "0.1.0")],
        )
        # A digest the release recorded is kept, never replaced by a made-up one.
        self.assertEqual(attestation["materials"][1]["digest"], "sha256:abc")

    @override_settings(RELEASE_DEMO_EVIDENCE=True)
    def test_a_candidate_has_tests_not_run_and_no_signature(self):
        result = release_evidence({**RELEASED, "status": "candidate"})
        self.assertTrue(all(t["outcome"] == "not_run" for t in result["tests"]))
        self.assertIsNone(result["attestation"])

    @override_settings(RELEASE_DEMO_EVIDENCE=True)
    def test_a_failed_release_shows_a_failing_end_to_end_suite(self):
        result = release_evidence({**RELEASED, "status": "failed"})
        self.assertEqual(result["tests"][-1]["outcome"], "failed")
        self.assertEqual(result["tests"][-1]["failed"], 1)
        self.assertIsNone(result["attestation"])


class TestReleaseDetailShowsEvidence(unittest.TestCase):
    def setUp(self):
        from tests.test_bundle_release_views import FakeClient, FakeResponse

        self.user = User.objects.create_user("ev-viewer", password="pw")
        self.fake = FakeClient()
        self.fake.responses["get_release_version"] = FakeResponse(RELEASED)
        patcher = mock.patch(
            "deployments.views.get_api_client_for_request", return_value=self.fake
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.user.delete)
        self.client = Client()
        self.client.force_login(self.user)
        self.url = reverse(
            "deployments:release_version_detail",
            kwargs={"release_name": "telemetry", "version": "2026.1009.3"},
        )

    @override_settings(RELEASE_DEMO_EVIDENCE=True)
    def test_tests_and_attestation_render_marked_as_demo_data(self):
        body = self.client.get(self.url).content.decode()
        self.assertIn("Tests", body)
        self.assertIn("telemetry end-to-end", body)
        self.assertIn("Attestation", body)
        self.assertIn("release:/telemetry/2026.1009.3/release.json", body)
        self.assertIn("Demo data", body)

    @override_settings(RELEASE_DEMO_EVIDENCE=False)
    def test_without_evidence_the_page_says_so_and_claims_nothing(self):
        body = self.client.get(self.url).content.decode()
        self.assertNotIn("Demo data", body)
        self.assertNotIn("telemetry end-to-end", body)
        self.assertIn("No test runs recorded", body)
        self.assertIn("Not signed", body)
