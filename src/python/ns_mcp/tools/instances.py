"""A single repo instance: its effective configuration and its dependency edges."""
from fastmcp.exceptions import ToolError

from deployments.models import AuditLog
from deployments.services.bom_query import reverse_dependency_index
from deployments.services.config_projection import (
    ConfigPathError,
    config_key_outline,
    project_config_path,
)
from deployments.services.instance_detail import (
    INSTANCE_METADATA_KEYS,
    build_instance_detail_sections,
)

from ..tooling import read_tool
from .bom import fetch_bom


def _find_bom_item(items: list, instance_name: str) -> dict:
    for item in items:
        if item.get("repo_instance_name") == instance_name:
            return item
    return {}


def fetch_instance_config(ctx, environment: str, instance_name: str) -> dict:
    """The merged effective configuration for one instance, or a ToolError.

    One uncached ``get_deployment_config`` call -- the same one the
    instance_detail view makes. Shared by both tools below so an instance that
    is not deployed produces the same message either way.
    """
    response = ctx.client.get_deployment_config(environment, instance_name)
    if not response.success:
        raise ToolError(
            f"Could not read instance '{instance_name}' in '{environment}': "
            f"{response.error}"
        )
    config = response.data if isinstance(response.data, dict) else {}
    if not config:
        raise ToolError(
            f"No instance named '{instance_name}' is deployed in '{environment}'. "
            f"Use describe_environment to list the instances that are."
        )
    return config


@read_tool(
    action=AuditLog.Action.MCP_TOOL_CALL,
    environment_arg="environment",
)
def describe_instance(
    ctx,
    environment: str,
    instance_name: str,
    history_limit: int = 10,
) -> dict:
    """Details, effective configuration, and dependency wiring for one instance."""
    config = fetch_instance_config(ctx, environment, instance_name)

    # The service wraps the records in {"repo_instance": ..., "history": [...]},
    # so unwrap the list here -- same shape the instance_detail view handles.
    history_response = ctx.client.get_deployment_history(environment, instance_name)
    history_data = history_response.data if history_response.success else {}
    if isinstance(history_data, dict):
        history_list = history_data.get("history", []) or []
    else:
        history_list = history_data or []

    # This is the one legitimate caller of classify_dependency_roles (inside
    # build_instance_detail_sections): a single instance, so a single
    # (repo_class, version) pair and one pair of service calls.
    sections = build_instance_detail_sections(
        ctx.client, config, history_list, environment
    )

    try:
        history_limit = max(int(history_limit), 0)
    except (TypeError, ValueError):
        history_limit = 10

    return {
        "environment": environment,
        "instance_name": instance_name,
        "details": sections["details"],
        "configuration": sections["configuration"],
        "dependencies": sections["dependency_rows"],
        "history": history_list[:history_limit],
        "history_total": len(history_list),
        "history_error": history_response.error
        if not history_response.success
        else None,
    }


@read_tool(
    action=AuditLog.Action.MCP_TOOL_CALL,
    environment_arg="environment",
)
def get_instance_dependencies(
    ctx,
    environment: str,
    instance_name: str,
    direction: str = "both",
) -> dict:
    """What an instance depends on, and what depends on it.

    Both directions come out of the one BOM fetch: every item carries its own
    already-resolved ``dependencies`` map, so the reverse edges are just that
    map inverted. No dependency-role classification is involved, which is what
    makes this cheap enough to call for any instance in a large environment;
    ``describe_instance`` is the tool that adds the role's wiring *kind*.
    """
    items = fetch_bom(ctx, environment)
    item = _find_bom_item(items, instance_name)
    if not item:
        raise ToolError(
            f"No instance named '{instance_name}' is in the BOM for "
            f"'{environment}'. Use describe_environment to list the instances "
            f"that are."
        )

    result: dict = {
        "environment": environment,
        "instance_name": instance_name,
        "direction": direction,
    }

    if direction in ("both", "depends_on"):
        known = {i.get("repo_instance_name") for i in items}
        depends_on = []
        unresolved = []
        for role, targets in (item.get("dependencies") or {}).items():
            target_list = targets if isinstance(targets, list) else [targets]
            for target in target_list:
                if target in known:
                    depends_on.append({"instance": target, "role": role})
                else:
                    # Named by the wiring but absent from this BOM -- typically
                    # a dependency satisfied outside the environment, or stale.
                    unresolved.append({"target": target, "role": role})
        depends_on.sort(key=lambda d: (d["instance"] or "", d["role"] or ""))
        result["depends_on"] = depends_on
        result["unresolved"] = unresolved

    if direction in ("both", "dependents"):
        result["dependents"] = reverse_dependency_index(items).get(instance_name, [])

    return result


@read_tool(
    action=AuditLog.Action.MCP_TOOL_CALL,
    environment_arg="environment",
)
def get_instance_configuration(
    ctx,
    environment: str,
    instance_name: str,
    path: str = "",
    keys_only: bool = False,
) -> dict:
    """Just the effective configuration of one instance, optionally projected.

    The cheap sibling of describe_instance: one ``get_deployment_config`` and
    *no* dependency-role classification, so it costs a single round-trip. A
    merged config runs to hundreds of keys, which is why it can be narrowed
    before it is returned rather than after.
    """
    config = fetch_instance_config(ctx, environment, instance_name)
    configuration = {k: v for k, v in config.items() if k not in INSTANCE_METADATA_KEYS}

    try:
        value = project_config_path(configuration, path)
    except ConfigPathError as exc:
        available = ", ".join(str(a) for a in exc.available) or "nothing"
        raise ToolError(
            f"No '{exc.segment}' in the configuration of '{instance_name}' at "
            f"path '{exc.path}'. Available at that level: {available}. Call "
            f"this tool with keys_only=true to see the shape first."
        ) from None

    return {
        "environment": environment,
        "instance_name": instance_name,
        "path": path,
        "keys_only": bool(keys_only),
        "configuration": config_key_outline(value) if keys_only else value,
    }


def register(mcp):
    """Register this module's tools. Returns the names registered."""
    mcp.tool(
        describe_instance,
        name="describe_instance",
        description=(
            "Describe one deployed repo instance: its metadata (repo class, "
            "version, deployment id, status), the full merged effective "
            "configuration that 'hmd deploy' would use, its dependency wiring "
            "per role tagged with the wiring kind (resource, repo_class, or "
            "instance), and its recent deployment history. Use "
            "describe_environment to find instance names. Requires view access "
            "to the environment."
        ),
    )
    mcp.tool(
        get_instance_dependencies,
        name="get_instance_dependencies",
        description=(
            "Show an instance's dependency edges in either direction. "
            "direction='depends_on' lists what it needs, 'dependents' lists "
            "what would be affected if it changed, and 'both' (the default) "
            "returns each. This is the cheap edge query -- it costs one BOM "
            "read and no role classification, so it is safe to call across many "
            "instances; use describe_instance when you also need the wiring "
            "kind or the configuration. Requires view access to the environment."
        ),
    )
    mcp.tool(
        get_instance_configuration,
        name="get_instance_configuration",
        description=(
            "Return the effective deployed configuration of one instance -- the "
            "merged values 'hmd deploy' would use -- and nothing else. Cheaper "
            "than describe_instance, which also classifies dependency roles. "
            "A real configuration is large, so narrow it: keys_only=true "
            "returns each key with its type instead of its value, and 'path' "
            "drills in with a dotted path ('database.host', or "
            "'dependencies.db.0.instance_name' to index a list). The two "
            "compose -- probe with keys_only, then fetch the branch you want. "
            "Requires view access to the environment."
        ),
    )
    return [
        "describe_instance",
        "get_instance_dependencies",
        "get_instance_configuration",
    ]
