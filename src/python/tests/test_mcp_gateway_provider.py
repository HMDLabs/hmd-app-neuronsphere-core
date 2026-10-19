"""The MCP gateway end to end: one logical server across environments (NERD012).

A real FastMCP gateway is served over Streamable HTTP with API-key auth, exactly
as ``/mcp`` is in production. Its upstreams are in-memory FastMCP servers -- one
per environment -- reached through the provider's injectable client factory, so
every call the gateway forwards (and every header it forwards it with) is
observable.

The behaviour under test is the one the gateway exists for: the same server
deployed in dev, test and prod appears once; each tool gains an ``environment``
argument limited to the environments the caller may use; and a caller naming an
environment they may not use is refused *before* anything is sent upstream.
"""
import asyncio
import os
import tempfile
import unittest

import httpx
from django.contrib.auth.models import User
from django.test import override_settings
from fastmcp import Client, FastMCP
from httpx import ASGITransport

from deployments.models import AuditLog, MCPApiKey, UserEnvironmentPermission
from ns_mcp.auth import ApiKeyVerifier
from ns_mcp.gateway.provider import GatewayProvider
from ns_mcp.gateway.registry import Endpoint, GatewayRegistry, LogicalServer
from ns_mcp.gateway.upstream import (
    GATEWAY_HOP_HEADER,
    GatewayCallError,
    upstream_headers,
)
from ns_mcp.principal import AUTH_MODE_API_KEY, AUTH_MODE_OKTA, Principal
from tests.test_mcp_server import MCP_HEADERS, _parse_rpc


def _upstream(environment):
    """A stand-in for one environment's deployment of an MCP server."""
    server = FastMCP(f"echo-{environment}")

    @server.tool
    def echo(text: str) -> str:
        """Echo text back, tagged with the environment that answered."""
        return f"{environment}:{text}"

    @server.tool
    def scoped(environment: str) -> str:
        """An upstream tool that already has its own `environment` argument."""
        return f"upstream-saw:{environment}"

    if environment == "dev":

        @server.tool
        def dev_only() -> str:
            """Only deployed in dev."""
            return "dev-only"

    return server


def _endpoint(server_name, environment, **kwargs):
    return Endpoint(
        server_name=server_name,
        environment=environment,
        url=f"http://{server_name}-{environment}.invalid/mcp",
        **kwargs,
    )


def _servers(credential_ref=None):
    echo = LogicalServer(name="echo", title="Echo", description="Echoes text.")
    for env in ("dev", "test", "prod"):
        echo.endpoints[env] = _endpoint("echo", env, credential_ref=credential_ref)
    ops = LogicalServer(name="ops", title="Ops", description="Needs deploy rights.")
    ops.endpoints["dev"] = _endpoint(
        "ops", "dev", required_role="deployer", credential_ref=credential_ref
    )
    relay = LogicalServer(name="relay", title="Relay", description="Passthrough.")
    relay.endpoints["dev"] = _endpoint("relay", "dev", auth_mode="passthrough")
    return {"echo": echo, "ops": ops, "relay": relay}


class GatewayTestCase(unittest.TestCase):
    def setUp(self):
        self.credentials_dir = tempfile.mkdtemp()
        with open(os.path.join(self.credentials_dir, "echo-token"), "w") as fh:
            fh.write("s3cret\n")
        self.settings = override_settings(
            MCP_GATEWAY_CREDENTIALS_DIR=self.credentials_dir
        )
        self.settings.enable()
        self.addCleanup(self.settings.disable)

        self.upstreams = {env: _upstream(env) for env in ("dev", "test", "prod")}
        self.forwarded = []  # (server, environment, headers) per upstream client

        def client_factory(endpoint, headers):
            self.forwarded.append((endpoint.server_name, endpoint.environment, headers))
            return Client(self.upstreams[endpoint.environment])

        servers = _servers(credential_ref="echo-token")
        self.provider = GatewayProvider(
            registry=GatewayRegistry(loader=lambda: servers, ttl=60),
            client_factory=client_factory,
        )
        gateway = FastMCP("gateway", auth=ApiKeyVerifier())
        gateway.add_provider(self.provider)
        self.app = gateway.http_app(path="/", stateless_http=True)

        self.dana = User.objects.create_user("gw_dana")  # dev only
        UserEnvironmentPermission.objects.create(
            user=self.dana, environment="dev", role="viewer"
        )
        self.alice = User.objects.create_user("gw_alice")  # dev, test, prod
        for env in ("dev", "test", "prod"):
            UserEnvironmentPermission.objects.create(
                user=self.alice, environment=env, role="viewer"
            )
        self.devon = User.objects.create_user("gw_devon")  # deployer in dev
        UserEnvironmentPermission.objects.create(
            user=self.devon, environment="dev", role="deployer"
        )
        self.root = User.objects.create_superuser("gw_root")
        self.nobody = User.objects.create_user("gw_nobody")
        self.keys = {
            user.username: MCPApiKey.generate(user, "tests")[1]
            for user in (self.dana, self.alice, self.devon, self.root, self.nobody)
        }

    # -- JSON-RPC plumbing -------------------------------------------------

    def _rpc(self, username, method, params=None, extra_headers=None):
        async def scenario():
            async with self.app.router.lifespan_context(self.app):
                async with httpx.AsyncClient(
                    transport=ASGITransport(app=self.app), base_url="http://localhost"
                ) as client:
                    response = await client.post(
                        "/",
                        json={
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": method,
                            "params": params or {},
                        },
                        headers=dict(
                            MCP_HEADERS,
                            Authorization=f"Bearer {self.keys[username]}",
                            **(extra_headers or {}),
                        ),
                    )
                    return _parse_rpc(response.text)

        return asyncio.run(scenario())

    def tools(self, username):
        return {
            t["name"]: t for t in self._rpc(username, "tools/list")["result"]["tools"]
        }

    def call(self, username, name, arguments=None):
        return self._rpc(
            username, "tools/call", {"name": name, "arguments": arguments or {}}
        )["result"]

    @staticmethod
    def text(result):
        return result["content"][0]["text"]


class TestToolsList(GatewayTestCase):
    def test_one_logical_server_not_one_per_environment(self):
        names = set(self.tools("gw_alice"))
        self.assertIn("echo__echo", names)
        self.assertFalse(
            any("dev" in n or "prod" in n for n in names - {"echo__dev_only"})
        )

    def test_environment_enum_is_limited_to_the_callers_grants(self):
        dana = self.tools("gw_dana")["echo__echo"]["inputSchema"]
        alice = self.tools("gw_alice")["echo__echo"]["inputSchema"]
        self.assertEqual(dana["properties"]["environment"]["enum"], ["dev"])
        self.assertEqual(
            sorted(alice["properties"]["environment"]["enum"]), ["dev", "prod", "test"]
        )

    def test_environment_is_optional_only_when_there_is_one_choice(self):
        dana = self.tools("gw_dana")["echo__echo"]["inputSchema"]
        alice = self.tools("gw_alice")["echo__echo"]["inputSchema"]
        self.assertNotIn("environment", dana.get("required", []))
        self.assertIn("environment", alice.get("required", []))
        # The upstream's own arguments are untouched.
        self.assertIn("text", alice["required"])

    def test_superuser_sees_every_environment(self):
        schema = self.tools("gw_root")["echo__echo"]["inputSchema"]
        self.assertEqual(
            sorted(schema["properties"]["environment"]["enum"]), ["dev", "prod", "test"]
        )

    def test_servers_the_caller_cannot_reach_are_hidden(self):
        self.assertFalse(self.tools("gw_nobody"))

    def test_required_role_is_respected_when_listing(self):
        self.assertNotIn("ops__echo", self.tools("gw_dana"))
        self.assertIn("ops__echo", self.tools("gw_devon"))

    def test_a_tool_missing_from_some_environments_only_offers_those_that_have_it(self):
        schema = self.tools("gw_alice")["echo__dev_only"]["inputSchema"]
        self.assertEqual(schema["properties"]["environment"]["enum"], ["dev"])

    def test_a_request_forwarded_by_a_gateway_is_not_offered_gateway_tools(self):
        # Two gateways pointed at each other -- or one at its own /mcp -- would
        # otherwise list each other's tools without end.
        listed = self._rpc(
            "gw_alice", "tools/list", extra_headers={GATEWAY_HOP_HEADER: "1"}
        )["result"]["tools"]
        self.assertEqual(listed, [])
        self.forwarded.clear()
        result = self._rpc(
            "gw_alice",
            "tools/call",
            {"name": "echo__echo", "arguments": {"text": "x", "environment": "dev"}},
            extra_headers={GATEWAY_HOP_HEADER: "1"},
        )
        self.assertTrue(result.get("error") or result["result"].get("isError"))
        self.assertEqual(self.forwarded, [])

    def test_an_upstream_environment_argument_is_not_shadowed(self):
        schema = self.tools("gw_alice")["echo__scoped"]["inputSchema"]
        self.assertIn("environment", schema["properties"])  # the upstream's own
        self.assertEqual(
            sorted(schema["properties"]["ns_environment"]["enum"]),
            ["dev", "prod", "test"],
        )


class TestToolsCall(GatewayTestCase):
    def test_single_environment_caller_routes_without_naming_it(self):
        result = self.call("gw_dana", "echo__echo", {"text": "hi"})
        self.assertFalse(result.get("isError"), result)
        self.assertEqual(self.text(result), "dev:hi")

    def test_multi_environment_caller_routes_to_the_one_named(self):
        for env in ("dev", "test", "prod"):
            with self.subTest(environment=env):
                result = self.call(
                    "gw_alice", "echo__echo", {"text": "hi", "environment": env}
                )
                self.assertEqual(self.text(result), f"{env}:hi")

    def test_multi_environment_caller_must_name_one(self):
        result = self.call("gw_alice", "echo__echo", {"text": "hi"})
        self.assertTrue(result["isError"])
        self.assertIn("environment", self.text(result))

    def test_a_forged_environment_is_denied_before_anything_is_sent_upstream(self):
        self.forwarded.clear()
        result = self.call(
            "gw_dana", "echo__echo", {"text": "hi", "environment": "prod"}
        )
        self.assertTrue(result["isError"])
        self.assertIn("prod", self.text(result))
        self.assertEqual(
            [f for f in self.forwarded if f[1] == "prod"],
            [],
            "a denied call must not reach the upstream",
        )
        row = AuditLog.objects.filter(user=self.dana, success=False).latest("timestamp")
        self.assertEqual(row.details["transport"], "mcp-gateway")
        self.assertEqual(row.details["server"], "echo")
        self.assertEqual(row.details["environment"], "prod")

    def test_successful_calls_are_audited(self):
        self.call("gw_alice", "echo__echo", {"text": "hi", "environment": "test"})
        row = AuditLog.objects.filter(user=self.alice, success=True).latest("timestamp")
        self.assertEqual(row.details["transport"], "mcp-gateway")
        self.assertEqual(row.details["tool"], "echo")
        self.assertEqual(row.details["environment"], "test")
        self.assertNotIn(
            "text", row.details.get("arguments", {})
        )  # payloads not logged

    def test_injected_argument_is_stripped_and_upstream_argument_is_kept(self):
        result = self.call(
            "gw_alice",
            "echo__scoped",
            {"environment": "theirs", "ns_environment": "test"},
        )
        self.assertEqual(self.text(result), "upstream-saw:theirs")

    def test_service_mode_forwards_the_gateway_credential_and_caller_identity(self):
        self.forwarded.clear()
        self.call("gw_dana", "echo__echo", {"text": "hi"})
        server, env, headers = self.forwarded[-1]
        self.assertEqual((server, env), ("echo", "dev"))
        self.assertEqual(headers["Authorization"], "Bearer s3cret")
        self.assertEqual(headers["X-NS-User"], "gw_dana")
        self.assertEqual(headers["X-NS-Environment"], "dev")
        self.assertTrue(headers["X-Request-Id"])
        self.assertEqual(headers[GATEWAY_HOP_HEADER], "1")

    def test_passthrough_server_refuses_api_key_callers(self):
        self.assertNotIn("relay__echo", self.tools("gw_dana"))


class TestUpstreamHeaders(unittest.TestCase):
    def _principal(self, mode):
        return Principal(
            user_id=1, username="alice", auth_mode=mode, raw_token="user-jwt"
        )

    def test_passthrough_forwards_the_callers_own_token(self):
        headers = upstream_headers(
            _endpoint("relay", "dev", auth_mode="passthrough"),
            self._principal(AUTH_MODE_OKTA),
            request_id="r1",
        )
        self.assertEqual(headers["Authorization"], "Bearer user-jwt")
        self.assertEqual(headers["X-NS-Environment"], "dev")

    def test_passthrough_rejects_an_api_key_principal(self):
        with self.assertRaises(GatewayCallError):
            upstream_headers(
                _endpoint("relay", "dev", auth_mode="passthrough"),
                self._principal(AUTH_MODE_API_KEY),
                request_id="r1",
            )

    @override_settings(MCP_GATEWAY_CREDENTIALS_DIR="/nonexistent-ns-mcp-creds")
    def test_a_missing_service_credential_is_an_error_not_an_anonymous_call(self):
        with self.assertRaises(GatewayCallError):
            upstream_headers(
                _endpoint("echo", "dev", credential_ref="echo-token"),
                self._principal(AUTH_MODE_OKTA),
                request_id="r1",
            )

    def test_service_mode_without_a_credential_ref_sends_identity_only(self):
        headers = upstream_headers(
            _endpoint("echo", "dev"), self._principal(AUTH_MODE_OKTA), request_id="r1"
        )
        self.assertNotIn("Authorization", headers)
        self.assertEqual(headers["X-NS-User"], "alice")
