"""``build_capability_rows`` flattens a search_discovery envelope into the
one-row-per-capability shape the capability search table and the MCP
``search_capabilities`` tool share (NERD0013 / NERD004 SPEC005)."""
import unittest

from deployments.services.repo_class_detail import build_capability_rows


ENVELOPE = {
    "items": [
        {
            "repo_class_name": "hmd-cli-monitoring",
            "version": "1.2.0",
            "summary": "Ships log retention and metrics collection.",
            "score": 3,
            "matched_fields": ["capability.name"],
            "capabilities": [
                {
                    "name": "hmd monitoring rotate-logs",
                    "kind": "cli_command",
                    "description": "Rotates log files.",
                    "location": "src/python/monitoring/cli.py:40",
                },
                {
                    "name": "hmd monitoring status",
                    "kind": "cli_command",
                    "description": "",
                },
            ],
            "entry_points": [],
            "related_docs": [],
            "capability_count": 3,
        },
        {
            "repo_class_name": "hmd-vpc",
            "version": "0.9.1",
            "summary": "Provisions the base VPC.",
            "score": 2,
            "matched_fields": ["summary"],
            "capabilities": [],
            "entry_points": [],
            "related_docs": [],
            "capability_count": 0,
        },
    ],
    "total": 2,
    "limit": 50,
    "offset": 0,
}


class TestBuildCapabilityRows(unittest.TestCase):
    def test_one_row_per_matched_capability_in_envelope_order(self):
        rows = build_capability_rows(ENVELOPE)

        self.assertEqual(
            [(r["repo_class_name"], r["name"]) for r in rows],
            [
                ("hmd-cli-monitoring", "hmd monitoring rotate-logs"),
                ("hmd-cli-monitoring", "hmd monitoring status"),
            ],
        )
        first = rows[0]
        self.assertEqual(first["version"], "1.2.0")
        self.assertEqual(first["kind"], "cli_command")
        self.assertEqual(first["description"], "Rotates log files.")
        self.assertEqual(first["location"], "src/python/monitoring/cli.py:40")
        self.assertEqual(
            first["summary"], "Ships log retention and metrics collection."
        )
        # A capability without a location still renders a row.
        self.assertEqual(rows[1]["location"], "")

    def test_summary_only_hits_produce_no_rows(self):
        # hmd-vpc matched on its summary alone; it appears in the class list
        # the caller renders separately, never as a capability row.
        rows = build_capability_rows(ENVELOPE)
        self.assertFalse(any(r["repo_class_name"] == "hmd-vpc" for r in rows))

    def test_tolerates_missing_or_malformed_envelope(self):
        self.assertEqual(build_capability_rows(None), [])
        self.assertEqual(build_capability_rows({}), [])
        self.assertEqual(build_capability_rows({"items": "nope"}), [])
        self.assertEqual(
            build_capability_rows(
                {"items": [{"repo_class_name": "x", "capabilities": None}]}
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
