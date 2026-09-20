"""Unit tests for build_instance_detail_sections -- details/config/dependency split."""
import unittest

from deployments.services.instance_detail import (
    build_instance_detail_sections as _build_instance_detail_sections,
)


class _Resp:
    def __init__(self, data, success=True):
        self.success = success
        self.data = data


class _Client:
    def find_repo_class_versions(self, _repo_class):
        return _Resp(
            [
                {
                    "version": "3.0.0",
                    "identifier": "rcv-svc-3",
                    "dependencies": {
                        "network": {
                            "repo_class_name": "hmd-inf-vpc",
                            "required": "true",
                        }
                    },
                }
            ]
        )

    def suggest_resource_dependencies(self, _repo_class, repo_class_version_id=None):
        return _Resp(
            {
                "cluster": {
                    "resource_definition": {
                        "resource_namespace": "kubernetes.neuronsphere.io",
                        "resource_definition_name": "kubernetes-cluster",
                        "version": "0.1",
                    },
                    "required": True,
                    "suggested_repo_class_name": "hmd-inf-eks",
                }
            }
        )


_FULL_CONFIG = {
    "instance_name": "svc-1",
    "repo_name": "hmd-ms-svc",
    "version": "3.0.0",
    "deployment_id": "dep-123",
    "hmd_region": "us-east-1",
    "some_setting": "value",
    "nested": {"a": 1, "b": [1, 2, 3]},
    "dependencies": {
        "cluster": {"instance_name": "eks-1"},
        "network": {"instance_name": "vpc-1"},
        "legacy": {"instance_name": "vpc-1"},
    },
}

_HISTORY = [{"status": "DEPLOYED", "start": "2026-01-01"}, {"status": "FAILED"}]


class TestBuildInstanceDetailSections(unittest.TestCase):
    def test_details_pulls_metadata_and_latest_status(self):
        sections = _build_instance_detail_sections(_Client(), _FULL_CONFIG, _HISTORY)
        details = sections["details"]
        self.assertEqual(details["instance_name"], "svc-1")
        self.assertEqual(details["repo_class_name"], "hmd-ms-svc")
        self.assertEqual(details["version"], "3.0.0")
        self.assertEqual(details["deployment_id"], "dep-123")
        self.assertEqual(details["hmd_region"], "us-east-1")
        self.assertEqual(details["status"], "DEPLOYED")

    def test_status_none_when_no_history(self):
        sections = _build_instance_detail_sections(_Client(), _FULL_CONFIG, [])
        self.assertIsNone(sections["details"]["status"])

    def test_configuration_excludes_metadata_and_dependencies(self):
        sections = _build_instance_detail_sections(_Client(), _FULL_CONFIG, _HISTORY)
        configuration = sections["configuration"]
        self.assertEqual(
            configuration, {"some_setting": "value", "nested": {"a": 1, "b": [1, 2, 3]}}
        )
        self.assertNotIn("dependencies", configuration)
        self.assertNotIn("instance_name", configuration)

    def test_dependency_rows_tagged_with_wiring_kind(self):
        sections = _build_instance_detail_sections(
            _Client(), _FULL_CONFIG, _HISTORY, "dev"
        )
        by_role = {r["role"]: r for r in sections["dependency_rows"]}
        self.assertEqual(by_role["cluster"]["kind"], "resource")
        self.assertEqual(by_role["cluster"]["targets"], ["eks-1"])
        self.assertEqual(by_role["network"]["kind"], "repo_class")
        self.assertEqual(by_role["legacy"]["kind"], "instance")

    def test_no_environment_skips_resource_classification(self):
        sections = _build_instance_detail_sections(_Client(), _FULL_CONFIG, _HISTORY)
        by_role = {r["role"]: r for r in sections["dependency_rows"]}
        self.assertEqual(by_role["cluster"]["kind"], "instance")
        self.assertEqual(by_role["network"]["kind"], "repo_class")

    def test_dependency_row_targets_flattened_from_list(self):
        config = dict(_FULL_CONFIG)
        config["dependencies"] = {
            "network": [{"instance_name": "vpc-1"}, {"instance_name": "vpc-2"}]
        }
        sections = _build_instance_detail_sections(_Client(), config, _HISTORY)
        row = sections["dependency_rows"][0]
        self.assertEqual(row["targets"], ["vpc-1", "vpc-2"])

    def test_empty_config_yields_empty_sections(self):
        sections = _build_instance_detail_sections(_Client(), {}, [])
        self.assertEqual(sections["configuration"], {})
        self.assertEqual(sections["dependency_rows"], [])
        self.assertEqual(sections["details"]["instance_name"], "")


if __name__ == "__main__":
    unittest.main()
