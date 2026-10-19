"""Wiring the gateway into the ``/mcp`` server (NERD012)."""
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

#: The installed provider, for the tools and the health endpoint. None when off.
_provider = None


def get_gateway():
    """The installed ``GatewayProvider``, or ``None`` when the gateway is off."""
    return _provider


def install_gateway(mcp, auth_provider, registry=None, client_factory=None):
    """Add the gateway provider and its catalog routes to ``mcp`` if enabled.

    Nothing upstream is contacted here: discovery and tool listing are lazy and
    per request, so an unreachable upstream (or deployment service) cannot stop
    the server starting.
    """
    global _provider

    if not settings.MCP_GATEWAY_ENABLED:
        _provider = None
        return None

    from .catalog import add_catalog_routes
    from .provider import GatewayProvider
    from .registry import default_registry
    from .upstream import default_client_factory

    provider = GatewayProvider(
        registry=registry or default_registry(),
        client_factory=client_factory or default_client_factory,
        separator=settings.MCP_GATEWAY_TOOL_SEPARATOR,
        tools_ttl=settings.MCP_GATEWAY_TOOLS_TTL,
    )
    mcp.add_provider(provider)
    add_catalog_routes(mcp, provider, auth_provider)
    _provider = provider
    logger.info(
        "MCP gateway enabled (discovery=%s)", settings.MCP_GATEWAY_DISCOVERY_ENABLED
    )
    return provider
