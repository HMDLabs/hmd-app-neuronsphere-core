"""The gateway's smoke-test upstream (``ns_mcp.gateway.echo``).

It reports back the routing headers each forwarded call arrived with, which is
what lets the acceptance suite prove end to end that a call naming an
environment reached the deployment it named.
"""
import asyncio
import json
import unittest

import httpx
from httpx import ASGITransport

from ns_mcp.gateway.echo import build_echo_server
from tests.test_mcp_server import MCP_HEADERS, _parse_rpc


class TestEchoUpstream(unittest.TestCase):
    def test_echo_reports_the_forwarded_environment_and_user(self):
        app = build_echo_server().http_app(path="/mcp", stateless_http=True)

        async def scenario():
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://localhost"
                ) as client:
                    response = await client.post(
                        "/mcp",
                        json={
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "tools/call",
                            "params": {"name": "echo", "arguments": {"text": "hi"}},
                        },
                        headers=dict(
                            MCP_HEADERS,
                            **{"X-NS-Environment": "test", "X-NS-User": "alice"},
                        ),
                    )
                    return _parse_rpc(response.text)

        result = asyncio.run(scenario())["result"]
        payload = result.get("structuredContent") or json.loads(
            result["content"][0]["text"]
        )
        self.assertEqual(
            payload, {"text": "hi", "environment": "test", "user": "alice"}
        )
