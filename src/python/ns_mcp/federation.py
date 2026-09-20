"""Federating MCP tools from deployed NeuronSphere services.

Inert in Phase 1 -- no service exposes an MCP endpoint yet (HMD_MS_BASE_NERD001
is drafted, not implemented). The seam exists now so nothing has to be
retrofitted later.

Discovery reuses the platform's own resource model rather than inventing a
registry: a service that opts into MCP publishes a Resource of definition
``mcp.neuronsphere.io/mcp-server`` whose output carries ``url`` and
``namespace``. This app finds them with client methods that already exist
(``find_resources_by_selector`` / ``list_resources``) and mounts one
``create_proxy`` per endpoint, so remote tools appear in a single ``tools/list``
namespaced by service.

Unresolved before this ships (see the plan's federation caveat): a proxy mounted
once at startup carries a single downstream identity, but each call should
forward the *caller's* bearer. Until that is settled, federation stays disabled
by default.
"""
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

#: Resource definition namespace a service publishes its MCP endpoint under.
MCP_RESOURCE_NAMESPACE = "mcp.neuronsphere.io"
MCP_RESOURCE_DEFINITION = "mcp-server"


def discover_endpoints() -> list:
    """Return the MCP endpoints to federate.

    Phase 1 supports only the static escape hatch (``MCP_FEDERATED_ENDPOINTS``,
    formatted ``namespace=url,namespace=url``) so the mounting path is testable
    before any service publishes the resource definition.
    """
    endpoints = []
    raw = getattr(settings, "MCP_FEDERATED_ENDPOINTS", "") or ""
    for entry in raw.split(","):
        entry = entry.strip()
        if "=" not in entry:
            continue
        namespace, url = entry.split("=", 1)
        namespace, url = namespace.strip(), url.strip()
        if namespace and url:
            endpoints.append({"namespace": namespace, "url": url})
    return endpoints


def mount_federated(mcp) -> int:
    """Mount a proxy per discovered endpoint. Returns how many were mounted."""
    if not getattr(settings, "MCP_FEDERATION_ENABLED", False):
        return 0

    from fastmcp.server import create_proxy

    mounted = 0
    for endpoint in discover_endpoints():
        try:
            mcp.mount(create_proxy(endpoint["url"]), namespace=endpoint["namespace"])
            mounted += 1
            logger.info(
                "Federated MCP server '%s' from %s",
                endpoint["namespace"],
                endpoint["url"],
            )
        except Exception:
            # One unreachable downstream must not prevent the server starting.
            logger.exception(
                "Failed to federate MCP server '%s' from %s; continuing",
                endpoint["namespace"],
                endpoint["url"],
            )
    return mounted
