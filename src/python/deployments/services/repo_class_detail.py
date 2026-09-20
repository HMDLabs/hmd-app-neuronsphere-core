"""RepoClassVersion declared-configuration shaping and DeploymentSet lookups.

Pure functions extracted from ``views.py`` so the GUI views and the MCP tool
layer share one implementation. No Django or request state.
"""

# The BACON ``discovery.capabilities[].kind`` enum (hmd-docs-bacon schema.rst),
# in display order. The backend rejects anything else with a 400; the GUI form
# and the MCP tool check locally first so a typo never costs a round trip.
CAPABILITY_KINDS = ("endpoint", "cli_command", "function", "class", "operation")


def build_repo_class_version_detail_sections(detail: dict) -> dict:
    """Shape a get_repo_class_version_detail() response for the template."""
    if not detail:
        return {
            "discovery": {},
            "dependency_rows": [],
            "default_configuration": {},
            "created": None,
            "updated": None,
        }

    dependency_rows = [
        {
            "role": role,
            "repo_class_name": dep.get("repo_class_name"),
            "required": str(dep.get("required")).lower() == "true",
            "version_spec": dep.get("version_spec"),
        }
        for role, dep in (detail.get("dependencies") or {}).items()
    ]
    dependency_rows.sort(key=lambda r: r["role"])

    return {
        "discovery": detail.get("discovery") or {},
        "dependency_rows": dependency_rows,
        "default_configuration": detail.get("default_configuration") or {},
        # Django templates forbid leading-underscore attribute/key lookups
        # (e.g. `detail._created`), so pull these out here instead.
        "created": detail.get("_created"),
        "updated": detail.get("_updated"),
    }


def environments_for_deployment_set(client, deployment_set: str) -> list:
    """Return the environment names that make up a DeploymentSet.

    Reads the DeploymentSet's ``definition`` entries and collects their
    ``environment`` values. Returns an empty list when the set is unknown or the
    listing call fails.
    """
    environments = []
    ds_response = client.list_deployment_sets()
    if ds_response.success and isinstance(ds_response.data, list):
        for ds in ds_response.data:
            if ds.get("name") == deployment_set:
                for entry in ds.get("definition") or []:
                    env_name = (
                        entry.get("environment") if isinstance(entry, dict) else None
                    )
                    if env_name:
                        environments.append(env_name)
                break
    return environments


def search_repo_classes(items: list, query: str) -> list:
    """Case-insensitive substring filter over repo class name, type and the
    latest version's discovery ``summary`` (which ``list_repo_classes`` carries
    since hmd-ms-deployment NERD0013).

    An empty ``query`` is a no-op. Extracted from the inline block in
    ``repo_class_list`` so the GUI and the MCP catalog tool filter identically.
    Capability-level search is ``search_discovery`` on the backend, not this.
    """
    if not query:
        return items
    needle = query.lower()
    return [
        rc
        for rc in items
        if needle in (rc.get("repo_class_name") or "").lower()
        or needle in (rc.get("repo_type") or "").lower()
        or needle in (rc.get("summary") or "").lower()
    ]


def build_capability_rows(search_data) -> list:
    """Flatten a ``search_discovery`` envelope into one row per capability.

    Each row carries the class/version it belongs to alongside the capability's
    own fields, which is the shape both the capability search table and the MCP
    ``search_capabilities`` tool render. Classes that matched on their summary
    alone contribute no rows; the caller lists them separately if it wants to.
    """
    if not isinstance(search_data, dict):
        return []
    items = search_data.get("items")
    if not isinstance(items, list):
        return []
    rows = []
    for item in items:
        if not isinstance(item, dict):
            continue
        capabilities = item.get("capabilities")
        if not isinstance(capabilities, list):
            continue
        for cap in capabilities:
            if not isinstance(cap, dict):
                continue
            rows.append(
                {
                    "repo_class_name": item.get("repo_class_name") or "",
                    "version": item.get("version") or "",
                    "summary": item.get("summary") or "",
                    "name": cap.get("name") or "",
                    "kind": cap.get("kind") or "",
                    "description": cap.get("description") or "",
                    "location": cap.get("location") or "",
                }
            )
    return rows
