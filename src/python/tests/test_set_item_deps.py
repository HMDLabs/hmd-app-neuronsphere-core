"""Unit tests for preserve_required_deps -- required-role restoration on save."""
import unittest

from deployments.services.dependency_roles import (
    preserve_required_deps as _preserve_required_deps,
)


def _classified(required_roles=(), optional_roles=()):
    out = {}
    for role in required_roles:
        out[role] = {"kind": "repo_class", "required": True}
    for role in optional_roles:
        out[role] = {"kind": "repo_class", "required": False}
    return out


class TestPreserveRequiredDeps(unittest.TestCase):
    def test_optional_role_omitted_stays_removed(self):
        # An optional role the user removed (absent from parsed) must not come back.
        classified = _classified(required_roles=["vpc"], optional_roles=["redis"])
        parsed = {"vpc": "base-vpc"}
        existing = {"vpc": "base-vpc", "redis": "cache-a"}
        result = _preserve_required_deps(parsed, existing, classified)
        self.assertEqual(result, {"vpc": "base-vpc"})
        self.assertNotIn("redis", result)

    def test_required_role_omitted_is_restored(self):
        classified = _classified(required_roles=["vpc"])
        parsed = {}
        existing = {"vpc": "base-vpc"}
        result = _preserve_required_deps(parsed, existing, classified)
        self.assertEqual(result, {"vpc": "base-vpc"})

    def test_required_role_rewired_keeps_new_target(self):
        classified = _classified(required_roles=["vpc"])
        parsed = {"vpc": "other-vpc"}
        existing = {"vpc": "base-vpc"}
        result = _preserve_required_deps(parsed, existing, classified)
        self.assertEqual(result, {"vpc": "other-vpc"})

    def test_required_role_restored_as_list(self):
        classified = _classified(required_roles=["backends"])
        parsed = {}
        existing = {"backends": ["a", "b"]}
        result = _preserve_required_deps(parsed, existing, classified)
        self.assertEqual(result, {"backends": ["a", "b"]})

    def test_required_role_without_prior_value_stays_empty(self):
        # Nothing to restore -> no key fabricated.
        classified = _classified(required_roles=["vpc"])
        parsed = {}
        existing = {}
        result = _preserve_required_deps(parsed, existing, classified)
        self.assertEqual(result, {})

    def test_required_resource_role_restored(self):
        classified = {"cluster": {"kind": "resource", "required": True}}
        parsed = {}
        existing = {"cluster": "prod-eks"}
        result = _preserve_required_deps(parsed, existing, classified)
        self.assertEqual(result, {"cluster": "prod-eks"})

    def test_undeclared_role_untouched(self):
        # A role not present in classified (stale/undeclared) is neither restored
        # nor dropped by this helper — parsed carries whatever the picker sent.
        classified = _classified(required_roles=["vpc"])
        parsed = {"stale": "x"}
        existing = {"vpc": "base-vpc", "stale": "x"}
        result = _preserve_required_deps(parsed, existing, classified)
        self.assertEqual(result, {"stale": "x", "vpc": "base-vpc"})

    def test_empty_classified_is_noop(self):
        parsed = {"vpc": "base-vpc"}
        result = _preserve_required_deps(parsed, {"vpc": "old"}, {})
        self.assertEqual(result, {"vpc": "base-vpc"})


if __name__ == "__main__":
    unittest.main()
