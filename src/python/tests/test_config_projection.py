"""Unit tests for the effective-configuration projections.

Pure shaping, no client and no Django -- the two knobs that let a caller narrow
a several-hundred-key configuration before it is returned.
"""
import unittest

from deployments.services.config_projection import (
    ConfigPathError,
    config_key_outline,
    project_config_path,
)

SAMPLE = {
    "database": {"host": "db.internal", "port": 5432, "ssl": True},
    "replicas": 3,
    "dependencies": [
        {"instance_name": "base-vpc", "role": "vpc"},
        {"instance_name": "k8s", "role": "cluster"},
    ],
    "notes": None,
}


class TestProjectConfigPath(unittest.TestCase):
    def test_an_empty_path_returns_the_whole_configuration(self):
        for path in ("", None, "   ", "."):
            with self.subTest(path=path):
                self.assertIs(project_config_path(SAMPLE, path), SAMPLE)

    def test_a_dotted_path_walks_nested_mappings(self):
        self.assertEqual(project_config_path(SAMPLE, "database.host"), "db.internal")
        self.assertEqual(project_config_path(SAMPLE, "database.port"), 5432)

    def test_a_numeric_segment_indexes_a_list(self):
        self.assertEqual(
            project_config_path(SAMPLE, "dependencies.1.instance_name"), "k8s"
        )

    def test_a_missing_key_reports_what_was_available(self):
        with self.assertRaises(ConfigPathError) as ctx:
            project_config_path(SAMPLE, "database.hostname")
        self.assertEqual(ctx.exception.segment, "hostname")
        self.assertEqual(ctx.exception.available, ["host", "port", "ssl"])

    def test_an_out_of_range_index_reports_the_range(self):
        with self.assertRaises(ConfigPathError) as ctx:
            project_config_path(SAMPLE, "dependencies.9")
        self.assertEqual(ctx.exception.available, ["0..1"])

    def test_descending_into_a_scalar_fails_rather_than_returning_it(self):
        with self.assertRaises(ConfigPathError):
            project_config_path(SAMPLE, "replicas.value")


class TestConfigKeyOutline(unittest.TestCase):
    def test_values_are_replaced_by_their_types(self):
        outline = config_key_outline(SAMPLE)
        self.assertEqual(
            outline,
            {
                "database": "object (3 keys)",
                "dependencies": "array (2 items)",
                "notes": "null",
                "replicas": "number",
            },
        )

    def test_booleans_are_not_reported_as_numbers(self):
        self.assertEqual(config_key_outline({"ssl": True})["ssl"], "boolean")

    def test_a_non_mapping_reports_only_its_own_type(self):
        self.assertEqual(config_key_outline([1, 2, 3]), {"_type": "array (3 items)"})


if __name__ == "__main__":
    unittest.main()
