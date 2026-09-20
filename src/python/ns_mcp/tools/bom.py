"""Environment BOM queries -- what is deployed where."""
from typing import Optional

from deployments.models import AuditLog
from deployments.services.bom_query import (
    SORTABLE_FIELDS,
    bom_facets,
    filter_bom,
    sort_bom,
    summarize_bom,
)
from deployments.services.pagination import build_pagination

from ..tooling import clamp_limit, read_tool


def fetch_bom(ctx, environment: str) -> list:
    """The environment's BOM, or an empty list if the service has nothing.

    Exactly one call, shared with the GUI through the client's ``bom:<env>``
    cache. Deliberately *not* enriched with dependency-role classification: that
    costs two service round-trips per unique (repo_class, version) pair and
    fanning it across a BOM is what caused the DAG gateway timeouts fixed in
    e4de1e1. ``describe_instance`` does the classification, for one instance.
    """
    from fastmcp.exceptions import ToolError

    response = ctx.client.get_deployment_bom(environment)
    if not response.success:
        raise ToolError(
            f"Could not read the BOM for environment '{environment}': "
            f"{response.error}"
        )
    return response.data if isinstance(response.data, list) else []


@read_tool(
    action=AuditLog.Action.MCP_TOOL_CALL,
    environment_arg="environment",
)
def describe_environment(
    ctx,
    environment: str,
    detail: str = "summary",
    search: str = "",
    status: str = "",
    repo_class: str = "",
    sort_by: str = "repo_instance_name",
    sort_dir: str = "asc",
    limit: Optional[int] = None,
    offset: int = 0,
) -> dict:
    """What is deployed in an environment: counts, or the instance list."""
    items = fetch_bom(ctx, environment)

    # Facets come from the unfiltered set so a caller can pick its next filter
    # without another round-trip.
    facets = bom_facets(items)

    if detail != "full":
        return {
            "environment": environment,
            "detail": "summary",
            "summary": summarize_bom(items),
            "facets": facets,
        }

    matched = sort_bom(
        filter_bom(items, search=search, status=status, repo_class=repo_class),
        sort_by,
        sort_dir,
    )

    limit = clamp_limit(limit)
    try:
        offset = max(int(offset), 0)
    except (TypeError, ValueError):
        offset = 0

    page = [
        {
            "instance_name": i.get("repo_instance_name", ""),
            "repo_class": i.get("repo_class_name", ""),
            "version": i.get("repo_class_version", ""),
            "status": i.get("status", ""),
            "dependency_count": len(i.get("dependencies") or {}),
        }
        for i in matched[offset : offset + limit]
    ]

    return {
        "environment": environment,
        "detail": "full",
        "instances": page,
        "pagination": build_pagination(len(matched), limit, offset),
        "facets": facets,
        "filters": {
            "search": search,
            "status": status,
            "repo_class": repo_class,
            "sort_by": sort_by,
            "sort_dir": sort_dir,
        },
    }


def register(mcp):
    """Register this module's tools. Returns the names registered."""
    mcp.tool(
        describe_environment,
        name="describe_environment",
        description=(
            "Describe what is deployed in a NeuronSphere environment. "
            "detail='summary' (the default) returns instance counts by status "
            "and by repo class plus the available filter values -- start here, "
            "it is cheap. detail='full' returns the instance list itself, "
            "narrowed by 'search' (matches instance or repo class name), "
            "'status', and 'repo_class', sorted by one of "
            f"{', '.join(SORTABLE_FIELDS)}, and paginated with 'limit'/'offset'. "
            "Instance names from here are what describe_instance and "
            "get_instance_dependencies take. Requires view access to the "
            "environment; call list_environments first."
        ),
    )
    return ["describe_environment"]
