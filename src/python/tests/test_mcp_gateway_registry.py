"""Unit tests for the MCP gateway's registry (NERD012).

The registry turns ``mcp.neuronsphere.io/mcp-server`` Resources -- one per
environment a server is deployed in -- into logical servers keyed by
``server_name``. Grouping, parsing, and caching are pure enough to test without
an MCP transport; the provider that serves them is covered separately.
"""

import unittest

from deployments.services.api_client import APIResponse
from ns_mcp.gateway.registry import (
    DISCOVERY_TAG,
    GatewayRegistry,
    discover,
    endpoint_from_output,
    parse_static_endpoints,
)


def _resource(server_name, url, **output):
    return {
        "resource_name": f"{server_name}-mcp",
        "output": {"server_name": server_name, "url": url, **output},
    }


class FakeClient:
    """Answers list_environments and the per-environment selector query."""

    def __init__(self, by_environment, failing=()):
        self.by_environment = by_environment
        self.failing = set(failing)
        self.selector_calls = []

    def list_environments(self):
        return APIResponse(
            success=True,
            data=[{"type": env} for env in sorted(self.by_environment)],
        )

    def find_resources_by_selector(self, tags, environment=None):
        self.selector_calls.append((dict(tags), environment))
        if environment in self.failing:
            return APIResponse(success=False, data=None, error="boom", status_code=500)
        return APIResponse(success=True, data=self.by_environment.get(environment, []))


class TestStaticEndpoints(unittest.TestCase):
    def test_server_at_environment_entries_are_parsed(self):
        endpoints = parse_static_endpoints(
            "echo@dev=http://dev-echo/mcp,"
            "echo@test=http://test-echo/mcp;auth=passthrough;role=deployer,"
            "trino@prod=http://trino/mcp;cred=trino-token"
        )
        by_key = {(e.server_name, e.environment): e for e in endpoints}
        self.assertEqual(
            set(by_key), {("echo", "dev"), ("echo", "test"), ("trino", "prod")}
        )
        self.assertEqual(by_key[("echo", "dev")].url, "http://dev-echo/mcp")
        self.assertEqual(by_key[("echo", "dev")].auth_mode, "service")
        self.assertEqual(by_key[("echo", "dev")].required_role, "viewer")
        self.assertEqual(by_key[("echo", "test")].auth_mode, "passthrough")
        self.assertEqual(by_key[("echo", "test")].required_role, "deployer")
        self.assertEqual(by_key[("trino", "prod")].credential_ref, "trino-token")

    def test_entries_without_an_environment_are_skipped(self):
        # The pre-gateway ``namespace=url`` form named no environment, and an
        # endpoint with no environment cannot be authorized against anything.
        self.assertEqual(parse_static_endpoints("echo=http://echo/mcp"), [])

    def test_malformed_entries_are_skipped_not_fatal(self):
        endpoints = parse_static_endpoints(
            "Bad Name@dev=http://x/mcp,echo@dev=,@dev=http://y,"
            "echo@dev=http://ok/mcp;auth=sideways,echo@test=http://ok/mcp"
        )
        self.assertEqual(
            [(e.server_name, e.environment) for e in endpoints], [("echo", "test")]
        )

    def test_empty_config_yields_nothing(self):
        self.assertEqual(parse_static_endpoints(""), [])
        self.assertEqual(parse_static_endpoints(None), [])


class TestEndpointFromOutput(unittest.TestCase):
    def test_defaults_are_service_auth_and_viewer_role(self):
        endpoint = endpoint_from_output(
            {"server_name": "trino", "url": "http://trino/mcp"}, "dev", "trino-mcp"
        )
        self.assertEqual(endpoint.auth_mode, "service")
        self.assertEqual(endpoint.required_role, "viewer")
        self.assertEqual(endpoint.environment, "dev")
        self.assertEqual(endpoint.resource_name, "trino-mcp")

    def test_output_without_url_or_server_name_is_rejected(self):
        self.assertIsNone(endpoint_from_output({"url": "http://x"}, "dev", "r"))
        self.assertIsNone(endpoint_from_output({"server_name": "x"}, "dev", "r"))

    def test_unknown_auth_mode_or_role_is_rejected(self):
        base = {"server_name": "x", "url": "http://x"}
        self.assertIsNone(
            endpoint_from_output({**base, "auth_mode": "magic"}, "dev", "r")
        )
        self.assertIsNone(
            endpoint_from_output({**base, "required_role": "owner"}, "dev", "r")
        )

    def test_unauthenticated_none_mode_is_static_only(self):
        # `none` is for local fixtures configured by an operator. A deployed
        # producer must not be able to opt its server out of upstream auth.
        self.assertIsNone(
            endpoint_from_output(
                {"server_name": "x", "url": "http://x", "auth_mode": "none"}, "dev", "r"
            )
        )
        (endpoint,) = parse_static_endpoints("echo@dev=http://echo/mcp;auth=none")
        self.assertEqual(endpoint.auth_mode, "none")

    def test_credential_ref_must_be_a_plain_name(self):
        # It names a file under MCP_GATEWAY_CREDENTIALS_DIR; a path would let a
        # producer point the gateway at any file it can read.
        base = {"server_name": "x", "url": "http://x"}
        self.assertIsNone(
            endpoint_from_output(
                {**base, "credential_ref": "../etc/passwd"}, "dev", "r"
            )
        )


class TestDiscover(unittest.TestCase):
    def test_same_server_in_several_environments_is_one_logical_server(self):
        client = FakeClient(
            {
                "dev": [_resource("trino", "http://dev-trino/mcp", title="Trino")],
                "test": [_resource("trino", "http://test-trino/mcp")],
                "prod": [
                    _resource("trino", "http://prod-trino/mcp"),
                    _resource("clickhouse", "http://prod-ch/mcp"),
                ],
            }
        )
        servers = discover(client, static="")

        self.assertEqual(set(servers), {"trino", "clickhouse"})
        self.assertEqual(set(servers["trino"].endpoints), {"dev", "test", "prod"})
        self.assertEqual(
            servers["trino"].endpoints["test"].url, "http://test-trino/mcp"
        )
        self.assertEqual(servers["trino"].title, "Trino")
        self.assertEqual(set(servers["clickhouse"].endpoints), {"prod"})

    def test_discovery_selects_on_the_mcp_server_tag_per_environment(self):
        client = FakeClient({"dev": [], "prod": []})
        discover(client, static="")
        self.assertEqual(
            client.selector_calls,
            [
                ({DISCOVERY_TAG[0]: DISCOVERY_TAG[1]}, "dev"),
                ({DISCOVERY_TAG[0]: DISCOVERY_TAG[1]}, "prod"),
            ],
        )

    def test_a_failing_environment_is_dropped_not_fatal(self):
        client = FakeClient(
            {
                "dev": [_resource("trino", "http://dev-trino/mcp")],
                "prod": [_resource("trino", "http://prod-trino/mcp")],
            },
            failing={"prod"},
        )
        servers = discover(client, static="")
        self.assertEqual(set(servers["trino"].endpoints), {"dev"})

    def test_invalid_resources_are_skipped(self):
        client = FakeClient({"dev": [{"resource_name": "junk", "output": {}}]})
        self.assertEqual(discover(client, static=""), {})

    def test_static_endpoints_merge_with_discovered_ones(self):
        client = FakeClient({"dev": [_resource("trino", "http://dev-trino/mcp")]})
        servers = discover(client, static="trino@local=http://localhost:9/mcp")
        self.assertEqual(set(servers["trino"].endpoints), {"dev", "local"})

    def test_no_client_means_static_only(self):
        servers = discover(None, static="echo@dev=http://echo/mcp")
        self.assertEqual(set(servers), {"echo"})


class TestGatewayRegistryCaching(unittest.TestCase):
    def test_snapshot_is_cached_until_the_ttl_expires(self):
        now = [1000.0]
        calls = []

        def loader():
            calls.append(now[0])
            return {}

        registry = GatewayRegistry(loader=loader, ttl=60, clock=lambda: now[0])
        registry.snapshot()
        registry.snapshot()
        self.assertEqual(len(calls), 1)

        now[0] += 61
        registry.snapshot()
        self.assertEqual(len(calls), 2)

    def test_a_failed_refresh_keeps_serving_the_last_good_snapshot(self):
        now = [0.0]
        results = [{"echo": "first"}]

        def loader():
            value = results.pop(0)
            if isinstance(value, Exception):
                raise value
            return value

        registry = GatewayRegistry(loader=loader, ttl=10, clock=lambda: now[0])
        self.assertEqual(registry.snapshot(), {"echo": "first"})
        results.append(RuntimeError("deployment service down"))
        now[0] += 11
        self.assertEqual(registry.snapshot(), {"echo": "first"})


class TestDefaultRegistryWithoutServiceToken(unittest.TestCase):
    """Discovery runs as the service account; without a token it must not run.

    An anonymous selector query is refused by the deployment service's authorizer
    in every environment, which read as "no MCP servers" with only a per-environment
    Unauthorized to go on. Skip discovery with one warning naming the cause, and
    keep serving the static endpoints.
    """

    def test_no_service_token_skips_discovery_but_keeps_static_endpoints(self):
        from unittest import mock

        from django.test import override_settings

        from ns_mcp.gateway.registry import default_registry

        client = mock.Mock(auth_token=None)
        with (
            override_settings(
                MCP_GATEWAY_DISCOVERY_ENABLED=True,
                MCP_GATEWAY_ENDPOINTS="echo@dev=http://echo/mcp",
                MCP_GATEWAY_REGISTRY_TTL=60,
            ),
            mock.patch("deployments.services.auth.get_api_client", return_value=client),
            self.assertLogs("ns_mcp.gateway.registry", level="WARNING") as logs,
        ):
            servers = default_registry().snapshot()

        client.find_resources_by_selector.assert_not_called()
        client.list_environments.assert_not_called()
        self.assertEqual(set(servers), {"echo"})
        self.assertTrue(any("SERVICE_CLIENT_ID" in line for line in logs.output))
