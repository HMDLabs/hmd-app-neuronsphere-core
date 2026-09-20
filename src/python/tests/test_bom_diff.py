"""Unit tests for BOM diff and instance mapping utilities."""
import importlib.util
import os
import sys
import unittest

# Import bom_diff directly to avoid Django-dependent __init__.py in the services package
_bom_diff_path = os.path.join(
    os.path.dirname(__file__),
    "..",
    "deployments",
    "services",
    "bom_diff.py",
)
_spec = importlib.util.spec_from_file_location("bom_diff", _bom_diff_path)
_bom_diff = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bom_diff)

compute_bom_impact = _bom_diff.compute_bom_impact
compute_dependency_diff = _bom_diff.compute_dependency_diff
compute_environment_diff = _bom_diff.compute_environment_diff
compute_json_diff = _bom_diff.compute_json_diff
summarize_impact = _bom_diff.summarize_impact


class TestComputeJsonDiff(unittest.TestCase):
    def test_no_changes(self):
        result = compute_json_diff({"a": 1, "b": 2}, {"a": 1, "b": 2})
        self.assertEqual(result, {"added": {}, "removed": {}, "changed": {}})

    def test_added_keys(self):
        result = compute_json_diff({"a": 1}, {"a": 1, "b": 2, "c": 3})
        self.assertEqual(result["added"], {"b": 2, "c": 3})
        self.assertEqual(result["removed"], {})
        self.assertEqual(result["changed"], {})

    def test_removed_keys(self):
        result = compute_json_diff({"a": 1, "b": 2}, {"a": 1})
        self.assertEqual(result["removed"], {"b": 2})
        self.assertEqual(result["added"], {})

    def test_changed_values(self):
        result = compute_json_diff({"a": 1, "b": "old"}, {"a": 1, "b": "new"})
        self.assertEqual(result["changed"], {"b": {"old": "old", "new": "new"}})

    def test_mixed_changes(self):
        result = compute_json_diff(
            {"keep": 1, "change": "v1", "remove": True},
            {"keep": 1, "change": "v2", "add": "new"},
        )
        self.assertEqual(result["added"], {"add": "new"})
        self.assertEqual(result["removed"], {"remove": True})
        self.assertEqual(result["changed"], {"change": {"old": "v1", "new": "v2"}})

    def test_empty_dicts(self):
        result = compute_json_diff({}, {})
        self.assertEqual(result, {"added": {}, "removed": {}, "changed": {}})

    def test_none_inputs(self):
        result = compute_json_diff(None, {"a": 1})
        self.assertEqual(result["added"], {"a": 1})

        result = compute_json_diff({"a": 1}, None)
        self.assertEqual(result["removed"], {"a": 1})


class TestComputeDependencyDiff(unittest.TestCase):
    def test_delegates_to_json_diff(self):
        result = compute_dependency_diff(
            {"vpc": "base-vpc", "rds": "postgres-rds"},
            {"vpc": "base-vpc-eu", "rds": "postgres-rds", "efs": "shared-efs"},
        )
        self.assertEqual(result["added"], {"efs": "shared-efs"})
        self.assertEqual(
            result["changed"], {"vpc": {"old": "base-vpc", "new": "base-vpc-eu"}}
        )
        self.assertEqual(result["removed"], {})

    def test_string_equals_single_element_list(self):
        result = compute_dependency_diff({"vpc": "base-vpc"}, {"vpc": ["base-vpc"]})
        self.assertEqual(result["added"], {})
        self.assertEqual(result["removed"], {})
        self.assertEqual(result["changed"], {})

    def test_list_order_insensitive(self):
        result = compute_dependency_diff(
            {"backends": ["a", "b", "c"]},
            {"backends": ["c", "a", "b"]},
        )
        self.assertEqual(result["changed"], {})

    def test_real_list_membership_change(self):
        result = compute_dependency_diff(
            {"backends": ["a", "b"]}, {"backends": ["a", "c"]}
        )
        self.assertEqual(
            result["changed"],
            {"backends": {"old": ["a", "b"], "new": ["a", "c"]}},
        )

    def test_grow_from_single_to_multiple(self):
        result = compute_dependency_diff({"backends": "a"}, {"backends": ["a", "b"]})
        self.assertEqual(
            result["changed"],
            {"backends": {"old": "a", "new": ["a", "b"]}},
        )


class TestComputeBomImpact(unittest.TestCase):
    def setUp(self):
        self.current_bom = {
            "base-vpc": {
                "repo_instance_name": "base-vpc",
                "repo_class_name": "hmd-inf-vpc",
                "repo_class_version": "0.1.24",
                "instance_configuration": {"cidr": "10.0.0.0/16", "az_count": 3},
                "dependencies": {},
            },
            "postgres-rds": {
                "repo_instance_name": "postgres-rds",
                "repo_class_name": "hmd-inf-rds",
                "repo_class_version": "0.2.1",
                "instance_configuration": {
                    "engine": "postgres",
                    "instance_type": "db.r5.large",
                },
                "dependencies": {"vpc": "base-vpc"},
            },
        }

    def test_new_instance(self):
        items = [
            {
                "repo_instance_name": "redis-cluster",
                "repo_class_name": "hmd-inf-redis",
                "repo_class_version": "0.1.0",
                "instance_configuration": {"node_type": "cache.r6g.large"},
                "dependencies": {"vpc": "base-vpc"},
            }
        ]
        impacts = compute_bom_impact(items, self.current_bom)
        self.assertEqual(len(impacts), 1)
        self.assertEqual(impacts[0]["change_type"], "NEW")
        self.assertIsNone(impacts[0]["version_change"])
        self.assertIsNone(impacts[0]["current"])

    def test_version_change(self):
        items = [
            {
                "repo_instance_name": "base-vpc",
                "repo_class_name": "hmd-inf-vpc",
                "repo_class_version": "0.1.25",
                "instance_configuration": {"cidr": "10.0.0.0/16", "az_count": 3},
                "dependencies": {},
            }
        ]
        impacts = compute_bom_impact(items, self.current_bom)
        self.assertEqual(impacts[0]["change_type"], "MODIFIED")
        self.assertEqual(
            impacts[0]["version_change"], {"old": "0.1.24", "new": "0.1.25"}
        )

    def test_config_change(self):
        items = [
            {
                "repo_instance_name": "postgres-rds",
                "repo_class_name": "hmd-inf-rds",
                "repo_class_version": "0.2.1",
                "instance_configuration": {
                    "engine": "postgres",
                    "instance_type": "db.r6g.xlarge",
                },
                "dependencies": {"vpc": "base-vpc"},
            }
        ]
        impacts = compute_bom_impact(items, self.current_bom)
        self.assertEqual(impacts[0]["change_type"], "MODIFIED")
        self.assertIsNone(impacts[0]["version_change"])
        self.assertIsNotNone(impacts[0]["config_diff"])
        self.assertEqual(
            impacts[0]["config_diff"]["changed"]["instance_type"],
            {"old": "db.r5.large", "new": "db.r6g.xlarge"},
        )

    def test_dependency_change(self):
        items = [
            {
                "repo_instance_name": "postgres-rds",
                "repo_class_name": "hmd-inf-rds",
                "repo_class_version": "0.2.1",
                "instance_configuration": {
                    "engine": "postgres",
                    "instance_type": "db.r5.large",
                },
                "dependencies": {"vpc": "base-vpc", "monitoring": "cloudwatch"},
            }
        ]
        impacts = compute_bom_impact(items, self.current_bom)
        self.assertEqual(impacts[0]["change_type"], "MODIFIED")
        self.assertIsNotNone(impacts[0]["dependency_diff"])
        self.assertEqual(
            impacts[0]["dependency_diff"]["added"], {"monitoring": "cloudwatch"}
        )

    def test_unchanged_instance(self):
        items = [
            {
                "repo_instance_name": "base-vpc",
                "repo_class_name": "hmd-inf-vpc",
                "repo_class_version": "0.1.24",
                "instance_configuration": {"cidr": "10.0.0.0/16", "az_count": 3},
                "dependencies": {},
            }
        ]
        impacts = compute_bom_impact(items, self.current_bom)
        self.assertEqual(impacts[0]["change_type"], "UNCHANGED")

    def test_empty_changeset(self):
        impacts = compute_bom_impact([], self.current_bom)
        self.assertEqual(impacts, [])

    def test_empty_bom(self):
        items = [
            {
                "repo_instance_name": "new-service",
                "repo_class_name": "hmd-ms-new",
                "repo_class_version": "0.1.0",
                "instance_configuration": {},
                "dependencies": {},
            }
        ]
        impacts = compute_bom_impact(items, {})
        self.assertEqual(impacts[0]["change_type"], "NEW")


class TestSummarizeImpact(unittest.TestCase):
    def test_summary_counts(self):
        impacts = [
            {"change_type": "NEW"},
            {"change_type": "NEW"},
            {"change_type": "MODIFIED"},
            {"change_type": "UNCHANGED"},
        ]
        result = summarize_impact(impacts)
        self.assertEqual(result, {"new": 2, "modified": 1, "unchanged": 1})

    def test_empty_list(self):
        result = summarize_impact([])
        self.assertEqual(result, {"new": 0, "modified": 0, "unchanged": 0})


class TestComputeEnvironmentDiff(unittest.TestCase):
    def test_empty_response(self):
        result = compute_environment_diff({})
        self.assertEqual(result["only_in_source"], [])
        self.assertEqual(result["only_in_target"], [])
        self.assertEqual(result["modified"], [])

    def test_none_response(self):
        result = compute_environment_diff(None)
        self.assertEqual(result["only_in_source"], [])
        self.assertEqual(result["only_in_target"], [])
        self.assertEqual(result["modified"], [])

    def test_only_in_source(self):
        api = {
            "deploy_change_set": [
                {
                    "repo_instance_name": "new-bucket",
                    "repo_class_name": "hmd-inf-s3bucket",
                },
            ],
            "removed_instances": [],
            "existing_change_set": [],
        }
        result = compute_environment_diff(api)
        self.assertEqual(len(result["only_in_source"]), 1)
        self.assertEqual(
            result["only_in_source"][0]["repo_instance_name"], "new-bucket"
        )
        self.assertEqual(result["modified"], [])
        self.assertEqual(result["only_in_target"], [])

    def test_only_in_target(self):
        api = {
            "deploy_change_set": [],
            "removed_instances": ["legacy-vpc", "old-cluster"],
            "existing_change_set": [],
        }
        result = compute_environment_diff(api)
        names = [r["repo_instance_name"] for r in result["only_in_target"]]
        self.assertEqual(names, ["legacy-vpc", "old-cluster"])

    def test_modified_with_version_change(self):
        api = {
            "deploy_change_set": [
                {
                    "repo_instance_name": "vpc",
                    "repo_class_name": "hmd-vpc",
                    "repo_class_version": "0.3.0",
                    "instance_configuration": {"cidr": "10.0.0.0/16"},
                    "dependencies": {},
                }
            ],
            "removed_instances": [],
            "existing_change_set": [
                {
                    "repo_instance_name": "vpc",
                    "repo_class_name": "hmd-vpc",
                    "repo_class_version": "0.2.1",
                    "instance_configuration": {"cidr": "10.0.0.0/16"},
                    "dependencies": {},
                }
            ],
        }
        result = compute_environment_diff(api)
        self.assertEqual(len(result["modified"]), 1)
        m = result["modified"][0]
        self.assertEqual(m["repo_instance_name"], "vpc")
        self.assertEqual(m["version_change"], {"old": "0.2.1", "new": "0.3.0"})
        self.assertIsNone(m["config_diff"])

    def test_modified_with_config_and_deps_change(self):
        api = {
            "deploy_change_set": [
                {
                    "repo_instance_name": "bucket",
                    "repo_class_name": "hmd-inf-s3bucket",
                    "repo_class_version": "0.1.1",
                    "instance_configuration": {"versioning": "enabled"},
                    "dependencies": {"vpc": "vpc-prod"},
                }
            ],
            "removed_instances": [],
            "existing_change_set": [
                {
                    "repo_instance_name": "bucket",
                    "repo_class_name": "hmd-inf-s3bucket",
                    "repo_class_version": "0.1.1",
                    "instance_configuration": {"versioning": "disabled"},
                    "dependencies": {"vpc": "vpc-dev"},
                }
            ],
        }
        result = compute_environment_diff(api)
        m = result["modified"][0]
        self.assertIsNone(m["version_change"])
        self.assertIsNotNone(m["config_diff"])
        self.assertEqual(
            m["config_diff"]["changed"],
            {"versioning": {"old": "disabled", "new": "enabled"}},
        )
        self.assertIsNotNone(m["dependency_diff"])
        self.assertEqual(
            m["dependency_diff"]["changed"],
            {"vpc": {"old": "vpc-dev", "new": "vpc-prod"}},
        )


if __name__ == "__main__":
    unittest.main()
