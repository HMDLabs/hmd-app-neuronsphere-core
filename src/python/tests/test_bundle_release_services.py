"""Shaping bundle and release rows for the catalog views (NERD009 / NERD011).

Pure functions, no Django: what a release claims must never be louder than what
was proved, so the evidence level is tested exhaustively.
"""
import unittest

from deployments.services.bundle_detail import role_rows
from deployments.services.release_detail import (
    arrival_summary,
    carried_forward,
    evidence_level,
    pin_rows,
)


class TestRoleRows(unittest.TestCase):
    def test_sorted_by_role_and_flattened(self):
        rows = role_rows(
            {
                "eks-alb": {
                    "repo_class_name": "hmd-inf-eks-alb",
                    "required": "true",
                    "resource": {
                        "resource_namespace": "kubernetes.neuronsphere.io",
                        "resource_definition_name": "ingress-controller",
                        "version_spec": "~= 0.1",
                    },
                },
                "collector": {
                    "repo_class_name": "hmd-inf-otel-collector",
                    "required": "false",
                    "version_spec": "~= 0.1",
                    "tag_selector": {"tier": "gold"},
                    "provision": "false",
                    "dedicated": "true",
                    "bind": ["users", "creds"],
                },
            }
        )

        self.assertEqual([r["role"] for r in rows], ["collector", "eks-alb"])
        collector, alb = rows
        self.assertEqual(collector["repo_class_name"], "hmd-inf-otel-collector")
        self.assertFalse(collector["required"])
        self.assertEqual(collector["version_spec"], "~= 0.1")
        self.assertEqual(collector["tag_selector"], {"tier": "gold"})
        self.assertFalse(collector["provision"])
        self.assertTrue(collector["dedicated"])
        self.assertEqual(collector["bind"], ["users", "creds"])
        self.assertTrue(alb["required"])
        self.assertEqual(
            alb["resource"], "kubernetes.neuronsphere.io/ingress-controller ~= 0.1"
        )

    def test_defaults_provision_true_dedicated_false_and_bind_empty(self):
        [row] = role_rows({"db": {"repo_class_name": "x"}})
        self.assertTrue(row["provision"])
        self.assertFalse(row["dedicated"])
        self.assertEqual(row["bind"], [])
        self.assertTrue(row["required"])  # a role is required unless declared otherwise

    def test_a_single_bind_string_becomes_a_list(self):
        [row] = role_rows({"db": {"repo_class_name": "x", "bind": "users"}})
        self.assertEqual(row["bind"], ["users"])

    def test_none_and_empty_give_no_rows(self):
        self.assertEqual(role_rows(None), [])
        self.assertEqual(role_rows({}), [])


class TestEvidenceLevel(unittest.TestCase):
    def test_carried_forward_pins_are_partly_attested_even_if_released(self):
        rv = {
            "status": "released",
            "evidence": {"method": "manual", "carried_forward": [{"role": "db"}]},
        }
        self.assertEqual(evidence_level(rv), "partly_attested")

    def test_never_verified_when_anything_was_carried_forward(self):
        for status in ("verified", "released"):
            with self.subTest(status=status):
                rv = {"status": status, "evidence": {"carried_forward": ["x"]}}
                self.assertNotEqual(evidence_level(rv), "verified")

    def test_manual_note_is_attested(self):
        rv = {
            "status": "verified",
            "evidence": {"method": "manual", "carried_forward": []},
        }
        self.assertEqual(evidence_level(rv), "attested")

    def test_a_gated_apply_is_verified(self):
        for status in ("verified", "released"):
            with self.subTest(status=status):
                rv = {"status": status, "evidence": {"change_set_deployment": "csd-1"}}
                self.assertEqual(evidence_level(rv), "verified")

    def test_unproven_releases_have_no_level(self):
        for status in ("candidate", "verifying", "failed", "superseded"):
            with self.subTest(status=status):
                self.assertEqual(
                    evidence_level({"status": status, "evidence": {}}), "none"
                )

    def test_missing_evidence_is_tolerated(self):
        self.assertEqual(
            evidence_level({"status": "released", "evidence": None}), "verified"
        )
        self.assertEqual(evidence_level({"status": "candidate"}), "none")


class TestCarriedForward(unittest.TestCase):
    def test_returns_the_items_naming_pin_and_source_release(self):
        item = {
            "bundle": "telemetry",
            "role": "clickhouse",
            "repo_class_name": "hmd-inf-clickhouse",
            "version": "0.2.7",
            "from_release": "telemetry@0.1.0",
        }
        self.assertEqual(
            carried_forward({"evidence": {"carried_forward": [item]}}), [item]
        )

    def test_empty_when_absent(self):
        self.assertEqual(carried_forward({"evidence": None}), [])
        self.assertEqual(carried_forward({}), [])


class TestPinRows(unittest.TestCase):
    def test_joins_pins_with_artifact_path_and_digest_sorted_by_class(self):
        rv = {
            "pins": {"hmd-inf-clickhouse": "0.2.7", "hmd-inf-otel-collector": "0.1.40"},
            "artifacts": [
                {
                    "repo_class_name": "hmd-inf-otel-collector",
                    "version": "0.1.40",
                    "content_path": "repository:/otel/0.1.40/a.zip",
                    "digest": "sha256:abc",
                }
            ],
        }
        rows = pin_rows(rv)
        self.assertEqual(
            [r["repo_class_name"] for r in rows],
            ["hmd-inf-clickhouse", "hmd-inf-otel-collector"],
        )
        self.assertIsNone(rows[0]["content_path"])
        self.assertEqual(rows[1]["content_path"], "repository:/otel/0.1.40/a.zip")
        self.assertEqual(rows[1]["digest"], "sha256:abc")

    def test_a_class_pinned_at_several_versions_gives_a_row_each(self):
        rv = {
            "pins": {},
            "artifacts": [
                {"repo_class_name": "bucket", "version": "0.1.1"},
                {"repo_class_name": "bucket", "version": "0.1.2"},
            ],
        }
        self.assertEqual(
            [(r["repo_class_name"], r["version"]) for r in pin_rows(rv)],
            [("bucket", "0.1.1"), ("bucket", "0.1.2")],
        )

    def test_falls_back_to_the_pins_mapping_without_artifacts(self):
        rows = pin_rows({"pins": {"a": "1.0.0"}, "artifacts": None})
        self.assertEqual(
            [(r["repo_class_name"], r["version"]) for r in rows], [("a", "1.0.0")]
        )


class TestArrivalSummary(unittest.TestCase):
    def _report(self, *statuses, installed=False):
        return {
            "installed": installed,
            "entries": [
                {"repo_class_name": f"c{i}", "version": "1", "status": s}
                for i, s in enumerate(statuses)
            ],
        }

    def test_installed(self):
        s = arrival_summary(self._report("present", "present", installed=True))
        self.assertEqual(
            (s["state"], s["present"], s["total"], s["polling"]),
            ("installed", 2, 2, False),
        )

    def test_arriving_polls(self):
        s = arrival_summary(
            self._report("present", "awaiting_replication", "awaiting_registration")
        )
        self.assertEqual(
            (s["state"], s["present"], s["total"], s["polling"]),
            ("arriving", 1, 3, True),
        )

    def test_a_digest_mismatch_blocks_and_stops_polling(self):
        s = arrival_summary(
            self._report("present", "digest_mismatch", "awaiting_replication")
        )
        self.assertEqual((s["state"], s["polling"]), ("blocked", False))
        self.assertEqual(s["blocked"], 1)

    def test_no_report_means_not_received(self):
        for report in (None, {"installed": None, "entries": []}):
            with self.subTest(report=report):
                s = arrival_summary(report)
                self.assertEqual(
                    (s["state"], s["total"], s["polling"]), ("unknown", 0, False)
                )


if __name__ == "__main__":
    unittest.main()
