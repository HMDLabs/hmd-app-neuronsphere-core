"""Unit tests for classify_dependency_roles -- resource vs. repo_class wiring kind."""
import unittest

from deployments.services.dependency_roles import (
    classify_dependency_roles as _classify_dependency_roles,
)


class _Resp:
    def __init__(self, data, success=True):
        self.success = success
        self.data = data


class _Client:
    def __init__(self, rcv_payload, suggest_payload=None, suggest_success=True):
        self._payload = rcv_payload
        self._suggest_payload = suggest_payload if suggest_payload is not None else {}
        self._suggest_success = suggest_success
        self.suggest_calls = []

    def find_repo_class_versions(self, _repo_class):
        return _Resp(self._payload)

    def suggest_resource_dependencies(
        self, environment_type, repo_class_version_id=None
    ):
        self.suggest_calls.append((environment_type, repo_class_version_id))
        return _Resp(self._suggest_payload, success=self._suggest_success)


class _ClientNoSuggest:
    """A client missing ``suggest_resource_dependencies`` entirely — the helper
    must tolerate its absence (older client, or method not yet wired)."""

    def __init__(self, rcv_payload):
        self._payload = rcv_payload

    def find_repo_class_versions(self, _repo_class):
        return _Resp(self._payload)


_K8S_DEF = {
    "resource_namespace": "kubernetes.neuronsphere.io",
    "resource_definition_name": "kubernetes-cluster",
    "version": "0.1",
}


class TestClassifyDependencyRoles(unittest.TestCase):
    def test_class_only_role_is_repo_class_kind(self):
        client = _Client(
            [
                {
                    "version": "1.0.0",
                    "identifier": "rcv-1",
                    "dependencies": {
                        "vpc": {"repo_class_name": "hmd-inf-vpc", "required": "true"}
                    },
                }
            ]
        )
        classified, matched = _classify_dependency_roles(client, "hmd-inf-foo", "1.0.0")
        self.assertIsNotNone(matched)
        self.assertEqual(classified["vpc"]["kind"], "repo_class")
        self.assertEqual(classified["vpc"]["compatible_class_name"], "hmd-inf-vpc")
        self.assertTrue(classified["vpc"]["required"])
        self.assertIsNone(classified["vpc"]["resource"])

    def test_resource_only_role_is_resource_kind(self):
        client = _Client(
            rcv_payload=[
                {"version": "1.0.0", "identifier": "rcv-1", "dependencies": {}}
            ],
            suggest_payload={
                "cluster": {
                    "resource_definition": _K8S_DEF,
                    "version_spec": "~= 0.1",
                    "tag_selector": "tier=prod",
                    "required": True,
                    "suggested_repo_class_name": "hmd-inf-eks",
                }
            },
        )
        classified, matched = _classify_dependency_roles(
            client, "hmd-inf-foo", "1.0.0", "dev"
        )
        self.assertIsNotNone(matched)
        self.assertEqual(classified["cluster"]["kind"], "resource")
        self.assertEqual(classified["cluster"]["compatible_class_name"], "hmd-inf-eks")
        self.assertTrue(classified["cluster"]["required"])
        self.assertEqual(
            classified["cluster"]["resource"]["resource_definition"], _K8S_DEF
        )

    def test_role_declared_both_ways_resource_wins(self):
        client = _Client(
            rcv_payload=[
                {
                    "version": "1.0.0",
                    "identifier": "rcv-1",
                    "dependencies": {
                        "cluster": {
                            "repo_class_name": "hmd-inf-eks-legacy",
                            "required": "false",
                        }
                    },
                }
            ],
            suggest_payload={
                "cluster": {
                    "resource_definition": _K8S_DEF,
                    "version_spec": None,
                    "tag_selector": None,
                    "required": True,
                    "suggested_repo_class_name": "hmd-inf-eks",
                }
            },
        )
        classified, _ = _classify_dependency_roles(
            client, "hmd-inf-foo", "1.0.0", "dev"
        )
        self.assertEqual(classified["cluster"]["kind"], "resource")
        self.assertEqual(classified["cluster"]["compatible_class_name"], "hmd-inf-eks")
        # required is OR'd across both declarations.
        self.assertTrue(classified["cluster"]["required"])

    def test_undeclared_role_absent_from_result(self):
        client = _Client(
            [
                {
                    "version": "1.0.0",
                    "identifier": "rcv-1",
                    "dependencies": {
                        "vpc": {"repo_class_name": "hmd-inf-vpc", "required": "false"}
                    },
                }
            ]
        )
        classified, _ = _classify_dependency_roles(client, "hmd-inf-foo", "1.0.0")
        self.assertNotIn("some-other-role", classified)

    def test_version_not_found_yields_empty_classification(self):
        client = _Client([])
        classified, matched = _classify_dependency_roles(client, "hmd-inf-foo", "9.9.9")
        self.assertIsNone(matched)
        self.assertEqual(classified, {})

    def test_suggest_failure_falls_back_to_class_based_only(self):
        client = _Client(
            rcv_payload=[
                {
                    "version": "1.0.0",
                    "identifier": "rcv-1",
                    "dependencies": {
                        "vpc": {"repo_class_name": "hmd-inf-vpc", "required": "false"}
                    },
                }
            ],
            suggest_payload={},
            suggest_success=False,
        )
        classified, matched = _classify_dependency_roles(
            client, "hmd-inf-foo", "1.0.0", "dev"
        )
        self.assertIsNotNone(matched)
        self.assertEqual(classified["vpc"]["kind"], "repo_class")

    def test_suggest_called_with_environment_as_first_positional_arg(self):
        client = _Client(
            rcv_payload=[
                {"version": "1.0.0", "identifier": "rcv-1", "dependencies": {}}
            ],
            suggest_payload={},
        )
        _classify_dependency_roles(client, "hmd-inf-foo", "1.0.0", "dev")
        self.assertEqual(client.suggest_calls, [("dev", "rcv-1")])

    def test_suggest_not_called_without_environment(self):
        client = _Client(
            rcv_payload=[
                {"version": "1.0.0", "identifier": "rcv-1", "dependencies": {}}
            ],
            suggest_payload={
                "cluster": {
                    "resource_definition": _K8S_DEF,
                    "version_spec": None,
                    "tag_selector": None,
                    "required": True,
                    "suggested_repo_class_name": "hmd-inf-eks",
                }
            },
        )
        classified, matched = _classify_dependency_roles(client, "hmd-inf-foo", "1.0.0")
        self.assertIsNotNone(matched)
        self.assertEqual(client.suggest_calls, [])
        self.assertNotIn("cluster", classified)

    def test_missing_suggest_method_tolerated(self):
        client = _ClientNoSuggest(
            [
                {
                    "version": "1.0.0",
                    "identifier": "rcv-1",
                    "dependencies": {
                        "vpc": {"repo_class_name": "hmd-inf-vpc", "required": "false"}
                    },
                }
            ]
        )
        classified, matched = _classify_dependency_roles(client, "hmd-inf-foo", "1.0.0")
        self.assertIsNotNone(matched)
        self.assertEqual(classified["vpc"]["kind"], "repo_class")


if __name__ == "__main__":
    unittest.main()
