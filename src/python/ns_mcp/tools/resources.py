"""Resource definitions and the repo classes that can provide them."""
from typing import Optional

from fastmcp.exceptions import ToolError

from deployments.models import AuditLog
from deployments.services.pagination import build_pagination
from deployments.services.resource_query import (
    filter_resource_definitions,
    resolve_resource_definition,
)

from ..tooling import clamp_limit, read_tool


def _data_or(response, fallback):
    """Unwrap an APIResponse, degrading to ``fallback`` on failure.

    Each lookup below is independent: a missing ancestry or an unavailable
    schema should still leave the producer list useful, which is how
    ``resource_definition_detail`` renders the same four calls.
    """
    if getattr(response, "success", False):
        return response.data
    return fallback


@read_tool(action=AuditLog.Action.MCP_TOOL_CALL)
def find_resource_providers(
    ctx,
    resource_definition_name: str,
    namespace: Optional[str] = None,
    version: Optional[str] = None,
    include_subtypes: bool = False,
) -> dict:
    """Which repo classes can produce a given resource definition.

    A global catalog read, not environment-scoped -- a resource definition and
    its producers are platform-wide facts, so this tool deliberately takes no
    ``environment`` and performs no per-environment authorization. To see what
    is actually *deployed* and providing the resource in one environment, use
    describe_environment / describe_instance.
    """
    definition = resolve_resource_definition(
        ctx.client, resource_definition_name, namespace=namespace, version=version
    )
    if not definition:
        qualified = (
            f"{namespace}/{resource_definition_name}"
            if namespace
            else resource_definition_name
        )
        raise ToolError(
            f"No resource definition matches '{qualified}'"
            + (f" at version {version}" if version else "")
            + ". Names are namespaced, e.g. "
            "kubernetes.neuronsphere.io/kubernetes-cluster."
        )

    rd_id = definition.get("identifier") or definition.get("id")
    if not rd_id:
        raise ToolError(
            f"Resource definition '{resource_definition_name}' has no identifier, "
            f"so its producers cannot be looked up."
        )

    ancestry_response = ctx.client.get_resource_definition_ancestry(rd_id)
    schema_response = ctx.client.get_effective_output_schema(rd_id)
    producers_response = ctx.client.get_producers(
        rd_id, include_subtypes=include_subtypes
    )

    producers = _data_or(producers_response, []) or []

    return {
        "definition": definition,
        "include_subtypes": include_subtypes,
        # The isa chain: with include_subtypes, a producer of any of these
        # subtypes also satisfies a requirement for this definition.
        "ancestry": _data_or(ancestry_response, []) or [],
        "output_schema": _data_or(schema_response, None),
        "producers": producers,
        "total_producers": len(producers) if isinstance(producers, list) else 0,
        "errors": {
            k: v
            for k, v in {
                "ancestry": None
                if ancestry_response.success
                else ancestry_response.error,
                "output_schema": None
                if schema_response.success
                else schema_response.error,
                "producers": None
                if producers_response.success
                else producers_response.error,
            }.items()
            if v
        },
    }


@read_tool(action=AuditLog.Action.MCP_TOOL_CALL)
def list_resource_definitions(
    ctx,
    namespace: str = "",
    query: str = "",
    limit: Optional[int] = None,
    offset: int = 0,
) -> dict:
    """The resource definition catalog: the vocabulary of dependency roles.

    ``namespace`` narrows server-side (and is what the client caches on);
    ``query`` is the same client-side substring filter the catalog page applies,
    over name, namespace, and description.
    """
    response = ctx.client.list_resource_definitions(
        resource_namespace=namespace or None
    )
    if not response.success:
        raise ToolError(
            f"Could not read the resource definition catalog: {response.error}"
        )

    items = response.data if isinstance(response.data, list) else []
    matched = filter_resource_definitions(items, query)
    matched = sorted(
        matched,
        key=lambda d: (
            d.get("resource_namespace") or "",
            d.get("resource_definition_name") or "",
        ),
    )

    limit = clamp_limit(limit)
    try:
        offset = max(int(offset), 0)
    except (TypeError, ValueError):
        offset = 0

    return {
        "namespace": namespace,
        "query": query,
        "definitions": [
            {
                "resource_definition_name": d.get("resource_definition_name", ""),
                "resource_namespace": d.get("resource_namespace", ""),
                "version": d.get("version", ""),
                "description": d.get("description") or "",
                "identifier": d.get("identifier") or d.get("id"),
            }
            for d in matched[offset : offset + limit]
        ],
        "pagination": build_pagination(len(matched), limit, offset),
        "namespaces": sorted(
            {d.get("resource_namespace") for d in items if d.get("resource_namespace")}
        ),
    }


@read_tool(
    action=AuditLog.Action.MCP_TOOL_CALL,
    environment_arg="environment",
)
def find_resource_candidates(
    ctx,
    environment: str,
    resource_definition_name: str,
    namespace: str = "",
    version_spec: str = "",
    tags: str = "",
) -> dict:
    """What is *deployed* in one environment that could satisfy a role.

    The environment-scoped counterpart of find_resource_providers, which answers
    the same question from the platform-wide catalog. ``environment`` is
    required rather than optional precisely so the permission check has
    something to check -- an optional one would reach the decorator as None.
    ``tags`` is the usual ``k=v,k=v`` AND-selector.
    """
    definition = resolve_resource_definition(
        ctx.client, resource_definition_name, namespace=namespace or None
    )

    response = ctx.client.suggest_resource_dependencies(
        environment,
        resource_namespace=namespace or (definition or {}).get("resource_namespace"),
        resource_definition_name=resource_definition_name,
        version_spec=version_spec or None,
        tags=tags or None,
    )
    if not response.success:
        raise ToolError(
            f"Could not find candidates for '{resource_definition_name}' in "
            f"'{environment}': {response.error}"
        )

    data = response.data if isinstance(response.data, dict) else {}
    candidates = data.get("candidates", []) or []

    return {
        "environment": environment,
        "resource_definition": definition,
        "resource_definition_name": resource_definition_name,
        "namespace": namespace,
        "version_spec": version_spec,
        "tags": tags,
        "candidates": candidates,
        "total": len(candidates) if isinstance(candidates, list) else 0,
    }


def register(mcp):
    """Register this module's tools. Returns the names registered."""
    mcp.tool(
        find_resource_providers,
        name="find_resource_providers",
        description=(
            "Find which repo classes can provide a resource definition -- the "
            "answer to 'what could satisfy this dependency role'. Takes the "
            "resource definition name and optionally its namespace and version "
            "(names are namespaced, e.g. namespace "
            "'kubernetes.neuronsphere.io' with name 'kubernetes-cluster'). "
            "Returns the definition, its isa ancestry, the effective merged "
            "output schema a consumer can expect, and the producing repo class "
            "versions. Set include_subtypes=true to also count producers of "
            "subtypes, which satisfy the requirement too. This is a "
            "platform-wide catalog query and is not scoped to an environment."
        ),
    )
    mcp.tool(
        list_resource_definitions,
        name="list_resource_definitions",
        description=(
            "List the resource definitions on this platform -- the namespaced, "
            "versioned types (e.g. kubernetes.neuronsphere.io/kubernetes-"
            "cluster) that dependency roles are declared against. Narrow with "
            "'namespace' or a free-text 'query' over name, namespace, and "
            "description; the response also lists every namespace in use, so "
            "call it with no arguments first to orient. Use "
            "find_resource_providers for the repo classes that can produce a "
            "definition. A platform-wide catalog query."
        ),
    )
    mcp.tool(
        find_resource_candidates,
        name="find_resource_candidates",
        description=(
            "Find what is already deployed in one environment that could "
            "satisfy a resource dependency -- the environment-scoped "
            "counterpart of find_resource_providers, which answers the same "
            "question from the platform-wide catalog. Give the resource "
            "definition name and optionally its namespace, a version spec "
            "(e.g. '~= 0.1'), and a 'k=v,k=v' tag selector. Requires view "
            "access to the environment."
        ),
    )
    return [
        "find_resource_providers",
        "list_resource_definitions",
        "find_resource_candidates",
    ]
