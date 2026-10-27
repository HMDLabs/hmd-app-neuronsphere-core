"""The gateway's discovery surfaces (NERD012): the registry listing and the tool.

``GET <mount>/registry/v0/servers`` answers in the official MCP Registry's
``server.json`` shape, so any registry-aware client can browse it; every entry
points back at this gateway and lists only the environments the caller may use.
``list_mcp_servers`` is the same answer from inside an MCP session.
"""

import asyncio
from unittest import mock

import httpx
from django.test import override_settings
from fastmcp import FastMCP
from httpx import ASGITransport

from ns_mcp.auth import ApiKeyVerifier
from ns_mcp.gateway.catalog import REGISTRY_NAMESPACE, add_catalog_routes
from ns_mcp.tooling import ToolContext
from ns_mcp.gateway.provider import GatewayProvider
from ns_mcp.gateway.registry import GatewayRegistry
from tests.test_mcp_gateway_provider import (
    FakeTokenSource,
    GatewayTestCase,
    _servers,
)


class CatalogTestCase(GatewayTestCase):
    def setUp(self):
        super().setUp()
        gateway = FastMCP("gateway", auth=ApiKeyVerifier())
        gateway.add_provider(self.provider)
        add_catalog_routes(gateway, self.provider, ApiKeyVerifier())
        self.app = gateway.http_app(path="/", stateless_http=True)

    def get(self, path, username=None):
        headers = {}
        if username:
            headers["Authorization"] = f"Bearer {self.keys[username]}"

        async def scenario():
            async with httpx.AsyncClient(
                transport=ASGITransport(app=self.app), base_url="http://gw.example"
            ) as client:
                return await client.get(path, headers=headers)

        return asyncio.run(scenario())


class TestRegistryListing(CatalogTestCase):
    def test_listing_requires_a_bearer(self):
        response = self.get("/registry/v0/servers")
        self.assertEqual(response.status_code, 401)
        self.assertIn("Bearer", response.headers.get("www-authenticate", ""))

    def test_one_entry_per_logical_server_in_registry_shape(self):
        body = self.get("/registry/v0/servers", "gw_alice").json()
        names = [entry["server"]["name"] for entry in body["servers"]]
        self.assertEqual(names, [f"{REGISTRY_NAMESPACE}/echo"])
        self.assertEqual(body["metadata"]["count"], 1)

        server = body["servers"][0]["server"]
        self.assertEqual(server["title"], "Echo")
        self.assertEqual(
            server["remotes"],
            [{"type": "streamable-http", "url": "http://gw.example/mcp/"}],
        )
        meta = body["servers"][0]["_meta"][f"{REGISTRY_NAMESPACE}/gateway"]
        self.assertEqual(meta["tool_prefix"], "echo__")
        self.assertEqual(
            [e["name"] for e in meta["environments"]], ["dev", "prod", "test"]
        )

    def test_listing_is_filtered_to_the_callers_environments(self):
        body = self.get("/registry/v0/servers", "gw_dana").json()
        meta = body["servers"][0]["_meta"][f"{REGISTRY_NAMESPACE}/gateway"]
        self.assertEqual([e["name"] for e in meta["environments"]], ["dev"])
        self.assertEqual(
            self.get("/registry/v0/servers", "gw_nobody").json()["servers"], []
        )

    def test_a_single_server_by_name(self):
        ok = self.get(f"/registry/v0/servers/{REGISTRY_NAMESPACE}/echo", "gw_dana")
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["server"]["name"], f"{REGISTRY_NAMESPACE}/echo")
        # Unreachable and nonexistent are indistinguishable.
        self.assertEqual(
            self.get(
                f"/registry/v0/servers/{REGISTRY_NAMESPACE}/ops", "gw_dana"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.get(
                f"/registry/v0/servers/{REGISTRY_NAMESPACE}/nope", "gw_dana"
            ).status_code,
            404,
        )

    @override_settings(MCP_BASE_URL="https://ns.example.com")
    def test_the_advertised_url_prefers_the_configured_base(self):
        body = self.get("/registry/v0/servers", "gw_dana").json()
        self.assertEqual(
            body["servers"][0]["server"]["remotes"][0]["url"],
            "https://ns.example.com/mcp/",
        )


class TestListMcpServersTool(CatalogTestCase):
    def test_lists_reachable_servers_for_the_caller(self):
        from ns_mcp.principal import AUTH_MODE_API_KEY, Principal
        from ns_mcp.tools.gateway import list_mcp_servers

        principal = Principal(
            user_id=self.dana.pk,
            username="gw_dana",
            auth_mode=AUTH_MODE_API_KEY,
            raw_token="",
        )
        with mock.patch("ns_mcp.tools.gateway.get_gateway", return_value=self.provider):
            result = list_mcp_servers.__wrapped__(
                ToolContext(self.dana, principal, None)
            )

        self.assertTrue(result["enabled"])
        self.assertEqual([s["server_name"] for s in result["servers"]], ["echo"])
        self.assertEqual(result["servers"][0]["environments"], ["dev"])
        self.assertEqual(result["servers"][0]["tool_prefix"], "echo__")

    def test_reports_a_disabled_gateway(self):
        from ns_mcp.tools.gateway import list_mcp_servers

        with mock.patch("ns_mcp.tools.gateway.get_gateway", return_value=None):
            result = list_mcp_servers.__wrapped__(ToolContext(self.dana, None, None))
        self.assertEqual(result, {"enabled": False, "servers": []})


class TestToolsUnavailable(CatalogTestCase):
    """A server listed with no tools says why, instead of the reason being only in
    the pod log."""

    def servers_for(self, provider, username="gw_dana"):
        from ns_mcp.principal import AUTH_MODE_API_KEY, Principal
        from ns_mcp.tools.gateway import list_mcp_servers

        user = {"gw_dana": self.dana, "gw_root": self.root}[username]
        principal = Principal(
            user_id=user.pk,
            username=username,
            auth_mode=AUTH_MODE_API_KEY,
            raw_token="",
        )
        with mock.patch("ns_mcp.tools.gateway.get_gateway", return_value=provider):
            result = list_mcp_servers.__wrapped__(ToolContext(user, principal, None))
        return {s["server_name"]: s for s in result["servers"]}

    def test_a_deployment_the_gateway_can_call_reports_nothing(self):
        self.tools("gw_dana")
        deployment = self.servers_for(self.provider)["echo"]["deployments"][0]
        self.assertNotIn("tools_unavailable", deployment)

    def test_a_service_mode_server_without_a_gateway_credential_says_so(self):
        servers = _servers()  # no credential_ref
        provider = GatewayProvider(
            registry=GatewayRegistry(loader=lambda: servers, ttl=60),
            client_factory=self.provider.client_factory,
            token_source=FakeTokenSource(configured=False),
        )
        deployment = self.servers_for(provider)["echo"]["deployments"][0]
        self.assertIn("no credential for 'echo'", deployment["tools_unavailable"])

    def test_an_upstream_that_fails_to_list_reports_the_failure(self):
        def failing_factory(endpoint, headers):
            raise ConnectionError("upstream detail that must not leak")

        servers = _servers(credential_ref="echo-token")
        self.provider = GatewayProvider(
            registry=GatewayRegistry(loader=lambda: servers, ttl=60),
            client_factory=failing_factory,
        )
        gateway = FastMCP("gateway", auth=ApiKeyVerifier())
        gateway.add_provider(self.provider)
        self.app = gateway.http_app(path="/", stateless_http=True)

        self.assertEqual(self.tools("gw_dana"), {})
        problem = self.servers_for(self.provider)["echo"]["deployments"][0][
            "tools_unavailable"
        ]
        self.assertIn("ConnectionError", problem)
        self.assertNotIn("must not leak", problem)
