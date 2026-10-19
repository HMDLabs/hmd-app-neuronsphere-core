"""The gateway's registry listing, in the official MCP Registry shape (NERD012).

``GET <MCP_MOUNT_PATH>/registry/v0/servers`` and ``.../v0/servers/{name}`` follow
the modelcontextprotocol/registry v0 API: a ``servers`` list of ``{server, _meta}``
entries whose ``server`` is a ``server.json`` document. That makes this a private
"subregistry" any registry-aware client can browse, rather than a format of our own.

Every entry's single remote is this gateway -- the upstream URLs are never
disclosed, since reaching an upstream directly would bypass the environment check.
What NeuronSphere adds (the tool prefix and the environments the caller may use)
goes under ``_meta["io.neuronsphere/gateway"]``, the registry's extension point.

These are plain routes beside the MCP endpoint, so FastMCP's auth middleware does
not cover them; each request verifies its bearer with the same auth provider.
"""
import logging

from django.conf import settings
from starlette.requests import Request
from starlette.responses import JSONResponse

from ..context import run_in_django
from ..principal import principal_from_access_token
from ..tooling import load_user

logger = logging.getLogger(__name__)

REGISTRY_NAMESPACE = "io.neuronsphere"
SERVER_SCHEMA = (
    "https://static.modelcontextprotocol.io/schemas/2025-09-29/server.schema.json"
)


def gateway_url(request=None) -> str:
    """The URL a client should connect to: this server's MCP endpoint."""
    base = settings.MCP_BASE_URL
    if not base and request is not None:
        base = f"{request.url.scheme}://{request.url.netloc}"
    return f"{base}{settings.MCP_MOUNT_PATH.rstrip('/')}/"


def _latest_version(endpoints) -> str:
    from .provider import _version_key

    versions = [e.version for e in endpoints if e.version]
    return max(versions, key=_version_key) if versions else "0.0.0"


def summaries(provider, principal, user) -> list:
    """What the caller can reach, one dict per logical server. Worker thread."""
    return [
        {
            "server_name": server.name,
            "title": server.title or server.name,
            "description": server.description,
            "tool_prefix": f"{server.name}{provider.separator}",
            "environments": [e.environment for e in endpoints],
            "deployments": [
                {
                    "name": e.environment,
                    "version": e.version,
                    "required_role": e.required_role,
                    "auth_mode": e.auth_mode,
                }
                for e in endpoints
            ],
            "version": _latest_version(endpoints),
        }
        for server, endpoints in provider.reachable(principal, user)
    ]


def registry_entry(summary: dict, url: str) -> dict:
    """One MCP Registry ``{server, _meta}`` entry for a summary."""
    return {
        "server": {
            "$schema": SERVER_SCHEMA,
            "name": f"{REGISTRY_NAMESPACE}/{summary['server_name']}",
            "title": summary["title"],
            "description": summary["description"]
            or f"NeuronSphere-hosted MCP server '{summary['server_name']}'.",
            "version": summary["version"],
            "remotes": [{"type": "streamable-http", "url": url}],
        },
        "_meta": {
            f"{REGISTRY_NAMESPACE}/gateway": {
                "tool_prefix": summary["tool_prefix"],
                "environments": summary["deployments"],
            }
        },
    }


def _unauthorized() -> JSONResponse:
    return JSONResponse(
        {
            "error": "unauthorized",
            "detail": "Send an Authorization: Bearer <token> header.",
        },
        status_code=401,
        headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
    )


def add_catalog_routes(mcp, provider, auth_provider) -> None:
    """Serve the registry listing beside the MCP endpoint."""

    async def entries_for(request: Request):
        header = request.headers.get("authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token or auth_provider is None:
            return None
        access_token = await auth_provider.verify_token(token.strip())
        if access_token is None:
            return None
        try:
            principal = principal_from_access_token(access_token)
        except Exception:
            return None

        def collect():
            return summaries(provider, principal, load_user(principal))

        url = gateway_url(request)
        return [registry_entry(s, url) for s in await run_in_django(collect)]

    @mcp.custom_route("/registry/v0/servers", methods=["GET"])
    async def list_servers(request: Request):
        entries = await entries_for(request)
        if entries is None:
            return _unauthorized()
        return JSONResponse({"servers": entries, "metadata": {"count": len(entries)}})

    @mcp.custom_route("/registry/v0/servers/{name:path}", methods=["GET"])
    async def get_server(request: Request):
        entries = await entries_for(request)
        if entries is None:
            return _unauthorized()
        name = request.path_params["name"]
        for entry in entries:
            if entry["server"]["name"] == name:
                return JSONResponse(entry)
        return JSONResponse({"error": "not_found", "name": name}, status_code=404)
