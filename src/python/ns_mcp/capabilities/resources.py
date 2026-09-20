"""MCP resources -- the same reads, addressable by URI instead of by call.

Every body here delegates to a tool body that already exists, wrapped in the
same ``@read_tool`` decorator, so a resource read is authorized and audited
exactly like the equivalent tool call. Templated URIs carry their parameters in
the path; FastMCP derives them from the (context-stripped) signature, which is
why the parameter names must match the URI placeholders.

Resources are the browsable half of the surface: a client that lists resources
sees the shape of the platform without having to guess at tool arguments.
"""
import json

from fastmcp.exceptions import ToolError

from deployments.models import AuditLog

from ..tooling import read_tool
from ..tools.bom import describe_environment
from ..tools.environments import list_environments
from ..tools.instances import get_instance_configuration
from ..tools.resources import list_resource_definitions

#: URI scheme for everything this server publishes.
SCHEME = "neuronsphere"


def _json(value) -> str:
    """Resource contents are text; JSON keeps them parseable by the caller."""
    return json.dumps(value, indent=2, default=str)


def _body(tool):
    """The undecorated body of an existing tool, to re-wrap as a resource."""
    return getattr(tool, "__wrapped__")


@read_tool(action=AuditLog.Action.MCP_TOOL_CALL)
def environments_resource(ctx) -> str:
    """The environments the caller can read."""
    return _json(_body(list_environments)(ctx))


@read_tool(action=AuditLog.Action.MCP_TOOL_CALL, environment_arg="environment")
def environment_bom_resource(ctx, environment: str) -> str:
    """One environment's BOM summary -- counts and the available filters."""
    return _json(_body(describe_environment)(ctx, environment=environment))


@read_tool(action=AuditLog.Action.MCP_TOOL_CALL, environment_arg="environment")
def instance_config_resource(ctx, environment: str, instance_name: str) -> str:
    """One instance's effective deployed configuration."""
    return _json(
        _body(get_instance_configuration)(
            ctx, environment=environment, instance_name=instance_name
        )
    )


@read_tool(action=AuditLog.Action.MCP_TOOL_CALL)
def resource_definitions_resource(ctx) -> str:
    """The platform-wide resource definition catalog."""
    return _json(_body(list_resource_definitions)(ctx))


@read_tool(action=AuditLog.Action.MCP_TOOL_CALL)
def repo_class_discovery_resource(ctx, repo_class_name: str) -> str:
    """One repo class's latest-version BACON discovery block, in full.

    One ``search_discovery`` call filtered by class-name prefix, then an
    exact-name pick: the backend filter is a prefix, so ``hmd-ms-deploy``
    would otherwise also answer for ``hmd-ms-deployment``. An empty query
    makes the backend return the complete capability and entry-point lists.
    """
    response = ctx.client.search_discovery(repo_class_name=repo_class_name, limit=500)
    if not response.success:
        raise ToolError(
            f"Could not read discovery for '{repo_class_name}': {response.error}"
        )
    data = response.data if isinstance(response.data, dict) else {}
    match = next(
        (
            it
            for it in (data.get("items") or [])
            if isinstance(it, dict) and it.get("repo_class_name") == repo_class_name
        ),
        None,
    )
    if match is None:
        raise ToolError(
            f"No repo class named '{repo_class_name}'. Use search_repo_classes "
            f"to find the name."
        )
    return _json(
        {
            "repo_class_name": repo_class_name,
            "version": match.get("version"),
            "discovery": {
                "summary": match.get("summary") or "",
                "entry_points": match.get("entry_points") or [],
                "capabilities": match.get("capabilities") or [],
                "related_docs": match.get("related_docs") or [],
            },
        }
    )


def register(mcp):
    """Register this module's resources. Returns the URIs registered."""
    uris = []

    def add(uri, fn, name, description):
        mcp.resource(
            uri,
            name=name,
            description=description,
            mime_type="application/json",
        )(fn)
        uris.append(uri)

    add(
        f"{SCHEME}://environments",
        environments_resource,
        "environments",
        "The NeuronSphere environments you have access to, with your role on "
        "each. The entry point: every environment-scoped URI below takes one "
        "of these names.",
    )
    add(
        f"{SCHEME}://environment/{{environment}}/bom",
        environment_bom_resource,
        "environment-bom",
        "A summary of what is deployed in one environment: counts by status "
        "and repo class, plus the values available to filter on. Use the "
        "describe_environment tool for the full, paginated instance list.",
    )
    add(
        f"{SCHEME}://environment/{{environment}}/instance/{{instance_name}}/config",
        instance_config_resource,
        "instance-configuration",
        "The full effective deployed configuration of one repo instance -- the "
        "merged values 'hmd deploy' would use. Use the "
        "get_instance_configuration tool to project a path out of it or list "
        "its keys instead of pulling the whole document.",
    )
    add(
        f"{SCHEME}://resource-definitions",
        resource_definitions_resource,
        "resource-definitions",
        "The platform-wide catalog of resource definitions -- the namespaced, "
        "versioned types that dependency roles are declared against.",
    )
    add(
        f"{SCHEME}://repo-classes/{{repo_class_name}}/discovery",
        repo_class_discovery_resource,
        "repo-class-discovery",
        "One repo class's BACON discovery metadata from its latest version: "
        "a summary, its entry points, every capability it declares (name, "
        "kind, description, source location) and related docs. Use the "
        "search_capabilities tool to find classes by what they can do, and "
        "describe_repo_class for dependencies and configuration.",
    )
    return uris
