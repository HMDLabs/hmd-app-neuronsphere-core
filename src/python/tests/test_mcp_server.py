"""End-to-end tests driving the real ASGI application over MCP's JSON-RPC.

These exercise the whole composition -- Starlette router, FastMCP transport,
bearer auth, the threadpool hop, per-environment authorization, and the audit
trail -- rather than any single unit. They are the regression test for the
WSGI-to-ASGI switch: if Django stops being served, or /mcp stops requiring a
token, they fail.
"""
import asyncio
import json
import unittest

import httpx
from django.contrib.auth.models import User
from httpx import ASGITransport

from deployments.models import AuditLog, MCPApiKey, UserEnvironmentPermission

MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


def _parse_rpc(text):
    """Read a JSON-RPC payload out of either a plain or SSE-framed response."""
    for line in text.splitlines():
        if line.startswith("data: "):
            return json.loads(line[6:])
    return json.loads(text) if text.strip() else None


class MCPServerTestCase(unittest.TestCase):
    """Base class providing a client bound to the real ASGI app."""

    @classmethod
    def setUpClass(cls):
        from deployment_gui.asgi import application

        cls.application = application

    def _run(self, coro):
        return asyncio.run(coro)

    async def _session(self, client, api_key):
        """Complete the MCP initialize handshake, returning usable headers."""
        headers = dict(MCP_HEADERS, Authorization=f"Bearer {api_key}")
        response = await client.post(
            "/mcp/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "tests", "version": "1"},
                },
            },
            headers=headers,
        )
        self.assertEqual(response.status_code, 200, response.text[:300])
        if response.headers.get("mcp-session-id"):
            headers["Mcp-Session-Id"] = response.headers["mcp-session-id"]
        await client.post(
            "/mcp/",
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers=headers,
        )
        return headers

    async def _rpc(self, client, headers, method, params=None):
        response = await client.post(
            "/mcp/",
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": method,
                "params": params or {},
            },
            headers=headers,
        )
        return _parse_rpc(response.text)

    async def _call_tool(self, client, headers, name, arguments=None):
        response = await client.post(
            "/mcp/",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments or {}},
            },
            headers=headers,
        )
        return _parse_rpc(response.text)

    def _client(self):
        return httpx.AsyncClient(
            transport=ASGITransport(app=self.application),
            base_url="http://localhost",
        )


class TestTransport(MCPServerTestCase):
    def test_django_is_still_served_alongside_mcp(self):
        async def scenario():
            async with self.application.router.lifespan_context(self.application):
                async with self._client() as client:
                    return await client.get("/health/")

        response = self._run(scenario())
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "healthy")
        # Only a process that went through deployment_gui/asgi.py has built the
        # MCP server, so this doubles as proof of the ASGI entry point.
        self.assertTrue(payload["mcp"]["built"])
        self.assertIn("list_environments", payload["mcp"]["tool_names"])
        # Resources and prompts are counted separately from tools, so a
        # capability that failed to register cannot hide in the tool count.
        self.assertEqual(
            payload["mcp"]["resources"], len(payload["mcp"]["resource_uris"])
        )
        self.assertIn("neuronsphere://environments", payload["mcp"]["resource_uris"])
        self.assertEqual(payload["mcp"]["prompts"], len(payload["mcp"]["prompt_names"]))
        self.assertIn("deployment_overview", payload["mcp"]["prompt_names"])

    def test_unauthenticated_request_is_rejected_with_a_challenge(self):
        async def scenario():
            async with self.application.router.lifespan_context(self.application):
                async with self._client() as client:
                    return await client.post(
                        "/mcp/",
                        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                        headers=MCP_HEADERS,
                    )

        response = self._run(scenario())
        self.assertEqual(response.status_code, 401)
        self.assertIn("Bearer", response.headers.get("www-authenticate", ""))

    def test_invalid_token_is_rejected(self):
        async def scenario():
            async with self.application.router.lifespan_context(self.application):
                async with self._client() as client:
                    return await client.post(
                        "/mcp/",
                        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                        headers=dict(
                            MCP_HEADERS, Authorization="Bearer nsmcp_not_a_real_key"
                        ),
                    )

        self.assertEqual(self._run(scenario()).status_code, 401)


class TestToolSurface(MCPServerTestCase):
    def setUp(self):
        self.alice = User.objects.create_user("mcp_alice")
        UserEnvironmentPermission.objects.create(
            user=self.alice, environment="dev", role="viewer"
        )
        UserEnvironmentPermission.objects.create(
            user=self.alice, environment="prod", role="admin"
        )
        _, self.alice_key = MCPApiKey.generate(self.alice, "tests")

        self.bob = User.objects.create_user("mcp_bob")
        _, self.bob_key = MCPApiKey.generate(self.bob, "tests")

    def test_tools_are_advertised_with_descriptions(self):
        async def scenario():
            async with self.application.router.lifespan_context(self.application):
                async with self._client() as client:
                    headers = await self._session(client, self.alice_key)
                    response = await client.post(
                        "/mcp/",
                        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                        headers=headers,
                    )
                    return _parse_rpc(response.text)

        tools = self._run(scenario())["result"]["tools"]
        by_name = {t["name"]: t for t in tools}
        self.assertIn("list_environments", by_name)
        for name, tool in by_name.items():
            with self.subTest(tool=name):
                self.assertTrue((tool.get("description") or "").strip())

    def test_injected_context_is_absent_from_the_input_schema(self):
        async def scenario():
            async with self.application.router.lifespan_context(self.application):
                async with self._client() as client:
                    headers = await self._session(client, self.alice_key)
                    response = await client.post(
                        "/mcp/",
                        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                        headers=headers,
                    )
                    return _parse_rpc(response.text)

        tools = self._run(scenario())["result"]["tools"]
        schema = next(t for t in tools if t["name"] == "list_environments")[
            "inputSchema"
        ]
        self.assertNotIn("ctx", schema.get("properties", {}))

    def test_list_environments_returns_only_the_callers_grants(self):
        async def scenario():
            async with self.application.router.lifespan_context(self.application):
                async with self._client() as client:
                    headers = await self._session(client, self.alice_key)
                    return await self._call_tool(client, headers, "list_environments")

        result = self._run(scenario())["result"]["structuredContent"]
        self.assertEqual(result["total"], 2)
        self.assertEqual(
            {e["name"]: e["role"] for e in result["environments"]},
            {"dev": "viewer", "prod": "admin"},
        )

    def test_user_without_grants_sees_nothing(self):
        async def scenario():
            async with self.application.router.lifespan_context(self.application):
                async with self._client() as client:
                    headers = await self._session(client, self.bob_key)
                    return await self._call_tool(client, headers, "list_environments")

        result = self._run(scenario())["result"]["structuredContent"]
        self.assertEqual(result["environments"], [])
        self.assertEqual(result["total"], 0)

    def test_environment_scoped_tools_are_advertised_with_their_arguments(self):
        async def scenario():
            async with self.application.router.lifespan_context(self.application):
                async with self._client() as client:
                    headers = await self._session(client, self.alice_key)
                    response = await client.post(
                        "/mcp/",
                        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                        headers=headers,
                    )
                    return _parse_rpc(response.text)

        by_name = {t["name"]: t for t in self._run(scenario())["result"]["tools"]}
        for name in (
            "describe_environment",
            "describe_instance",
            "get_instance_dependencies",
            "get_instance_configuration",
            "search_repo_classes",
            "search_capabilities",
            "describe_repo_class",
            "find_resource_providers",
            "list_resource_definitions",
            "find_resource_candidates",
            "compare_environments",
        ):
            self.assertIn(name, by_name)
        # The environment-scoped tools must actually require it, or the
        # decorator would authorize against a None the caller never supplied.
        for name in (
            "describe_environment",
            "describe_instance",
            "get_instance_configuration",
            "find_resource_candidates",
        ):
            with self.subTest(tool=name):
                self.assertIn(
                    "environment", by_name[name]["inputSchema"].get("required", [])
                )
        required = set(by_name["compare_environments"]["inputSchema"]["required"])
        self.assertEqual(required, {"from_environment", "to_environment"})

    def test_a_tool_call_for_an_unpermitted_environment_is_refused(self):
        """The end-to-end proof that @read_tool's authorization actually runs.

        bob holds no grants, so this must fail before any request reaches
        hmd-ms-deployment -- and it must still be audited.
        """

        async def scenario():
            async with self.application.router.lifespan_context(self.application):
                async with self._client() as client:
                    headers = await self._session(client, self.bob_key)
                    return await self._call_tool(
                        client,
                        headers,
                        "describe_environment",
                        {"environment": "dev"},
                    )

        payload = self._run(scenario())
        self.assertTrue(payload["result"]["isError"], payload)
        self.assertIn("dev", payload["result"]["content"][0]["text"])

        row = AuditLog.objects.get(action=AuditLog.Action.MCP_TOOL_CALL)
        self.assertEqual(row.user, self.bob)
        self.assertFalse(row.success)
        self.assertEqual(row.details["tool"], "describe_environment")
        self.assertEqual(row.details["arguments"]["environment"], "dev")

    def test_a_tool_call_is_audited_against_the_calling_user(self):
        async def scenario():
            async with self.application.router.lifespan_context(self.application):
                async with self._client() as client:
                    headers = await self._session(client, self.alice_key)
                    await self._call_tool(client, headers, "list_environments")

        self._run(scenario())
        row = AuditLog.objects.get(action=AuditLog.Action.MCP_TOOL_CALL)
        self.assertEqual(row.user, self.alice)
        self.assertTrue(row.success)
        self.assertEqual(row.details["transport"], "mcp")
        self.assertEqual(row.details["tool"], "list_environments")
        self.assertEqual(row.details["auth_mode"], "apikey")
        self.assertIsNotNone(row.duration_ms)


class TestResourcesAndPrompts(MCPServerTestCase):
    """The other two halves of the protocol surface, over the real transport."""

    def setUp(self):
        self.alice = User.objects.create_user("mcp_res_alice")
        UserEnvironmentPermission.objects.create(
            user=self.alice, environment="dev", role="viewer"
        )
        _, self.alice_key = MCPApiKey.generate(self.alice, "tests")

    def test_resources_are_advertised_with_descriptions(self):
        async def scenario():
            async with self.application.router.lifespan_context(self.application):
                async with self._client() as client:
                    headers = await self._session(client, self.alice_key)
                    return (
                        await self._rpc(client, headers, "resources/list"),
                        await self._rpc(client, headers, "resources/templates/list"),
                    )

        listed, templated = self._run(scenario())
        uris = {r["uri"] for r in listed["result"]["resources"]}
        self.assertIn("neuronsphere://environments", uris)
        for resource in listed["result"]["resources"]:
            with self.subTest(uri=resource["uri"]):
                self.assertTrue((resource.get("description") or "").strip())
        # The environment-scoped reads are templates, not static resources.
        templates = {t["uriTemplate"] for t in templated["result"]["resourceTemplates"]}
        self.assertIn("neuronsphere://environment/{environment}/bom", templates)
        self.assertIn(
            "neuronsphere://repo-classes/{repo_class_name}/discovery", templates
        )

    def test_reading_a_resource_runs_the_same_authorized_read(self):
        async def scenario():
            async with self.application.router.lifespan_context(self.application):
                async with self._client() as client:
                    headers = await self._session(client, self.alice_key)
                    return await self._rpc(
                        client,
                        headers,
                        "resources/read",
                        {"uri": "neuronsphere://environments"},
                    )

        payload = self._run(scenario())
        contents = payload["result"]["contents"][0]
        self.assertEqual(contents["mimeType"], "application/json")
        self.assertIn("environments", json.loads(contents["text"]))

        # ...and it is audited exactly like a tool call.
        row = AuditLog.objects.get(action=AuditLog.Action.MCP_TOOL_CALL)
        self.assertEqual(row.user, self.alice)
        self.assertEqual(row.details["tool"], "environments_resource")

    def test_prompts_are_advertised_and_render_their_call_order(self):
        async def scenario():
            async with self.application.router.lifespan_context(self.application):
                async with self._client() as client:
                    headers = await self._session(client, self.alice_key)
                    return (
                        await self._rpc(client, headers, "prompts/list"),
                        await self._rpc(
                            client,
                            headers,
                            "prompts/get",
                            {
                                "name": "deployment_overview",
                                "arguments": {"environment": "dev"},
                            },
                        ),
                    )

        listed, rendered = self._run(scenario())
        names = {p["name"] for p in listed["result"]["prompts"]}
        self.assertEqual(
            names,
            {
                "deployment_overview",
                "dependency_impact",
                "find_provider_for_role",
                "environment_drift",
                "find_capability",
            },
        )
        text = rendered["result"]["messages"][0]["content"]["text"]
        self.assertIn("describe_environment", text)
        self.assertIn("dev", text)


class TestMultiEnvironmentAuthorization(MCPServerTestCase):
    """compare_environments authorizes *both* environments, not just the first."""

    def setUp(self):
        self.carol = User.objects.create_user("mcp_carol")
        UserEnvironmentPermission.objects.create(
            user=self.carol, environment="dev", role="viewer"
        )
        _, self.carol_key = MCPApiKey.generate(self.carol, "tests")

    def _compare(self, from_env, to_env):
        async def scenario():
            async with self.application.router.lifespan_context(self.application):
                async with self._client() as client:
                    headers = await self._session(client, self.carol_key)
                    return await self._call_tool(
                        client,
                        headers,
                        "compare_environments",
                        {"from_environment": from_env, "to_environment": to_env},
                    )

        return self._run(scenario())

    def test_a_permitted_source_does_not_admit_an_unpermitted_target(self):
        payload = self._compare("dev", "prod")
        self.assertTrue(payload["result"]["isError"], payload)
        self.assertIn("prod", payload["result"]["content"][0]["text"])

    def test_an_unpermitted_source_is_refused_first(self):
        payload = self._compare("prod", "dev")
        self.assertTrue(payload["result"]["isError"], payload)
        self.assertIn("prod", payload["result"]["content"][0]["text"])

    def test_the_refusal_is_audited_against_the_source_environment(self):
        self._compare("dev", "prod")
        row = AuditLog.objects.get(action=AuditLog.Action.MCP_TOOL_CALL)
        self.assertFalse(row.success)
        self.assertEqual(row.details["tool"], "compare_environments")
        self.assertEqual(row.details["arguments"]["to_environment"], "prod")
        self.assertIn("dev", row.target)


if __name__ == "__main__":
    unittest.main()


class TestOktaTransport(MCPServerTestCase):
    """The Okta bearer path over the real ASGI composition.

    Builds its own application because ``deployment_gui.asgi`` is imported once, with
    whatever settings were in effect then. Both credentials are enabled here, which is
    also the composition (``MultiAuth``) a deployment running both would use.
    """

    @classmethod
    def setUpClass(cls):
        from tests.test_mcp_okta_auth import BASE_URL, ISSUER, okta_settings

        cls.issuer = ISSUER
        cls.base_url = BASE_URL
        cls.settings_override = okta_settings(MCP_API_KEYS_ENABLED=True)
        cls.settings_override.enable()

        import ns_mcp.server as server_module

        # build_mcp() writes module state that the health endpoint and the ASGI entry
        # point both read; put back what the rest of the suite expects.
        cls._saved = (server_module._auth_provider, dict(server_module._server_stats))
        cls._server_module = server_module

        from django.core.asgi import get_asgi_application
        from starlette.applications import Starlette
        from starlette.routing import Mount

        from django.conf import settings
        from ns_mcp.server import build_mcp_app, get_well_known_routes

        mcp_application = build_mcp_app()
        cls.application = Starlette(
            routes=[
                Mount(settings.MCP_MOUNT_PATH, app=mcp_application),
                *get_well_known_routes(),
                Mount("/", app=get_asgi_application()),
            ],
            lifespan=mcp_application.lifespan,
        )

    @classmethod
    def tearDownClass(cls):
        provider, stats = cls._saved
        cls._server_module._auth_provider = provider
        cls._server_module._server_stats.clear()
        cls._server_module._server_stats.update(stats)
        cls.settings_override.disable()

    def setUp(self):
        from tests.test_mcp_okta_auth import link_okta_account

        self.alice = User.objects.create_user(
            "mcp_okta_alice", email="alice@example.com"
        )
        link_okta_account(self.alice, "00uALICE")
        UserEnvironmentPermission.objects.create(
            user=self.alice, environment="dev", role="viewer"
        )
        _, self.alice_key = MCPApiKey.generate(self.alice, "tests")

    def okta_token(self, uid="00uALICE", subject="alice@example.com"):
        from tests.test_mcp_okta_auth import mint

        return mint(subject=subject, uid=uid)

    def test_an_okta_bearer_is_accepted_and_scoped_to_the_mapped_user(self):
        async def scenario():
            async with self.application.router.lifespan_context(self.application):
                async with self._client() as client:
                    headers = await self._session(client, self.okta_token())
                    return await self._call_tool(client, headers, "list_environments")

        payload = self._run(scenario())
        self.assertNotIn("error", payload, payload)
        # alice holds exactly one grant; the token resolved to her, not to nobody.
        self.assertEqual(
            payload["result"]["structuredContent"]["environments"],
            [{"name": "dev", "role": "viewer"}],
        )

    def test_an_unpermitted_environment_is_still_refused(self):
        async def scenario():
            async with self.application.router.lifespan_context(self.application):
                async with self._client() as client:
                    headers = await self._session(client, self.okta_token())
                    return await self._call_tool(
                        client, headers, "describe_environment", {"environment": "prod"}
                    )

        payload = self._run(scenario())
        self.assertTrue(payload.get("result", {}).get("isError"), payload)

    def test_the_call_is_audited_as_an_okta_call(self):
        async def scenario():
            async with self.application.router.lifespan_context(self.application):
                async with self._client() as client:
                    headers = await self._session(client, self.okta_token())
                    await self._call_tool(client, headers, "list_environments")

        self._run(scenario())
        row = AuditLog.objects.get(action=AuditLog.Action.MCP_TOOL_CALL)
        self.assertEqual(row.user, self.alice)
        self.assertEqual(row.details["auth_mode"], "okta")

    def test_a_token_for_an_unprovisioned_user_is_told_to_sign_in(self):
        async def scenario():
            async with self.application.router.lifespan_context(self.application):
                async with self._client() as client:
                    headers = await self._session(
                        client,
                        self.okta_token(uid="00uNOBODY", subject="nobody@example.com"),
                    )
                    return await self._call_tool(client, headers, "list_environments")

        payload = self._run(scenario())
        self.assertIn("Sign in to the Deployment GUI", json.dumps(payload))

    def test_an_api_key_still_works_alongside_okta(self):
        async def scenario():
            async with self.application.router.lifespan_context(self.application):
                async with self._client() as client:
                    headers = await self._session(client, self.alice_key)
                    return await self._call_tool(client, headers, "list_environments")

        payload = self._run(scenario())
        self.assertNotIn("error", payload, payload)

    def test_the_protected_resource_document_is_served_at_the_host_root(self):
        # Not under /mcp: RFC 9728 puts it beside the resource, and a client that
        # cannot fetch it has no way to discover where to get a token.
        async def scenario():
            async with self.application.router.lifespan_context(self.application):
                async with self._client() as client:
                    return await client.get("/.well-known/oauth-protected-resource/mcp")

        response = self._run(scenario())
        self.assertEqual(response.status_code, 200, response.text[:300])
        document = response.json()
        self.assertEqual(document["resource"], f"{self.base_url}/mcp")
        self.assertIn(self.issuer, document["authorization_servers"])

    def test_the_challenge_points_at_the_document_that_exists(self):
        async def scenario():
            async with self.application.router.lifespan_context(self.application):
                async with self._client() as client:
                    return await client.post(
                        "/mcp/",
                        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                        headers=MCP_HEADERS,
                    )

        response = self._run(scenario())
        self.assertEqual(response.status_code, 401)
        challenge = response.headers.get("www-authenticate", "")
        self.assertIn(
            f'resource_metadata="{self.base_url}/.well-known/oauth-protected-resource/mcp"',
            challenge,
        )
