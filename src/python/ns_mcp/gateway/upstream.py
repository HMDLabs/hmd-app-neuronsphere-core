"""Talking to an upstream MCP server on a caller's behalf (NERD012).

Each request opens its own client: the gateway is stateless (like ``/mcp`` itself,
which runs under several gunicorn workers with no affinity), so a pooled session
would be one worker's state that the next request never sees. More to the point,
the identity forwarded differs per caller, and a long-lived proxy session is
exactly what left NERD008 SPEC014's federation unable to carry it.

How the gateway authenticates is declared per server (the Resource's
``auth_mode``):

* ``service`` (default) -- the gateway's own identity, plus the caller's in
  ``X-NS-*`` headers. The gateway is the enforcement point, so the upstream must
  accept only the gateway (SPEC007). The credential is, in order:

  - a static bearer from ``MCP_GATEWAY_CREDENTIALS_DIR/<credential_ref>`` (a mounted
    Kubernetes secret), for an upstream outside the platform's IdP; otherwise
  - an access token the IdP issued to the gateway's client, scoped to the
    endpoint's environment (``ns_mcp.gateway.idp``).

  With neither, the call is refused: a service-mode upstream is never called
  anonymously.
* ``passthrough`` -- the caller's own SSO bearer, so the upstream applies its own
  authorization to the user. Platform API keys mean nothing outside this app, so
  API-key callers cannot use a passthrough server.
* ``none`` -- identity headers only. Static configuration only (local fixtures);
  a discovered Resource cannot select it.
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


def _service_token_source(token_source):
    if token_source is None:
        from .idp import default_token_source

        token_source = default_token_source()
    return token_source


def credential_problem(endpoint: Endpoint, principal, token_source=None):
    """Why the gateway cannot authenticate to ``endpoint`` for ``principal``, or None.

    The configuration checks ``upstream_headers`` refuses on, made without calling
    anything, so ``list_mcp_servers`` can say why a server offers no tools.
    """
    if endpoint.auth_mode == "none":
        return None
    if endpoint.auth_mode == "passthrough":
        if principal.is_api_key:
            return (
                f"'{endpoint.server_name}' authorizes callers itself and needs your "
                "SSO token; platform API keys cannot be forwarded to it."
            )
        return None
    if endpoint.credential_ref:
        try:
            _credential(endpoint.credential_ref)
        except GatewayCallError as exc:
            return str(exc)
        return None
    if not _service_token_source(token_source).configured:
        return (
            f"The gateway has no credential for '{endpoint.server_name}': configure "
            "its identity provider client or give the server a credential_ref."
        )
    return None


async def upstream_headers(
    endpoint: Endpoint, principal, request_id: str, token_source=None
) -> dict:
    """The headers to send upstream for ``principal`` calling ``endpoint``.

    ``token_source`` supplies IdP tokens for service mode; it defaults to the
    process-wide one built from settings.
    """
    problem = credential_problem(endpoint, principal, token_source)
    if problem:
        raise GatewayCallError(problem)
    headers = {
        "X-NS-User": principal.username,
        "X-NS-Environment": endpoint.environment,
        "X-Request-Id": request_id,
        GATEWAY_HOP_HEADER: "1",
    }
    if endpoint.auth_mode == "none":
        return headers
    if endpoint.auth_mode == "passthrough":
        headers["Authorization"] = f"Bearer {principal.raw_token}"
        return headers
    if endpoint.credential_ref:
        headers["Authorization"] = f"Bearer {_credential(endpoint.credential_ref)}"
        return headers

    token = await _service_token_source(token_source).token(endpoint.environment)
    headers["Authorization"] = f"Bearer {token}"
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
