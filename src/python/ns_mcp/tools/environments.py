"""Environment discovery and comparison -- the entry point for any MCP session."""
from fastmcp.exceptions import ToolError

from deployments.models import AuditLog, UserEnvironmentPermission
from deployments.services.bom_diff import compute_environment_diff
from deployments.services.environment_service import get_user_environments

from ..tooling import read_tool

#: Roles a user may hold on an environment, weakest first, so the strongest
#: grant wins when a user has both a manual and an Okta-synced permission row
#: for the same environment (``unique_together`` is per-source, so that happens).
_ROLE_RANK = {"viewer": 0, "deployer": 1, "admin": 2}


@read_tool(action=AuditLog.Action.MCP_TOOL_CALL)
def list_environments(ctx) -> dict:
    """Environments the caller may read, with the role they hold on each."""
    names = get_user_environments(ctx.user, ctx.client)

    if ctx.user.is_superuser:
        return {
            "environments": [{"name": n, "role": "superuser"} for n in names],
            "source": "deployment_service",
            "total": len(names),
        }

    roles: dict = {}
    rows = UserEnvironmentPermission.objects.filter(
        user=ctx.user, environment__in=names
    ).values_list("environment", "role")
    for environment, role in rows:
        current = roles.get(environment)
        if current is None or _ROLE_RANK.get(role, 0) > _ROLE_RANK.get(current, 0):
            roles[environment] = role

    return {
        "environments": [{"name": n, "role": roles.get(n, "viewer")} for n in names],
        "source": "permissions",
        "total": len(names),
    }


@read_tool(
    action=AuditLog.Action.MCP_TOOL_CALL,
    environment_arg=("from_environment", "to_environment"),
)
def compare_environments(
    ctx,
    from_environment: str,
    to_environment: str,
    detail: str = "summary",
) -> dict:
    """What differs between two environments, as the compare page renders it.

    Both environments are authorized by the decorator -- the GUI's own
    environment_compare view does that check inline and, in doing so, misses
    the superuser short-circuit in services.authz.
    """
    response = ctx.client.compare_environments(
        from_env=from_environment, to_env=to_environment
    )
    if not response.success:
        raise ToolError(
            f"Could not compare '{from_environment}' with '{to_environment}': "
            f"{response.error}"
        )

    diff = compute_environment_diff(response.data or {})
    counts = {
        "only_in_source": len(diff["only_in_source"]),
        "only_in_target": len(diff["only_in_target"]),
        "modified": len(diff["modified"]),
    }

    result = {
        "from_environment": from_environment,
        "to_environment": to_environment,
        "detail": "summary" if detail != "full" else "full",
        "summary": counts,
    }

    if detail != "full":
        # Names only: enough to decide what to look at, without the per-instance
        # configuration diffs, which are by far the bulk of the payload.
        result["only_in_source"] = [
            i.get("repo_instance_name", "") for i in diff["only_in_source"]
        ]
        result["only_in_target"] = [
            i.get("repo_instance_name", "") for i in diff["only_in_target"]
        ]
        result["modified"] = [
            {
                "repo_instance_name": m.get("repo_instance_name", ""),
                "version_change": m.get("version_change"),
                "config_changed": bool(m.get("config_diff")),
                "dependencies_changed": bool(m.get("dependency_diff")),
            }
            for m in diff["modified"]
        ]
        return result

    result["only_in_source"] = diff["only_in_source"]
    result["only_in_target"] = diff["only_in_target"]
    result["modified"] = [
        {
            "repo_instance_name": m.get("repo_instance_name", ""),
            "repo_class_name": m.get("repo_class_name", ""),
            "version_change": m.get("version_change"),
            "config_diff": m.get("config_diff"),
            "dependency_diff": m.get("dependency_diff"),
        }
        for m in diff["modified"]
    ]
    return result


def register(mcp):
    """Register this module's tools. Returns the names registered."""
    mcp.tool(
        list_environments,
        name="list_environments",
        description=(
            "List the NeuronSphere environments you have access to, with your "
            "role on each. Call this first: every other environment-scoped tool "
            "rejects an environment you cannot view. Takes no arguments."
        ),
    )
    mcp.tool(
        compare_environments,
        name="compare_environments",
        description=(
            "Compare two environments and report what differs: instances only "
            "in the source, instances only in the target, and instances present "
            "in both whose version, configuration, or dependency wiring has "
            "changed. detail='summary' (the default) returns counts and "
            "instance names with change flags; detail='full' adds the "
            "per-instance configuration and dependency deltas and is much "
            "larger. Requires view access to *both* environments."
        ),
    )
    return ["list_environments", "compare_environments"]
