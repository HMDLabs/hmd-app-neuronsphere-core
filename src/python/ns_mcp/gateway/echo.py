"""A minimal upstream MCP server for smoke-testing the gateway (NERD012).

``python -m ns_mcp.gateway.echo`` serves one tool, ``echo``, at
``http://0.0.0.0:$PORT/mcp`` (port 8100 by default). It reports back the routing
headers the gateway forwarded the call with, so a caller can see which
environment's deployment answered. The local chart runs it as a sidecar when
``config.mcpGatewayEchoFixture`` is set; nothing in production uses it.

Deliberately free of Django: it runs in its own container from the same image.
"""
import os

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_request


def build_echo_server() -> FastMCP:
    server = FastMCP(
        "ns-gateway-echo",
        instructions="Smoke-test upstream for the NeuronSphere MCP gateway.",
    )

    @server.tool
    def echo(text: str) -> dict:
        """Echo `text`, with the environment and user the gateway routed it as."""
        headers = get_http_request().headers
        return {
            "text": text,
            "environment": headers.get("x-ns-environment"),
            "user": headers.get("x-ns-user"),
        }

    return server


if __name__ == "__main__":  # pragma: no cover - container entry point
    build_echo_server().run(
        transport="http",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8100")),
        path="/mcp",
        stateless_http=True,
    )
