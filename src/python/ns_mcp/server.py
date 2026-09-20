"""Construction of the FastMCP server mounted at ``/mcp``."""
import logging

from django.conf import settings
from fastmcp import FastMCP

from .auth import build_auth_provider
from .federation import mount_federated
from .registry import (
    register_prompt_modules,
    register_resource_modules,
    register_tool_modules,
)

logger = logging.getLogger(__name__)

INSTRUCTIONS = """\
Read-only access to a NeuronSphere platform's deployment state, backed by the
hmd-ms-deployment service.

Core concepts: an *environment* (dev, prod, ...) contains *repo instances*, each
a deployed instance of a *repo class* at a given version. An instance's
dependencies are wired by *role*; a role is satisfied either by naming a repo
class directly (legacy) or by declaring a *resource* requirement -- a namespaced,
versioned type such as kubernetes.neuronsphere.io/kubernetes-cluster -- which any
repo class that produces that resource can satisfy. The full set of instances in
an environment is its *BOM*.

Start with list_environments to see what you can access. Results are scoped to
your permissions; environments you cannot view are not listed and cannot be
queried.

What is deployed: describe_environment at detail='summary' is the cheap
overview -- counts by status and repo class, plus the values you can filter on.
Only ask for detail='full' once you know what you are looking for, and page it:
a real BOM runs to hundreds of instances. describe_instance gives one instance's
effective configuration and the wiring kind of each dependency role;
get_instance_configuration is the narrower, cheaper read of just that
configuration, and can project a dotted path or list keys instead of returning
the whole document. get_instance_dependencies is the cheapest edge-only query
and is the one to use when walking several instances, in either direction.
compare_environments reports how two environments have diverged; it needs view
access to both.

The catalog, which is platform-wide and not scoped to an environment:
search_repo_classes and describe_repo_class cover what can be deployed and what
each version declares. search_capabilities answers "which repo class can do X"
from the summary and capabilities (endpoints, CLI commands, functions, classes,
operations) each class declares in its manifest -- start there when you know
what you need done but not what it is called, then describe_repo_class the hit.
list_resource_definitions is the vocabulary of dependency roles,
find_resource_providers answers "which repo classes could satisfy this role",
and find_resource_candidates answers the same question about what is already
deployed in one environment.

The same reads are also addressable as resources under neuronsphere://, and the
prompts describe the call orders these tools are meant to be used in.
"""

#: The auth provider built alongside the server. Held so the ASGI entry point can
#: pull its /.well-known routes out and serve them above the /mcp mount.
_auth_provider = None

#: Set at build time so the health endpoint can report what actually loaded.
_server_stats = {
    "tools": 0,
    "tool_names": [],
    "resources": 0,
    "resource_uris": [],
    "prompts": 0,
    "prompt_names": [],
    "modules": 0,
    "federated": 0,
    "well_known_routes": [],
    "built": False,
}


def get_server_stats() -> dict:
    """A snapshot of what the MCP server registered, for the health endpoint."""
    return dict(_server_stats)


def get_well_known_routes() -> list:
    """The provider's ``/.well-known`` routes, for mounting at the application root.

    RFC 9728 puts the protected-resource document at
    ``https://host/.well-known/oauth-protected-resource/mcp`` -- above the /mcp mount,
    not inside it -- so these have to be served by the outer router. Empty whenever
    there is no provider, or the provider advertises nothing (a bare verifier does not).
    """
    if _auth_provider is None:
        return []
    return _auth_provider.get_well_known_routes(mcp_path=settings.MCP_MOUNT_PATH)


def _warn_on_downstream_mode() -> None:
    """Flag a downstream token mode that cannot actually authenticate."""
    import os

    if getattr(settings, "MCP_DOWNSTREAM_TOKEN_MODE", "passthrough") != "service":
        return
    if not (
        os.environ.get("SERVICE_CLIENT_ID") and os.environ.get("SERVICE_CLIENT_SECRET")
    ):
        logger.warning(
            "MCP_DOWNSTREAM_TOKEN_MODE=service but SERVICE_CLIENT_ID/"
            "SERVICE_CLIENT_SECRET are unset, so the service account cannot mint a "
            "token and every downstream request will go out unauthenticated."
        )


def build_mcp() -> FastMCP:
    """Build the FastMCP server: auth, local capabilities, then federation."""
    global _auth_provider

    _auth_provider = build_auth_provider()
    _warn_on_downstream_mode()

    mcp = FastMCP(
        name=settings.MCP_SERVER_NAME,
        instructions=INSTRUCTIONS,
        auth=_auth_provider,
    )

    registered = register_tool_modules(mcp, settings.MCP_TOOL_MODULES)
    resources = register_resource_modules(mcp, settings.MCP_RESOURCE_MODULES)
    prompts = register_prompt_modules(mcp, settings.MCP_PROMPT_MODULES)
    federated = mount_federated(mcp)

    def _flatten(registry):
        return sorted(n for names in registry.values() for n in names)

    tool_names = _flatten(registered)
    resource_uris = _flatten(resources)
    prompt_names = _flatten(prompts)
    _server_stats.update(
        {
            "tools": len(tool_names),
            "tool_names": tool_names,
            "resources": len(resource_uris),
            "resource_uris": resource_uris,
            "prompts": len(prompt_names),
            "prompt_names": prompt_names,
            "modules": len(registered) + len(resources) + len(prompts),
            "federated": federated,
            "well_known_routes": [r.path for r in get_well_known_routes()],
            "built": True,
        }
    )
    return mcp


def build_mcp_app():
    """The ASGI app to mount at ``settings.MCP_MOUNT_PATH``.

    ``stateless_http`` is required, not optional: gunicorn forks several workers
    with no request affinity, so a session held in one worker's memory is
    invisible to the next request. Host/Origin protection is FastMCP's own --
    Django's ``SecurityMiddleware`` and ``ALLOWED_HOSTS`` do not apply to a
    sibling ASGI mount.
    """
    mcp = build_mcp()
    return mcp.http_app(
        path="/",
        stateless_http=settings.MCP_STATELESS_HTTP,
        allowed_hosts=settings.MCP_ALLOWED_HOSTS or None,
        allowed_origins=settings.MCP_ALLOWED_ORIGINS or None,
    )
