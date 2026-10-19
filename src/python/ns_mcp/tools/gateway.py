"""``list_mcp_servers`` -- what the gateway can route the caller to (NERD012)."""
from deployments.models import AuditLog

from ..gateway.catalog import summaries
from ..gateway.install import get_gateway
from ..tooling import read_tool


@read_tool(action=AuditLog.Action.MCP_TOOL_CALL)
def list_mcp_servers(ctx):
    """List the MCP servers this gateway routes to, and where you may use them."""
    provider = get_gateway()
    if provider is None:
        return {"enabled": False, "servers": []}
    return {"enabled": True, "servers": summaries(provider, ctx.principal, ctx.user)}


def register(mcp):
    from django.conf import settings

    if not settings.MCP_GATEWAY_ENABLED:
        return []
    mcp.tool(
        list_mcp_servers,
        name="list_mcp_servers",
        description=(
            "List the other MCP servers NeuronSphere hosts (Trino, ClickHouse, internal "
            "services, ...) that this gateway routes to. Each appears once, whatever "
            "number of environments it runs in; its tools are named "
            "<server>__<tool> and take an `environment` argument limited to the "
            "environments you may use. Scoped to your permissions."
        ),
    )
    return ["list_mcp_servers"]
