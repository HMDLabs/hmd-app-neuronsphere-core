"""Effective deployed-configuration shaping for a single RepoInstance.

Pure functions extracted from ``views.py`` so the GUI views and the MCP tool
layer share one implementation. No Django or request state.
"""

from .dependency_roles import classify_dependency_roles


# Top-level keys DeployBase.get_instance_config sets that aren't part of the
# effective deploy configuration -- excluded from the "Configuration" section
# since they're shown in "Details" (or, for "dependencies", their own section).
INSTANCE_METADATA_KEYS = {
    "instance_name",
    "repo_name",
    "version",
    "deployment_id",
    "hmd_region",
    "dependencies",
}


def build_instance_detail_sections(
    client, config: dict, history_list: list, environment: str = None
) -> dict:
    """Partition a get_deployment_config response into three display-friendly
    sections instead of one flat blob: metadata ("details"), the full merged
    effective configuration that ``hmd deploy`` would actually use
    ("configuration"), and per-role dependency wiring ("dependency_rows", each
    tagged with its wiring kind via classify_dependency_roles). Pure — no
    Django/request state.
    """
    status = history_list[0].get("status") if history_list else None

    details = {
        "instance_name": config.get("instance_name", ""),
        "repo_class_name": config.get("repo_name", ""),
        "version": config.get("version", ""),
        "deployment_id": config.get("deployment_id", ""),
        "hmd_region": config.get("hmd_region"),
        "status": status,
    }

    configuration = {k: v for k, v in config.items() if k not in INSTANCE_METADATA_KEYS}

    classified = {}
    if details["repo_class_name"] and details["version"]:
        classified, _ = classify_dependency_roles(
            client, details["repo_class_name"], details["version"], environment
        )

    dependency_rows = []
    for role, role_cfg in (config.get("dependencies") or {}).items():
        cfgs = role_cfg if isinstance(role_cfg, list) else [role_cfg]
        targets = [c.get("instance_name", "") for c in cfgs if isinstance(c, dict)]
        dependency_rows.append(
            {
                "role": role,
                "targets": targets,
                "kind": classified.get(role, {}).get("kind", "instance"),
            }
        )

    return {
        "details": details,
        "configuration": configuration,
        "dependency_rows": dependency_rows,
    }
