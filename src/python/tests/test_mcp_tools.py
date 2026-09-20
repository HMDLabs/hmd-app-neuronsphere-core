"""Unit tests for the MCP tool bodies.

The bodies are called directly rather than through ``@read_tool`` -- identity,
authorization, and auditing are the decorator's job and are covered by
``test_mcp_server.py`` and ``test_mcp_registry.py``. What matters here is the
shaping of the response and, just as much, *how many service calls it takes*:
``FakeClient`` counts every call so the tools can be held to their cost budget.
"""
import unittest

from fastmcp.exceptions import ToolError

from deployments.services.api_client import APIResponse
from ns_mcp.tooling import ToolContext
from ns_mcp.tools.bom import describe_environment
from ns_mcp.tools.environments import compare_environments
from ns_mcp.tools.instances import (
    describe_instance,
    get_instance_configuration,
    get_instance_dependencies,
)
from ns_mcp.tools.repo_classes import (
    describe_repo_class,
    search_capabilities,
    search_repo_classes,
)
from ns_mcp.tools.resources import (
    find_resource_candidates,
    find_resource_providers,
    list_resource_definitions,
)


def _bom_item(name, repo_class, version="1.0", status="DEPLOYED", dependencies=None):
    return {
        "repo_instance_name": name,
        "repo_class_name": repo_class,
        "repo_class_version": version,
        "status": status,
        "dependencies": dependencies or {},
    }


#: Four instances over three repo classes and four distinct (class, version)
#: pairs -- enough that a tool fanning classification across the BOM would show
#: up plainly in the call counts.
SAMPLE_BOM = [
    _bom_item("base-vpc", "hmd-inf-vpc"),
    _bom_item("k8s", "hmd-inf-k8s", dependencies={"vpc": "base-vpc"}),
    _bom_item(
        "deployment-svc",
        "hmd-ms-deployment",
        version="2.0",
        status="FAILED",
        dependencies={"cluster": "k8s", "db": ["base-vpc", "not-in-this-bom"]},
    ),
    _bom_item(
        "gui",
        "hmd-app-neuronsphere",
        version="0.1",
        dependencies={"api": "deployment-svc"},
    ),
]


class FakeClient:
    """A DeploymentAPIClient stand-in that records every call it receives."""

    def __init__(self, **responses):
        self.calls = []
        self._responses = responses

    def _record(self, method, *args, **kwargs):
        self.calls.append(method)
        value = self._responses.get(method, APIResponse(success=True, data=None))
        return value(*args, **kwargs) if callable(value) else value

    def count(self, method):
        return self.calls.count(method)

    def __getattr__(self, name):
        # Any client method not explicitly stubbed still records its call and
        # returns an empty success, so an accidental extra round-trip is caught
        # by the counts rather than by an AttributeError.
        def method(*args, **kwargs):
            return self._record(name, *args, **kwargs)

        return method


def body(tool):
    """The undecorated tool body.

    ``@read_tool`` wraps each tool in an async function that resolves a
    principal from the request context; these tests call the sync body directly
    and supply their own ToolContext.
    """
    return getattr(tool, "__wrapped__")


def ctx_for(client):
    """A ToolContext with no user -- the bodies under test never touch one."""
    return ToolContext(user=None, principal=None, client=client)


def bom_client(items=None, **extra):
    return FakeClient(
        get_deployment_bom=APIResponse(
            success=True, data=SAMPLE_BOM if items is None else items
        ),
        **extra,
    )


class TestDescribeEnvironment(unittest.TestCase):
    def test_summary_is_the_default_and_counts_by_status_and_class(self):
        client = bom_client()
        result = body(describe_environment)(ctx_for(client), environment="dev")

        self.assertEqual(result["detail"], "summary")
        self.assertEqual(result["summary"]["total"], 4)
        self.assertEqual(result["summary"]["by_status"], {"DEPLOYED": 3, "FAILED": 1})
        # No instance list in the summary -- that is the point of it.
        self.assertNotIn("instances", result)

    def test_summary_costs_exactly_one_bom_read_and_no_classification(self):
        """The regression guard for the DAG gateway timeouts fixed in e4de1e1.

        ``classify_dependency_roles`` issues one ``find_repo_class_versions`` and
        one ``suggest_resource_dependencies`` per (repo_class, version). Fanning
        that across a BOM is what timed out; this tool must never do it.
        """
        client = bom_client()
        for detail in ("summary", "full"):
            with self.subTest(detail=detail):
                client.calls.clear()
                body(describe_environment)(
                    ctx_for(client), environment="dev", detail=detail
                )
                self.assertEqual(client.count("get_deployment_bom"), 1)
                self.assertEqual(client.count("find_repo_class_versions"), 0)
                self.assertEqual(client.count("suggest_resource_dependencies"), 0)

    def test_facets_come_from_the_unfiltered_set(self):
        # Filtered down to one instance, the caller still needs to see every
        # value it could have filtered on instead.
        result = body(describe_environment)(
            ctx_for(bom_client()), environment="dev", detail="full", status="FAILED"
        )
        self.assertEqual(len(result["instances"]), 1)
        self.assertEqual(result["facets"]["statuses"], ["DEPLOYED", "FAILED"])
        self.assertEqual(len(result["facets"]["repo_classes"]), 4)

    def test_full_detail_filters_sorts_and_paginates(self):
        result = body(describe_environment)(
            ctx_for(bom_client()),
            environment="dev",
            detail="full",
            sort_by="repo_instance_name",
            sort_dir="desc",
            limit=2,
        )
        self.assertEqual(
            [i["instance_name"] for i in result["instances"]], ["k8s", "gui"]
        )
        self.assertEqual(result["pagination"]["total"], 4)
        self.assertTrue(result["pagination"]["has_next"])
        self.assertEqual(result["instances"][1]["dependency_count"], 1)

    def test_offset_pages_through_the_matched_set(self):
        result = body(describe_environment)(
            ctx_for(bom_client()),
            environment="dev",
            detail="full",
            limit=2,
            offset=2,
        )
        self.assertEqual(
            [i["instance_name"] for i in result["instances"]], ["gui", "k8s"]
        )
        self.assertFalse(result["pagination"]["has_next"])
        self.assertTrue(result["pagination"]["has_prev"])

    def test_search_matches_instance_or_repo_class_name(self):
        result = body(describe_environment)(
            ctx_for(bom_client()), environment="dev", detail="full", search="hmd-inf"
        )
        self.assertEqual(
            sorted(i["instance_name"] for i in result["instances"]),
            ["base-vpc", "k8s"],
        )

    def test_an_oversized_limit_is_clamped_not_rejected(self):
        from django.conf import settings

        result = body(describe_environment)(
            ctx_for(bom_client(items=[_bom_item(f"i{n}", "c") for n in range(600)])),
            environment="dev",
            detail="full",
            limit=100000,
        )
        self.assertEqual(len(result["instances"]), settings.MCP_MAX_PAGE_SIZE)

    def test_a_failing_bom_read_is_reported_as_a_tool_error(self):
        client = FakeClient(
            get_deployment_bom=APIResponse(success=False, data=None, error="boom")
        )
        with self.assertRaises(ToolError) as ctx:
            body(describe_environment)(ctx_for(client), environment="dev")
        self.assertIn("boom", str(ctx.exception))


class TestDescribeInstance(unittest.TestCase):
    def _client(self, history=None, **extra):
        return FakeClient(
            get_deployment_config=APIResponse(
                success=True,
                data={
                    "instance_name": "deployment-svc",
                    "repo_name": "hmd-ms-deployment",
                    "version": "2.0",
                    "deployment_id": "did-1",
                    "hmd_region": "reg1",
                    "dependencies": {"cluster": {"instance_name": "k8s"}},
                    "log_level": "INFO",
                },
            ),
            get_deployment_history=APIResponse(
                success=True,
                data={
                    "history": history if history is not None else [{"status": "OK"}]
                },
            ),
            find_repo_class_versions=APIResponse(
                success=True,
                data=[
                    {
                        "version": "2.0",
                        "identifier": "rcv-1",
                        "dependencies": {
                            "cluster": {
                                "repo_class_name": "hmd-inf-k8s",
                                "required": "true",
                            }
                        },
                    }
                ],
            ),
            **extra,
        )

    def test_splits_metadata_configuration_and_dependency_wiring(self):
        result = body(describe_instance)(
            ctx_for(self._client()),
            environment="dev",
            instance_name="deployment-svc",
        )
        self.assertEqual(result["details"]["repo_class_name"], "hmd-ms-deployment")
        self.assertEqual(result["details"]["status"], "OK")
        # Metadata keys are shown under "details", not repeated in the config.
        self.assertEqual(result["configuration"], {"log_level": "INFO"})
        self.assertEqual(
            result["dependencies"],
            [{"role": "cluster", "targets": ["k8s"], "kind": "repo_class"}],
        )

    def test_a_resource_backed_role_is_tagged_resource_not_repo_class(self):
        # A role declared both ways is "resource" -- the resource requirement is
        # authoritative (NERD0004 SPEC0008). This is the distinction the GUI
        # only shows on the instance page, and the reason describe_instance
        # pays for classification at all.
        client = self._client(
            suggest_resource_dependencies=APIResponse(
                success=True,
                data={
                    "cluster": {
                        "suggested_repo_class_name": "hmd-inf-k8s",
                        "required": True,
                        "resource_definition": {
                            "resource_namespace": "kubernetes.neuronsphere.io",
                            "resource_definition_name": "kubernetes-cluster",
                        },
                    }
                },
            )
        )
        result = body(describe_instance)(
            ctx_for(client), environment="dev", instance_name="deployment-svc"
        )
        self.assertEqual(result["dependencies"][0]["kind"], "resource")

    def test_classifies_roles_for_exactly_one_class_version_pair(self):
        """Classification is legitimate here -- but only once, for this instance."""
        client = self._client()
        body(describe_instance)(
            ctx_for(client), environment="dev", instance_name="deployment-svc"
        )
        self.assertEqual(client.count("find_repo_class_versions"), 1)
        self.assertEqual(client.count("suggest_resource_dependencies"), 1)

    def test_history_is_truncated_but_the_true_total_is_reported(self):
        result = body(describe_instance)(
            ctx_for(self._client(history=[{"status": f"s{n}"} for n in range(25)])),
            environment="dev",
            instance_name="deployment-svc",
            history_limit=3,
        )
        self.assertEqual(len(result["history"]), 3)
        self.assertEqual(result["history_total"], 25)

    def test_a_failing_history_read_still_returns_the_instance(self):
        client = self._client()
        client._responses["get_deployment_history"] = APIResponse(
            success=False, data=None, error="history unavailable"
        )
        result = body(describe_instance)(
            ctx_for(client), environment="dev", instance_name="deployment-svc"
        )
        self.assertEqual(result["history"], [])
        self.assertEqual(result["history_error"], "history unavailable")
        self.assertEqual(result["details"]["repo_class_name"], "hmd-ms-deployment")

    def test_an_unknown_instance_says_so(self):
        client = FakeClient(get_deployment_config=APIResponse(success=True, data={}))
        with self.assertRaises(ToolError) as ctx:
            body(describe_instance)(
                ctx_for(client), environment="dev", instance_name="nope"
            )
        self.assertIn("nope", str(ctx.exception))


class TestGetInstanceDependencies(unittest.TestCase):
    def test_both_directions_from_a_single_bom_read(self):
        client = bom_client()
        result = body(get_instance_dependencies)(
            ctx_for(client), environment="dev", instance_name="k8s"
        )
        self.assertEqual(
            result["depends_on"], [{"instance": "base-vpc", "role": "vpc"}]
        )
        self.assertEqual(
            result["dependents"], [{"instance": "deployment-svc", "role": "cluster"}]
        )
        self.assertEqual(client.count("get_deployment_bom"), 1)
        self.assertEqual(client.count("find_repo_class_versions"), 0)
        self.assertEqual(client.count("suggest_resource_dependencies"), 0)

    def test_targets_absent_from_the_bom_are_reported_as_unresolved(self):
        result = body(get_instance_dependencies)(
            ctx_for(bom_client()),
            environment="dev",
            instance_name="deployment-svc",
            direction="depends_on",
        )
        self.assertEqual(
            result["depends_on"],
            [
                {"instance": "base-vpc", "role": "db"},
                {"instance": "k8s", "role": "cluster"},
            ],
        )
        self.assertEqual(
            result["unresolved"], [{"target": "not-in-this-bom", "role": "db"}]
        )

    def test_direction_selects_which_edges_are_returned(self):
        for direction, present, absent in (
            ("depends_on", "depends_on", "dependents"),
            ("dependents", "dependents", "depends_on"),
        ):
            with self.subTest(direction=direction):
                result = body(get_instance_dependencies)(
                    ctx_for(bom_client()),
                    environment="dev",
                    instance_name="k8s",
                    direction=direction,
                )
                self.assertIn(present, result)
                self.assertNotIn(absent, result)

    def test_a_leaf_instance_reports_empty_edges_rather_than_failing(self):
        result = body(get_instance_dependencies)(
            ctx_for(bom_client()), environment="dev", instance_name="gui"
        )
        self.assertEqual(result["dependents"], [])
        self.assertEqual(
            result["depends_on"], [{"instance": "deployment-svc", "role": "api"}]
        )

    def test_an_instance_not_in_the_bom_says_so(self):
        with self.assertRaises(ToolError) as ctx:
            body(get_instance_dependencies)(
                ctx_for(bom_client()), environment="dev", instance_name="ghost"
            )
        self.assertIn("ghost", str(ctx.exception))


class TestFindResourceProviders(unittest.TestCase):
    DEFINITION = {
        "identifier": "rd-1",
        "resource_definition_name": "kubernetes-cluster",
        "resource_namespace": "kubernetes.neuronsphere.io",
        "version": "0.1.0",
    }

    def _client(self, **extra):
        defaults = dict(
            list_resource_definitions=APIResponse(success=True, data=[self.DEFINITION]),
            get_resource_definition_ancestry=APIResponse(
                success=True, data=[{"resource_definition_name": "compute"}]
            ),
            get_effective_output_schema=APIResponse(
                success=True, data={"type": "object"}
            ),
            get_producers=APIResponse(
                success=True,
                data=[{"repo_class_name": "hmd-inf-k8s", "version": "1.0"}],
            ),
        )
        defaults.update(extra)
        return FakeClient(**defaults)

    def test_fuses_definition_ancestry_schema_and_producers(self):
        result = body(find_resource_providers)(
            ctx_for(self._client()),
            resource_definition_name="kubernetes-cluster",
            namespace="kubernetes.neuronsphere.io",
        )
        self.assertEqual(result["definition"], self.DEFINITION)
        self.assertEqual(result["ancestry"][0]["resource_definition_name"], "compute")
        self.assertEqual(result["output_schema"], {"type": "object"})
        self.assertEqual(result["total_producers"], 1)
        self.assertEqual(result["errors"], {})

    def test_include_subtypes_is_passed_through_and_reflected(self):
        captured = {}

        def producers(rd_id, include_subtypes=False):
            captured["rd_id"] = rd_id
            captured["include_subtypes"] = include_subtypes
            return APIResponse(success=True, data=[])

        result = body(find_resource_providers)(
            ctx_for(self._client(get_producers=producers)),
            resource_definition_name="kubernetes-cluster",
            include_subtypes=True,
        )
        self.assertEqual(captured, {"rd_id": "rd-1", "include_subtypes": True})
        self.assertTrue(result["include_subtypes"])

    def test_one_failing_lookup_does_not_lose_the_others(self):
        result = body(find_resource_providers)(
            ctx_for(
                self._client(
                    get_effective_output_schema=APIResponse(
                        success=False, data=None, error="schema unavailable"
                    )
                )
            ),
            resource_definition_name="kubernetes-cluster",
        )
        self.assertIsNone(result["output_schema"])
        self.assertEqual(result["errors"], {"output_schema": "schema unavailable"})
        self.assertEqual(result["total_producers"], 1)

    def test_an_unmatched_definition_names_what_was_searched_for(self):
        with self.assertRaises(ToolError) as ctx:
            body(find_resource_providers)(
                ctx_for(self._client()),
                resource_definition_name="no-such-thing",
                namespace="kubernetes.neuronsphere.io",
            )
        self.assertIn("kubernetes.neuronsphere.io/no-such-thing", str(ctx.exception))

    def test_version_narrows_the_match(self):
        with self.assertRaises(ToolError):
            body(find_resource_providers)(
                ctx_for(self._client()),
                resource_definition_name="kubernetes-cluster",
                version="9.9.9",
            )


#: What get_deployment_config returns: metadata keys alongside the merged
#: effective configuration, which is what the projections operate on.
SAMPLE_CONFIG = {
    "instance_name": "gui",
    "repo_name": "hmd-app-neuronsphere",
    "version": "0.1",
    "deployment_id": "dep-1",
    "hmd_region": "reg1",
    "dependencies": {"api": [{"instance_name": "deployment-svc"}]},
    "database": {"host": "db.internal", "port": 5432},
    "replicas": 2,
}


def config_client(config=None, **extra):
    return FakeClient(
        get_deployment_config=APIResponse(
            success=True, data=SAMPLE_CONFIG if config is None else config
        ),
        **extra,
    )


class TestGetInstanceConfiguration(unittest.TestCase):
    def test_metadata_keys_are_excluded_from_the_configuration(self):
        result = body(get_instance_configuration)(
            ctx_for(config_client()), environment="dev", instance_name="gui"
        )
        self.assertEqual(set(result["configuration"]), {"database", "replicas"})

    def test_it_costs_one_call_and_never_classifies(self):
        """The cheap sibling of describe_instance -- and it must stay cheap."""
        client = config_client()
        body(get_instance_configuration)(
            ctx_for(client), environment="dev", instance_name="gui"
        )
        self.assertEqual(client.count("get_deployment_config"), 1)
        self.assertEqual(client.count("find_repo_class_versions"), 0)
        self.assertEqual(client.count("suggest_resource_dependencies"), 0)
        self.assertEqual(client.count("get_deployment_history"), 0)

    def test_a_path_projects_into_the_configuration(self):
        result = body(get_instance_configuration)(
            ctx_for(config_client()),
            environment="dev",
            instance_name="gui",
            path="database.host",
        )
        self.assertEqual(result["configuration"], "db.internal")

    def test_keys_only_returns_types_rather_than_values(self):
        result = body(get_instance_configuration)(
            ctx_for(config_client()),
            environment="dev",
            instance_name="gui",
            keys_only=True,
        )
        self.assertEqual(
            result["configuration"],
            {"database": "object (2 keys)", "replicas": "number"},
        )

    def test_a_bad_path_names_the_keys_that_do_exist(self):
        with self.assertRaises(ToolError) as ctx:
            body(get_instance_configuration)(
                ctx_for(config_client()),
                environment="dev",
                instance_name="gui",
                path="database.hostname",
            )
        message = str(ctx.exception)
        self.assertIn("host", message)
        self.assertIn("keys_only", message)

    def test_an_undeployed_instance_points_at_describe_environment(self):
        client = FakeClient(get_deployment_config=APIResponse(success=True, data={}))
        with self.assertRaises(ToolError) as ctx:
            body(get_instance_configuration)(
                ctx_for(client), environment="dev", instance_name="nope"
            )
        self.assertIn("describe_environment", str(ctx.exception))


SAMPLE_REPO_CLASSES = [
    {
        "repo_class_name": "hmd-ms-deployment",
        "repo_type": "microservice",
        "summary": "Orchestrates deployments across environments.",
        "capability_count": 14,
        "latest_version": "0.4.12",
    },
    {"repo_class_name": "hmd-inf-k8s", "repo_type": "infrastructure"},
    {"repo_class_name": "hmd-app-neuronsphere", "repo_type": "application"},
]

SAMPLE_DISCOVERY_ENVELOPE = {
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
                }
            ],
            "entry_points": [],
            "related_docs": [
                {"title": "Monitoring guide", "path": "docs/monitoring.rst"}
            ],
            "capability_count": 3,
        },
        {
            "repo_class_name": "hmd-vpc",
            "version": "0.9.1",
            "summary": "Provisions the base VPC; rotates nothing.",
            "score": 2,
            "matched_fields": ["summary"],
            "capabilities": [],
            "entry_points": [],
            "related_docs": [],
            "capability_count": 2,
        },
    ],
    "total": 2,
    "limit": 50,
    "offset": 0,
    "q": "rotate",
    "kind": None,
    "repo_class_name": None,
}


class TestSearchRepoClasses(unittest.TestCase):
    def _client(self, **extra):
        return FakeClient(
            list_repo_classes=APIResponse(success=True, data=SAMPLE_REPO_CLASSES),
            **extra,
        )

    def test_the_whole_catalog_comes_back_sorted_and_paginated(self):
        result = body(search_repo_classes)(ctx_for(self._client()))
        self.assertEqual(
            [rc["repo_class_name"] for rc in result["repo_classes"]],
            ["hmd-app-neuronsphere", "hmd-inf-k8s", "hmd-ms-deployment"],
        )
        self.assertEqual(result["pagination"]["total"], 3)

    def test_the_query_matches_name_or_repo_type(self):
        result = body(search_repo_classes)(ctx_for(self._client()), query="infra")
        self.assertEqual(
            [rc["repo_class_name"] for rc in result["repo_classes"]], ["hmd-inf-k8s"]
        )

    def test_it_costs_one_catalog_read(self):
        client = self._client()
        body(search_repo_classes)(ctx_for(client), query="ms")
        self.assertEqual(client.count("list_repo_classes"), 1)

    def test_offset_and_limit_page_the_result(self):
        result = body(search_repo_classes)(ctx_for(self._client()), limit=1, offset=2)
        self.assertEqual(
            [rc["repo_class_name"] for rc in result["repo_classes"]],
            ["hmd-ms-deployment"],
        )
        self.assertTrue(result["pagination"]["has_prev"])
        self.assertFalse(result["pagination"]["has_next"])

    def test_description_comes_from_the_discovery_summary(self):
        # NERD0013 SPEC0001: list_repo_classes now carries the summary, so the
        # always-empty description this tool used to emit is populated -- and
        # the query matches it, so "what does deployments" finds the service.
        result = body(search_repo_classes)(
            ctx_for(self._client()), query="orchestrates"
        )
        self.assertEqual(
            [
                (rc["repo_class_name"], rc["description"])
                for rc in result["repo_classes"]
            ],
            [("hmd-ms-deployment", "Orchestrates deployments across environments.")],
        )
        self.assertEqual(result["repo_classes"][0]["capability_count"], 14)
        self.assertEqual(result["repo_classes"][0]["latest_version"], "0.4.12")


class TestSearchCapabilities(unittest.TestCase):
    """NERD008 SPEC015: one search_discovery call, rows flattened per capability."""

    def _client(self, **extra):
        return FakeClient(
            search_discovery=APIResponse(success=True, data=SAMPLE_DISCOVERY_ENVELOPE),
            **extra,
        )

    def test_it_costs_one_discovery_search_and_no_catalog_read(self):
        client = self._client()
        body(search_capabilities)(ctx_for(client), query="rotate")
        self.assertEqual(client.count("search_discovery"), 1)
        self.assertEqual(client.count("list_repo_classes"), 0)
        self.assertEqual(client.count("find_repo_class_versions"), 0)

    def test_rows_flatten_capabilities_and_classes_carry_the_summary(self):
        result = body(search_capabilities)(ctx_for(self._client()), query="rotate")

        self.assertEqual(result["query"], "rotate")
        self.assertEqual(
            [
                (r["repo_class_name"], r["version"], r["name"], r["kind"])
                for r in result["capabilities"]
            ],
            [
                (
                    "hmd-cli-monitoring",
                    "1.2.0",
                    "hmd monitoring rotate-logs",
                    "cli_command",
                )
            ],
        )
        self.assertEqual(
            result["capabilities"][0]["location"], "src/python/monitoring/cli.py:40"
        )
        # Every matching class is listed, including the summary-only hit, so
        # the agent can follow up with describe_repo_class(name, version).
        self.assertEqual(
            [
                (c["repo_class_name"], c["version"], c["matched_fields"])
                for c in result["repo_classes"]
            ],
            [
                ("hmd-cli-monitoring", "1.2.0", ["capability.name"]),
                ("hmd-vpc", "0.9.1", ["summary"]),
            ],
        )
        self.assertEqual(result["repo_classes"][0]["capability_count"], 3)
        self.assertEqual(result["pagination"]["total"], 2)

    def test_filters_are_forwarded_verbatim(self):
        captured = {}

        def search_discovery(**kwargs):
            captured.update(kwargs)
            return APIResponse(success=True, data={"items": [], "total": 0})

        client = FakeClient(search_discovery=search_discovery)
        body(search_capabilities)(
            ctx_for(client),
            query="logs",
            kind="cli_command",
            repo_class_name="hmd-cli-",
            limit=5,
            offset=10,
        )
        self.assertEqual(
            captured,
            {
                "q": "logs",
                "kind": "cli_command",
                "repo_class_name": "hmd-cli-",
                "limit": 5,
                "offset": 10,
            },
        )

    def test_an_unknown_kind_is_a_tool_error_before_any_call(self):
        client = self._client()
        with self.assertRaises(ToolError) as ctx:
            body(search_capabilities)(ctx_for(client), kind="bogus")
        self.assertIn("cli_command", str(ctx.exception))
        self.assertEqual(client.count("search_discovery"), 0)

    def test_a_backend_failure_is_a_tool_error(self):
        client = FakeClient(
            search_discovery=APIResponse(success=False, data=None, error="down")
        )
        with self.assertRaises(ToolError) as ctx:
            body(search_capabilities)(ctx_for(client), query="x")
        self.assertIn("down", str(ctx.exception))


class TestDescribeRepoClass(unittest.TestCase):
    def _client(self, **extra):
        responses = dict(
            find_repo_class_versions_page=APIResponse(
                success=True,
                data={
                    "items": [
                        {"version": "0.1", "repo_type": "application"},
                        {"version": "0.2", "repo_type": "application"},
                    ],
                    "total": 2,
                },
            ),
            get_repo_class_version_detail=APIResponse(
                success=True,
                data={
                    "discovery": {"summary": "the GUI"},
                    "dependencies": {
                        "api": {
                            "repo_class_name": "hmd-ms-deployment",
                            "required": "true",
                            "version_spec": "~= 0.1",
                        }
                    },
                    "default_configuration": {"replicas": 1},
                    "_created": "2026-01-01",
                    "_updated": "2026-02-01",
                },
            ),
        )
        responses.update(extra)
        return FakeClient(**responses)

    def test_without_a_version_it_lists_versions_via_the_paged_endpoint(self):
        """The unpaged variant resolves dependencies per version; this must not."""
        client = self._client()
        result = body(describe_repo_class)(
            ctx_for(client), repo_class_name="hmd-app-neuronsphere"
        )
        self.assertEqual([v["version"] for v in result["versions"]], ["0.1", "0.2"])
        self.assertEqual(result["pagination"]["total"], 2)
        self.assertEqual(client.count("find_repo_class_versions_page"), 1)
        self.assertEqual(client.count("find_repo_class_versions"), 0)

    def test_with_a_version_it_returns_the_declared_sections(self):
        client = self._client()
        result = body(describe_repo_class)(
            ctx_for(client), repo_class_name="hmd-app-neuronsphere", version="0.2"
        )
        self.assertEqual(result["discovery"], {"summary": "the GUI"})
        self.assertEqual(result["default_configuration"], {"replicas": 1})
        self.assertEqual(
            result["dependencies"],
            [
                {
                    "role": "api",
                    "repo_class_name": "hmd-ms-deployment",
                    "required": True,
                    "version_spec": "~= 0.1",
                }
            ],
        )
        self.assertEqual(client.count("find_repo_class_versions_page"), 0)

    def test_an_unknown_version_points_back_at_the_listing(self):
        client = self._client(
            get_repo_class_version_detail=APIResponse(success=True, data={})
        )
        with self.assertRaises(ToolError) as ctx:
            body(describe_repo_class)(
                ctx_for(client), repo_class_name="hmd-app-neuronsphere", version="9.9"
            )
        self.assertIn("without a version", str(ctx.exception))


SAMPLE_DEFINITIONS = [
    {
        "resource_definition_name": "kubernetes-cluster",
        "resource_namespace": "kubernetes.neuronsphere.io",
        "version": "0.1.0",
        "description": "a k8s cluster",
        "identifier": "rd-1",
    },
    {
        "resource_definition_name": "database",
        "resource_namespace": "data.neuronsphere.io",
        "version": "0.1.0",
        "description": "a relational database",
        "identifier": "rd-2",
    },
]


class TestListResourceDefinitions(unittest.TestCase):
    def _client(self, **extra):
        responses = dict(
            list_resource_definitions=APIResponse(
                success=True, data=SAMPLE_DEFINITIONS
            ),
        )
        responses.update(extra)
        return FakeClient(**responses)

    def test_definitions_are_sorted_by_namespace_and_name(self):
        result = body(list_resource_definitions)(ctx_for(self._client()))
        self.assertEqual(
            [d["resource_definition_name"] for d in result["definitions"]],
            ["database", "kubernetes-cluster"],
        )

    def test_the_namespaces_in_use_are_reported_for_orientation(self):
        result = body(list_resource_definitions)(ctx_for(self._client()))
        self.assertEqual(
            result["namespaces"],
            ["data.neuronsphere.io", "kubernetes.neuronsphere.io"],
        )

    def test_the_query_also_matches_the_description(self):
        result = body(list_resource_definitions)(
            ctx_for(self._client()), query="relational"
        )
        self.assertEqual(
            [d["resource_definition_name"] for d in result["definitions"]],
            ["database"],
        )

    def test_it_costs_one_catalog_read(self):
        client = self._client()
        body(list_resource_definitions)(ctx_for(client), namespace="data")
        self.assertEqual(client.count("list_resource_definitions"), 1)


class TestFindResourceCandidates(unittest.TestCase):
    def _client(self, **extra):
        responses = dict(
            list_resource_definitions=APIResponse(
                success=True, data=SAMPLE_DEFINITIONS
            ),
            suggest_resource_dependencies=APIResponse(
                success=True,
                data={"candidates": [{"name": "k8s", "identifier": "ri-1"}]},
            ),
        )
        responses.update(extra)
        return FakeClient(**responses)

    def test_candidates_come_back_with_the_definition_they_matched(self):
        result = body(find_resource_candidates)(
            ctx_for(self._client()),
            environment="dev",
            resource_definition_name="kubernetes-cluster",
        )
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["candidates"][0]["name"], "k8s")
        self.assertEqual(result["resource_definition"]["identifier"], "rd-1")

    def test_the_namespace_is_resolved_from_the_definition_when_omitted(self):
        captured = {}

        def suggest(environment, **kwargs):
            captured.update(kwargs)
            return APIResponse(success=True, data={"candidates": []})

        client = self._client(suggest_resource_dependencies=suggest)
        body(find_resource_candidates)(
            ctx_for(client),
            environment="dev",
            resource_definition_name="kubernetes-cluster",
        )
        self.assertEqual(captured["resource_namespace"], "kubernetes.neuronsphere.io")

    def test_a_failed_suggestion_names_the_environment(self):
        client = self._client(
            suggest_resource_dependencies=APIResponse(
                success=False, data=None, error="boom"
            )
        )
        with self.assertRaises(ToolError) as ctx:
            body(find_resource_candidates)(
                ctx_for(client),
                environment="dev",
                resource_definition_name="kubernetes-cluster",
            )
        self.assertIn("dev", str(ctx.exception))


SAMPLE_COMPARE = {
    "deploy_change_set": [
        {"repo_instance_name": "only-here", "repo_class_version": "1.0"},
        {
            "repo_instance_name": "gui",
            "repo_class_name": "hmd-app-neuronsphere",
            "repo_class_version": "0.2",
            "instance_configuration": {"replicas": 2},
        },
    ],
    "existing_change_set": [
        {
            "repo_instance_name": "gui",
            "repo_class_name": "hmd-app-neuronsphere",
            "repo_class_version": "0.1",
            "instance_configuration": {"replicas": 1},
        }
    ],
    "removed_instances": ["gone"],
}


class TestCompareEnvironments(unittest.TestCase):
    def _client(self, **extra):
        responses = dict(
            compare_environments=APIResponse(success=True, data=SAMPLE_COMPARE),
        )
        responses.update(extra)
        return FakeClient(**responses)

    def test_the_summary_is_names_and_flags_rather_than_diffs(self):
        result = body(compare_environments)(
            ctx_for(self._client()), from_environment="dev", to_environment="prod"
        )
        self.assertEqual(
            result["summary"],
            {"only_in_source": 1, "only_in_target": 1, "modified": 1},
        )
        self.assertEqual(result["only_in_source"], ["only-here"])
        self.assertEqual(result["only_in_target"], ["gone"])
        modified = result["modified"][0]
        self.assertEqual(modified["version_change"], {"old": "0.1", "new": "0.2"})
        self.assertTrue(modified["config_changed"])
        # The summary must not carry the deltas themselves; that is the point.
        self.assertNotIn("config_diff", modified)

    def test_full_detail_carries_the_configuration_delta(self):
        result = body(compare_environments)(
            ctx_for(self._client()),
            from_environment="dev",
            to_environment="prod",
            detail="full",
        )
        self.assertEqual(
            result["modified"][0]["config_diff"]["changed"],
            {"replicas": {"old": 1, "new": 2}},
        )

    def test_it_costs_one_comparison_and_reads_no_bom(self):
        client = self._client()
        body(compare_environments)(
            ctx_for(client), from_environment="dev", to_environment="prod"
        )
        self.assertEqual(client.count("compare_environments"), 1)
        self.assertEqual(client.count("get_deployment_bom"), 0)

    def test_a_failed_comparison_names_both_environments(self):
        client = self._client(
            compare_environments=APIResponse(success=False, data=None, error="boom")
        )
        with self.assertRaises(ToolError) as ctx:
            body(compare_environments)(
                ctx_for(client), from_environment="dev", to_environment="prod"
            )
        self.assertIn("dev", str(ctx.exception))
        self.assertIn("prod", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
