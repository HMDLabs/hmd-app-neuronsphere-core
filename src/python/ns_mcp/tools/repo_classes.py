"""The RepoClass catalog -- what can be deployed, and what each version declares.

Platform-wide facts, not environment-scoped: neither tool here declares an
``environment_arg``, for the same reason ``find_resource_providers`` does not.
What is *deployed* is describe_environment's job.
"""
from typing import Optional

from fastmcp.exceptions import ToolError

from deployments.models import AuditLog
from deployments.services.pagination import build_pagination
from deployments.services.repo_class_detail import (
    CAPABILITY_KINDS,
    build_capability_rows,
    build_repo_class_version_detail_sections,
    search_repo_classes as filter_repo_classes,
)

from ..tooling import clamp_limit, read_tool


def _coerce_offset(offset) -> int:
    try:
        return max(int(offset), 0)
    except (TypeError, ValueError):
        return 0


@read_tool(action=AuditLog.Action.MCP_TOOL_CALL)
def search_repo_classes(
    ctx,
    query: str = "",
    limit: Optional[int] = None,
    offset: int = 0,
) -> dict:
    """Search the repo class catalog by name, repo type, or summary.

    ``description`` is the latest version's BACON discovery summary, which
    ``list_repo_classes`` carries since hmd-ms-deployment NERD0013. For
    capability-level search ("which class can rotate logs?") use
    ``search_capabilities``; this is the class-level catalog.
    """
    response = ctx.client.list_repo_classes()
    if not response.success:
        raise ToolError(f"Could not read the repo class catalog: {response.error}")

    items = response.data if isinstance(response.data, list) else []
    matched = filter_repo_classes(items, query)
    matched = sorted(matched, key=lambda rc: (rc.get("repo_class_name") or ""))

    limit = clamp_limit(limit)
    offset = _coerce_offset(offset)

    return {
        "query": query,
        "repo_classes": [
            {
                "repo_class_name": rc.get("repo_class_name", ""),
                "repo_type": rc.get("repo_type", ""),
                "description": rc.get("summary") or rc.get("description") or "",
                "latest_version": rc.get("latest_version") or "",
                "capability_count": rc.get("capability_count") or 0,
            }
            for rc in matched[offset : offset + limit]
        ],
        "pagination": build_pagination(len(matched), limit, offset),
    }


@read_tool(action=AuditLog.Action.MCP_TOOL_CALL)
def search_capabilities(
    ctx,
    query: str = "",
    kind: str = "",
    repo_class_name: str = "",
    limit: Optional[int] = None,
    offset: int = 0,
) -> dict:
    """ "Which repo class can do X?" over every class's latest discovery block.

    One ``search_discovery`` call (hmd-ms-deployment NERD0013 SPEC0002); the
    backend does the matching and ranking. ``kind`` is validated here so a
    typo never costs a round trip. Rows are one per matching capability via
    the same ``build_capability_rows`` the GUI's capability search renders;
    ``repo_classes`` lists every matching class -- including summary-only hits
    with no capability rows -- so the caller can follow up with
    ``describe_repo_class(name, version)``.
    """
    if kind and kind not in CAPABILITY_KINDS:
        raise ToolError(
            f"Unknown capability kind '{kind}'. Use one of: "
            f"{', '.join(CAPABILITY_KINDS)}."
        )
    limit = clamp_limit(limit)
    offset = _coerce_offset(offset)

    response = ctx.client.search_discovery(
        q=query, kind=kind, repo_class_name=repo_class_name, limit=limit, offset=offset
    )
    if not response.success:
        raise ToolError(f"Could not search the discovery catalog: {response.error}")
    data = response.data if isinstance(response.data, dict) else {}
    items = [it for it in (data.get("items") or []) if isinstance(it, dict)]

    return {
        "query": query,
        "kind": kind,
        "repo_class_name": repo_class_name,
        "capabilities": build_capability_rows(data),
        "repo_classes": [
            {
                "repo_class_name": it.get("repo_class_name") or "",
                "version": it.get("version") or "",
                "summary": it.get("summary") or "",
                "score": it.get("score") or 0,
                "matched_fields": list(it.get("matched_fields") or []),
                "capability_count": it.get("capability_count") or 0,
            }
            for it in items
        ],
        "pagination": build_pagination(int(data.get("total") or 0), limit, offset),
    }


@read_tool(action=AuditLog.Action.MCP_TOOL_CALL)
def describe_repo_class(
    ctx,
    repo_class_name: str,
    version: str = "",
    q: str = "",
    limit: Optional[int] = None,
    offset: int = 0,
) -> dict:
    """A repo class: its versions, or one version's declared configuration.

    Without ``version`` this is the paged version listing, which deliberately
    uses ``find_repo_class_versions_page`` rather than the unpaged variant: the
    paged endpoint skips per-version dependency resolution and is cached, and a
    long-lived repo class has hundreds of versions.
    """
    if not version:
        limit = clamp_limit(limit)
        offset = _coerce_offset(offset)
        response = ctx.client.find_repo_class_versions_page(
            repo_class_name, q=q, limit=limit, offset=offset
        )
        if not response.success:
            raise ToolError(
                f"Could not list versions of '{repo_class_name}': {response.error}. "
                f"Use search_repo_classes to check the name."
            )
        data = response.data if isinstance(response.data, dict) else {}
        items = data.get("items", []) or []
        return {
            "repo_class_name": repo_class_name,
            "q": q,
            "versions": [
                {
                    "version": v.get("version", ""),
                    "repo_type": v.get("repo_type", ""),
                    "identifier": v.get("identifier") or v.get("id"),
                }
                for v in items
            ],
            "pagination": build_pagination(data.get("total", 0), limit, offset),
        }

    response = ctx.client.get_repo_class_version_detail(repo_class_name, version)
    if not response.success:
        raise ToolError(
            f"Could not read '{repo_class_name}' version '{version}': "
            f"{response.error}. Call this tool without a version to list the "
            f"versions that exist."
        )
    detail = response.data if isinstance(response.data, dict) else {}
    if not detail:
        raise ToolError(
            f"No version '{version}' of repo class '{repo_class_name}'. Call "
            f"this tool without a version to list the versions that exist."
        )

    sections = build_repo_class_version_detail_sections(detail)
    return {
        "repo_class_name": repo_class_name,
        "version": version,
        "discovery": sections["discovery"],
        # Each row is what the class *declares* it needs, per role -- the
        # counterpart of the wiring describe_instance reports for a deployment.
        "dependencies": sections["dependency_rows"],
        "default_configuration": sections["default_configuration"],
        "created": sections["created"],
        "updated": sections["updated"],
    }


def register(mcp):
    """Register this module's tools. Returns the names registered."""
    mcp.tool(
        search_repo_classes,
        name="search_repo_classes",
        description=(
            "Search the platform-wide catalog of repo classes -- the things "
            "that can be deployed -- by a case-insensitive substring of the "
            "class name, repo type, or one-paragraph summary. Each result "
            "carries that summary as 'description', plus its latest version "
            "and how many capabilities it declares. An empty query returns "
            "the whole catalog, paginated with 'limit'/'offset'. To search "
            "what classes can DO rather than what they are called, use "
            "search_capabilities. This is the catalog, not an environment: "
            "use describe_environment to see what is actually deployed."
        ),
    )
    mcp.tool(
        search_capabilities,
        name="search_capabilities",
        description=(
            "Find which repo classes can do something. Searches every class's "
            "latest-version discovery metadata -- its summary and its declared "
            "capabilities (endpoints, CLI commands, functions, classes, "
            "operations) and entry points. 'query' is free text: every word "
            "must appear in a summary, capability name/description or entry "
            "point (substring, case-insensitive; class names are NOT searched "
            "-- use 'repo_class_name' as a prefix filter for that). 'kind' "
            "restricts to one capability kind. Returns 'capabilities' (one "
            "row per matching capability, with the class, version, kind, "
            "description and source location) and 'repo_classes' (every "
            "matching class, ranked, including ones that matched on summary "
            "alone). Follow up with describe_repo_class(name, version) for a "
            "class's full discovery block, dependencies and configuration. "
            "A catalog query, not scoped to an environment."
        ),
    )
    mcp.tool(
        describe_repo_class,
        name="describe_repo_class",
        description=(
            "Describe a repo class. Without 'version' it returns that class's "
            "versions, paginated and optionally narrowed by 'q'. With "
            "'version' it returns what that version declares: its discovery "
            "metadata, its dependency roles (each with the repo class and "
            "version spec that satisfies it, and whether it is required), and "
            "its default configuration. Use search_repo_classes to find the "
            "name first. A catalog query, not scoped to an environment."
        ),
    )
    return ["search_repo_classes", "search_capabilities", "describe_repo_class"]
