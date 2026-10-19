"""Talking to an upstream MCP server on a caller's behalf (NERD012).

Each request opens its own client: the gateway is stateless (like ``/mcp`` itself,
which runs under several gunicorn workers with no affinity), so a pooled session
would be one worker's state that the next request never sees. More to the point,
the identity forwarded differs per caller, and a long-lived proxy session is
exactly what left NERD008 SPEC014's federation unable to carry it.

How the gateway authenticates is declared per server (the Resource's
``auth_mode``):

* ``service`` (default) -- the gateway's own credential for that server, read from
  ``MCP_GATEWAY_CREDENTIALS_DIR/<credential_ref>`` (a mounted Kubernetes secret),
  plus the caller's identity in ``X-NS-*`` headers. The gateway is the
  enforcement point; the upstream trusts it.
* ``passthrough`` -- the caller's own Okta bearer, so the upstream applies its own
  authorization to the user. Platform API keys mean nothing outside this app, so
  API-key callers cannot use a passthrough server.
"""
import os
from typing import Callable, Optional

from .registry import Endpoint


#: Set on every request the gateway forwards. A gateway receiving it serves only
#: its native tools, so two gateways pointed at each other (or one at its own
#: /mcp) cannot list each other's tools without end.
GATEWAY_HOP_HEADER = "X-NS-Gateway-Hop"


class GatewayCallError(Exception):
    """A gateway call that cannot be made, with a message fit for the caller."""


def _credential(ref: str) -> str:
    from django.conf import settings

    directory = settings.MCP_GATEWAY_CREDENTIALS_DIR
    path = os.path.join(directory, ref) if directory else ""
    try:
        with open(path) as fh:
            value = fh.read().strip()
    except OSError:
        value = ""
    if not value:
        # Refuse rather than call anonymously: an upstream that happens to accept
        # unauthenticated requests would otherwise be reached with no credential.
        raise GatewayCallError(
            f"The gateway has no credential '{ref}' for this server; ask a platform "
            "administrator to provision it."
        )
    return value


def upstream_headers(endpoint: Endpoint, principal, request_id: str) -> dict:
    """The headers to send upstream for ``principal`` calling ``endpoint``."""
    headers = {
        "X-NS-User": principal.username,
        "X-NS-Environment": endpoint.environment,
        "X-Request-Id": request_id,
        GATEWAY_HOP_HEADER: "1",
    }
    if endpoint.auth_mode == "passthrough":
        if principal.is_api_key:
            raise GatewayCallError(
                f"'{endpoint.server_name}' authorizes callers itself and needs your "
                "SSO token; platform API keys cannot be forwarded to it."
            )
        headers["Authorization"] = f"Bearer {principal.raw_token}"
    elif endpoint.credential_ref:
        headers["Authorization"] = f"Bearer {_credential(endpoint.credential_ref)}"
    return headers


def default_client_factory(endpoint: Endpoint, headers: dict):
    """A Streamable HTTP client for ``endpoint``."""
    from django.conf import settings
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    return Client(
        StreamableHttpTransport(endpoint.url, headers=headers),
        timeout=settings.MCP_GATEWAY_CALL_TIMEOUT,
    )


ClientFactory = Callable[[Endpoint, dict], object]


async def list_upstream_tools(
    factory: ClientFactory, endpoint: Endpoint, headers: dict
):
    """The upstream's ``tools/list``, as ``mcp.types.Tool`` objects."""
    async with factory(endpoint, headers) as client:
        return await client.list_tools()


async def call_upstream(
    factory: ClientFactory,
    endpoint: Endpoint,
    name: str,
    arguments: dict,
    headers: dict,
    meta: Optional[dict] = None,
):
    """The upstream's raw ``CallToolResult`` -- errors included, not raised."""
    async with factory(endpoint, headers) as client:
        return await client.call_tool_mcp(name=name, arguments=arguments, meta=meta)
