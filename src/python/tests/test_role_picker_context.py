"""Unit tests for build_role_picker_context -- dependency picker template context."""
import unittest

from deployments.services.dependency_roles import (
    build_role_picker_context as _build_role_picker_context,
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

    def find_repo_class_versions(self, _repo_class):
        return _Resp(self._payload)

    def suggest_resource_dependencies(self, _repo_class, repo_class_version_id=None):
        return _Resp(self._suggest_payload, success=self._suggest_success)


class _ClientNoSuggest:
    """A client missing ``suggest_resource_dependencies`` entirely — the helper
    must tolerate its absence (older client, or method not yet wired)."""

    def __init__(self, rcv_payload):
        self._payload = rcv_payload

    def find_repo_class_versions(self, _repo_class):
        return _Resp(self._payload)


class _Draft:
    def __init__(self, content):
        self.content = content
        self.pk = 1


def _make_client_with_role(role_name, compatible_class, required=False):
    return _Client(
        [
            {
                "version": "1.0.0",
                "dependencies": {
                    role_name: {
                        "repo_class_name": compatible_class,
                        "required": "true" if required else "false",
                    }
                },
            }
        ]
    )


class TestRolePickerContext(unittest.TestCase):
    def test_string_selected_normalized_to_list(self):
        client = _make_client_with_role("vpc", "hmd-inf-vpc")
        draft = _Draft(
            [{"repo_class_name": "hmd-inf-vpc", "repo_instance_name": "base-vpc"}]
        )
        ctx = _build_role_picker_context(
            client,
            draft,
            "hmd-inf-foo",
            "1.0.0",
            selected_deps={"vpc": "base-vpc"},
        )
        role = ctx["roles"][0]
        self.assertEqual(role["selected"], ["base-vpc"])
        self.assertEqual(role["initial_source"], "draft")

    def test_list_selected_preserved(self):
        client = _make_client_with_role("backends", "hmd-svc-backend")
        draft = _Draft(
            [
                {"repo_class_name": "hmd-svc-backend", "repo_instance_name": "a"},
                {"repo_class_name": "hmd-svc-backend", "repo_instance_name": "b"},
            ]
        )
        ctx = _build_role_picker_context(
            client,
            draft,
            "hmd-inf-foo",
            "1.0.0",
            selected_deps={"backends": ["a", "b"]},
        )
        role = ctx["roles"][0]
        self.assertEqual(role["selected"], ["a", "b"])
        self.assertEqual(role["initial_source"], "draft")

    def test_initial_source_bom_when_any_selected_not_in_draft(self):
        client = _make_client_with_role("backends", "hmd-svc-backend")
        draft = _Draft(
            [{"repo_class_name": "hmd-svc-backend", "repo_instance_name": "a"}]
        )
        ctx = _build_role_picker_context(
            client,
            draft,
            "hmd-inf-foo",
            "1.0.0",
            selected_deps={"backends": ["a", "from-bom"]},
        )
        role = ctx["roles"][0]
        self.assertEqual(role["selected"], ["a", "from-bom"])
        self.assertEqual(role["initial_source"], "bom")

    def test_none_selected_yields_draft_source(self):
        client = _make_client_with_role("vpc", "hmd-inf-vpc")
        draft = _Draft([])
        ctx = _build_role_picker_context(
            client, draft, "hmd-inf-foo", "1.0.0", selected_deps={}
        )
        role = ctx["roles"][0]
        self.assertEqual(role["selected"], [])
        self.assertEqual(role["initial_source"], "draft")

    def test_resolved_version_missing_role_preserved_as_stale(self):
        # The resolved version declares "vpc" but the instance also has a
        # "stale-role" dep no longer declared — it must be preserved, not dropped.
        client = _make_client_with_role("vpc", "hmd-inf-vpc")
        draft = _Draft([])
        ctx = _build_role_picker_context(
            client,
            draft,
            "hmd-inf-foo",
            "1.0.0",
            selected_deps={"stale-role": ["a", "b"]},
        )
        self.assertNotIn("orphan_deps", ctx)
        self.assertFalse(ctx["no_version"])
        stale = [r for r in ctx["roles"] if r["role"] == "stale-role"]
        self.assertEqual(len(stale), 1)
        self.assertTrue(stale[0]["stale"])
        self.assertEqual(stale[0]["selected"], ["a", "b"])
        self.assertEqual(stale[0]["initial_source"], "bom")

    def test_version_not_found_prepopulates_existing_deps(self):
        # find_repo_class_versions returns nothing matching -> no_version, but the
        # instance's current deps must still render as editable, preserved rows.
        client = _Client([])  # no versions at all
        draft = _Draft(
            [{"repo_class_name": "hmd-svc-backend", "repo_instance_name": "a"}]
        )
        ctx = _build_role_picker_context(
            client,
            draft,
            "hmd-inf-foo",
            "9.9.9",
            selected_deps={"vpc": "base-vpc", "backends": ["a", "other"]},
        )
        self.assertTrue(ctx["no_version"])
        by_role = {r["role"]: r for r in ctx["roles"]}
        self.assertEqual(set(by_role), {"vpc", "backends"})
        self.assertTrue(all(r["stale"] for r in ctx["roles"]))
        # Stale rows are BOM-sourced with no in-draft candidates so every current
        # value is preserved via the template's hidden-input path on save.
        self.assertEqual(by_role["vpc"]["selected"], ["base-vpc"])
        self.assertEqual(by_role["vpc"]["initial_source"], "bom")
        self.assertEqual(by_role["vpc"]["in_draft_candidates"], [])
        self.assertEqual(by_role["backends"]["selected"], ["a", "other"])
        self.assertEqual(by_role["backends"]["in_draft_candidates"], [])
        self.assertEqual(by_role["backends"]["initial_source"], "bom")

    def test_version_not_found_with_no_deps_yields_empty_roles(self):
        client = _Client([])
        draft = _Draft([])
        ctx = _build_role_picker_context(
            client, draft, "hmd-inf-foo", "9.9.9", selected_deps={}
        )
        self.assertTrue(ctx["no_version"])
        self.assertEqual(ctx["roles"], [])


_K8S_DEF = {
    "resource_namespace": "kubernetes.neuronsphere.io",
    "resource_definition_name": "kubernetes-cluster",
    "version": "0.1",
}


def _client_with_resource_role(role_name="cluster", required=True):
    """RCV that declares NO class-name deps but has an identifier so the helper
    can call ``suggest_resource_dependencies``, which returns one resource role."""
    return _Client(
        rcv_payload=[{"version": "1.0.0", "identifier": "rcv-1", "dependencies": {}}],
        suggest_payload={
            role_name: {
                "resource_definition": _K8S_DEF,
                "version_spec": "~= 0.1",
                "tag_selector": "tier=prod",
                "required": required,
                "suggested_repo_class_name": "hmd-inf-eks",
                "candidates": [{"name": "prod-eks", "identifier": "ri-1"}],
            }
        },
    )


class TestRolePickerResourceRoles(unittest.TestCase):
    def test_resource_role_added_from_suggestion(self):
        client = _client_with_resource_role()
        draft = _Draft([])
        ctx = _build_role_picker_context(
            client, draft, "hmd-inf-foo", "1.0.0", selected_deps={}, environment="dev"
        )
        by_role = {r["role"]: r for r in ctx["roles"]}
        self.assertIn("cluster", by_role)
        role = by_role["cluster"]
        self.assertTrue(role["is_resource"])
        self.assertEqual(role["resource"]["resource_definition"], _K8S_DEF)
        self.assertEqual(role["resource"]["version_spec"], "~= 0.1")
        self.assertEqual(role["resource"]["tag_selector"], "tier=prod")
        self.assertTrue(role["required"])

    def test_in_draft_candidates_matched_by_producer_class(self):
        client = _client_with_resource_role()
        # A draft item of the suggested producer class should be an in-draft candidate.
        draft = _Draft(
            [{"repo_class_name": "hmd-inf-eks", "repo_instance_name": "draft-eks"}]
        )
        ctx = _build_role_picker_context(
            client, draft, "hmd-inf-foo", "1.0.0", selected_deps={}, environment="dev"
        )
        role = {r["role"]: r for r in ctx["roles"]}["cluster"]
        self.assertIn("draft-eks", role["in_draft_candidates"])

    def test_no_environment_skips_resource_suggestion(self):
        client = _client_with_resource_role()
        draft = _Draft([])
        ctx = _build_role_picker_context(
            client, draft, "hmd-inf-foo", "1.0.0", selected_deps={}
        )
        by_role = {r["role"]: r for r in ctx["roles"]}
        self.assertNotIn("cluster", by_role)

    def test_class_based_unchanged_when_suggestion_empty(self):
        # Same shape as TestRolePickerContext but the client also exposes an
        # (empty) suggest endpoint — class-based behavior must be identical.
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
        )
        draft = _Draft(
            [{"repo_class_name": "hmd-inf-vpc", "repo_instance_name": "base-vpc"}]
        )
        ctx = _build_role_picker_context(
            client, draft, "hmd-inf-foo", "1.0.0", selected_deps={"vpc": "base-vpc"}
        )
        role = {r["role"]: r for r in ctx["roles"]}["vpc"]
        self.assertFalse(role.get("is_resource", False))
        self.assertEqual(role["selected"], ["base-vpc"])
        self.assertEqual(role["initial_source"], "draft")

    def test_suggestion_failure_does_not_break_context(self):
        client = _Client(
            rcv_payload=[
                {"version": "1.0.0", "identifier": "rcv-1", "dependencies": {}}
            ],
            suggest_payload={},
            suggest_success=False,
        )
        draft = _Draft([])
        ctx = _build_role_picker_context(
            client, draft, "hmd-inf-foo", "1.0.0", selected_deps={}
        )
        self.assertFalse(ctx["no_version"])
        self.assertEqual(ctx["roles"], [])

    def test_missing_suggest_method_tolerated(self):
        client = _ClientNoSuggest(
            [{"version": "1.0.0", "identifier": "rcv-1", "dependencies": {}}]
        )
        draft = _Draft([])
        ctx = _build_role_picker_context(
            client, draft, "hmd-inf-foo", "1.0.0", selected_deps={}
        )
        self.assertEqual(ctx["roles"], [])


if __name__ == "__main__":
    unittest.main()
