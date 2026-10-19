"""Shape a bundle version's declared roles for the catalog views (NERD009 SPEC001)."""
from typing import Dict, List, Optional


def _flag(value, default: bool) -> bool:
    """Bundle declarations carry booleans as the strings ``"true"``/``"false"``."""
    if value is None:
        return default
    return str(value).lower() == "true"


def _resource_label(resource: Optional[Dict]) -> Optional[str]:
    if not resource:
        return None
    label = f"{resource.get('resource_namespace', '')}/{resource.get('resource_definition_name', '')}"
    spec = resource.get("version_spec")
    return f"{label} {spec}" if spec else label


def role_rows(roles: Optional[Dict]) -> List[Dict]:
    """One row per role, sorted by role name.

    A role is required and provisioned unless declared otherwise, and is not
    dedicated; ``bind`` is always a list (a single role name is accepted).
    """
    rows = []
    for role, member in sorted((roles or {}).items()):
        bind = member.get("bind") or []
        rows.append(
            {
                "role": role,
                "repo_class_name": member.get("repo_class_name"),
                "resource": _resource_label(member.get("resource")),
                "required": _flag(member.get("required"), True),
                "version_spec": member.get("version_spec"),
                "tag_selector": member.get("tag_selector"),
                "provision": _flag(member.get("provision"), True),
                "dedicated": _flag(member.get("dedicated"), False),
                "bind": [bind] if isinstance(bind, str) else list(bind),
            }
        )
    return rows
