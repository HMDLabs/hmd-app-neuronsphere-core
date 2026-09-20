"""Robot Framework library speaking MCP's JSON-RPC to the GUI's /mcp endpoint.

Protocol-level, not browser-driven: the MCP surface has no pages, so this suite
is the only acceptance coverage of it. Written on ``urllib`` in the style of
``DeploymentSeed.py`` rather than pulling in a requests-based Robot library, so
``test_requirements.txt`` gains no dependency. The handshake, the SSE framing
and the session-id threading mirror ``src/python/tests/test_mcp_server.py``,
which drives the same endpoint in-process.

Authentication uses the fixed local key the chart's ``createLocalMcpKey`` hook
installs. It is read back from the same instance configuration that set it --
``TRANSFORM_INSTANCE_CONTEXT``, which bender already injects -- so the credential
is declared in exactly one place. ``MCP_API_KEY`` overrides it for a run against
a deploy that was not configured that way.
"""

import json
import os
import time
import urllib.error
import urllib.request

APP_URL = os.environ.get("APP_URL", "http://localhost:19003")
MCP_PATH = "/mcp/"
PROTOCOL_VERSION = "2025-06-18"

BASE_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


def _resolve_api_key():
    """The bearer key: MCP_API_KEY, else config.localMcpApiKey from the deploy."""
    explicit = os.environ.get("MCP_API_KEY", "").strip()
    if explicit:
        return explicit
    context = os.environ.get("TRANSFORM_INSTANCE_CONTEXT", "")
    if context:
        try:
            config = json.loads(context).get("config") or {}
        except (ValueError, AttributeError):
            config = {}
        key = (config.get("localMcpApiKey") or "").strip()
        if key:
            return key
    raise RuntimeError(
        "No MCP API key available. The local deploy sets config.localMcpApiKey "
        "(config_local.json -> createLocalMcpKey); set MCP_API_KEY to override."
    )


class MCPSeed:
    """An MCP client, as Robot keywords."""

    def __init__(self):
        self._headers = None
        self._api_key = None
        self._request_id = 0

    # -- transport ---------------------------------------------------------

    def _post(self, payload, headers, timeout=30):
        """POST one JSON-RPC message. Returns ``(status, body, headers)``."""
        request = urllib.request.Request(
            APP_URL.rstrip("/") + MCP_PATH,
            data=json.dumps(payload).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return (
                    response.status,
                    response.read().decode(),
                    dict(response.headers),
                )
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode(), dict(exc.headers)

    @staticmethod
    def _parse(body):
        """A JSON-RPC payload out of either a plain or SSE-framed response."""
        for line in body.splitlines():
            if line.startswith("data: "):
                return json.loads(line[6:])
        return json.loads(body) if body.strip() else None

    def _next_id(self):
        self._request_id += 1
        return self._request_id

    # -- keywords ----------------------------------------------------------

    def wait_for_mcp_endpoint(self, timeout=60):
        """Wait until /mcp answers at all -- 401 counts, it means it is up."""
        deadline = time.time() + int(timeout)
        last = None
        while time.time() < deadline:
            try:
                status, _, _ = self._post(
                    {"jsonrpc": "2.0", "id": 0, "method": "tools/list"},
                    dict(BASE_HEADERS),
                    timeout=5,
                )
                if status in (200, 401, 403):
                    return status
                last = f"HTTP {status}"
            except Exception as exc:  # noqa: BLE001 - readiness probe
                last = str(exc)
            time.sleep(2)
        raise RuntimeError(f"MCP endpoint not ready after {timeout}s: {last}")

    def mcp_request_without_authentication(self):
        """Call the endpoint with no bearer. Returns ``(status, headers)``."""
        status, _, headers = self._post(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, dict(BASE_HEADERS)
        )
        return status, headers

    def initialize_mcp_session(self):
        """Complete the initialize handshake. Returns the server's capabilities."""
        self._api_key = _resolve_api_key()
        headers = dict(BASE_HEADERS, Authorization=f"Bearer {self._api_key}")
        status, body, response_headers = self._post(
            {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "bender", "version": "1"},
                },
            },
            headers,
        )
        if status != 200:
            raise RuntimeError(f"initialize failed: HTTP {status}: {body[:300]}")
        session_id = response_headers.get("mcp-session-id") or response_headers.get(
            "Mcp-Session-Id"
        )
        if session_id:
            headers["Mcp-Session-Id"] = session_id
        self._post(
            {"jsonrpc": "2.0", "method": "notifications/initialized"}, headers
        )
        self._headers = headers
        return self._parse(body)["result"]

    def mcp_rpc(self, method, **params):
        """Send one JSON-RPC request on the established session."""
        if self._headers is None:
            self.initialize_mcp_session()
        status, body, _ = self._post(
            {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": method,
                "params": params,
            },
            self._headers,
        )
        if status != 200:
            raise RuntimeError(f"{method} failed: HTTP {status}: {body[:300]}")
        payload = self._parse(body)
        if "error" in payload:
            raise RuntimeError(f"{method} returned an error: {payload['error']}")
        return payload["result"]

    def list_mcp_tools(self):
        """The advertised tool names."""
        return [t["name"] for t in self.mcp_rpc("tools/list")["tools"]]

    def list_mcp_resources(self):
        """The advertised static resource URIs."""
        return [r["uri"] for r in self.mcp_rpc("resources/list")["resources"]]

    def list_mcp_resource_templates(self):
        """The advertised templated resource URIs."""
        return [
            t["uriTemplate"]
            for t in self.mcp_rpc("resources/templates/list")["resourceTemplates"]
        ]

    def list_mcp_prompts(self):
        """The advertised prompt names."""
        return [p["name"] for p in self.mcp_rpc("prompts/list")["prompts"]]

    def read_mcp_resource(self, uri):
        """Read a resource, returning its decoded JSON body."""
        contents = self.mcp_rpc("resources/read", uri=uri)["contents"]
        return json.loads(contents[0]["text"])

    def get_mcp_prompt(self, name, **arguments):
        """Render a prompt, returning the text of its first message."""
        result = self.mcp_rpc("prompts/get", name=name, arguments=arguments)
        return result["messages"][0]["content"]["text"]

    def call_mcp_tool(self, name, **arguments):
        """Call a tool and return its structured result.

        Raises when the tool reports an error, so a failing call fails the test
        rather than returning an error blob a later assertion has to notice.
        """
        result = self.mcp_rpc("tools/call", name=name, arguments=arguments)
        if result.get("isError"):
            raise RuntimeError(
                f"{name} returned an error: {result['content'][0]['text']}"
            )
        return result.get("structuredContent", result)

    def call_mcp_tool_raw(self, name, **arguments):
        """Call a tool and return the raw result, error or not.

        For the cases where either outcome is legitimate and what is being
        tested is that the server answered at all rather than 500'd.
        """
        return self.mcp_rpc("tools/call", name=name, arguments=arguments)

    def call_mcp_tool_expecting_error(self, name, **arguments):
        """Call a tool that should fail, returning the error text."""
        result = self.mcp_rpc("tools/call", name=name, arguments=arguments)
        if not result.get("isError"):
            raise RuntimeError(f"{name} unexpectedly succeeded: {result}")
        return result["content"][0]["text"]

    def get_mcp_health(self):
        """The /health/ payload's ``mcp`` block -- unauthenticated on purpose."""
        request = urllib.request.Request(APP_URL.rstrip("/") + "/health/")
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode())["mcp"]
