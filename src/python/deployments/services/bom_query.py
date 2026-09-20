"""Read-side queries over an environment BOM.

Pure functions extracted from ``views.py`` so the GUI views and the MCP tool
layer share one implementation. No Django or request state.
"""


def build_bom_dag_elements(bom_data: list) -> dict:
    """Build Cytoscape {nodes, edges} JSON from BOM data. Pure — no Django/request state.

    Edges are built directly from each BOM item's own ``dependencies`` map — the
    already-resolved current wiring — with no dependency-role classification. An
    earlier version tagged each edge with a wiring ``kind`` ("resource" |
    "repo_class" | "instance") via ``classify_dependency_roles``, but that call
    triggers a full environment reload per unique (repo_class, version) pair in
    the BOM purely to fetch role-declaration metadata this view never used beyond
    the kind label — the frontend (bom_dag.js) already falls back to the
    "instance" style when ``kind`` is absent, so it's simply omitted here.
    """
    nodes = []
    edges = []
    instance_set = {item["repo_instance_name"] for item in bom_data}

    for item in bom_data:
        name = item["repo_instance_name"]
        rc = item.get("repo_class_name", "")
        rc_version = item.get("repo_class_version", "")
        # Derive type prefix: hmd-inf, hmd-ms, hmd-app, etc.
        parts = rc.split("-")
        type_prefix = "-".join(parts[:2]) if len(parts) >= 2 else rc

        nodes.append(
            {
                "data": {
                    "id": name,
                    "label": name,
                    "repo_class": rc,
                    "version": rc_version,
                    "status": item.get("status", ""),
                    "type_prefix": type_prefix,
                    "dep_count": len(item.get("dependencies", {})),
                }
            }
        )

        # Edges from dependencies
        dependencies = item.get("dependencies", {})
        for role, targets in dependencies.items():
            target_list = targets if isinstance(targets, list) else [targets]
            for t in target_list:
                if t in instance_set:
                    edges.append(
                        {
                            "data": {
                                "source": name,
                                "target": t,
                                "role": role,
                            }
                        }
                    )

    return {"nodes": nodes, "edges": edges}


# Fields the BOM table allows sorting on. Anything else is ignored rather than
# rejected, so a stale or crafted ``?sort=`` can't blow up the view.
SORTABLE_FIELDS = (
    "repo_instance_name",
    "repo_class_name",
    "repo_class_version",
    "status",
)


def sort_bom(items: list, sort_by: str, sort_dir: str = "asc") -> list:
    """Sort BOM items by one of ``SORTABLE_FIELDS``.

    An unrecognised ``sort_by`` returns the list unchanged, matching the
    original inline behaviour.
    """
    if sort_by not in SORTABLE_FIELDS:
        return items
    return sorted(items, key=lambda x: x.get(sort_by, ""), reverse=sort_dir == "desc")


def filter_bom(
    items: list, search: str = "", status: str = "", repo_class: str = ""
) -> list:
    """Apply the status / repo_class / free-text filters to BOM items.

    ``search`` is a case-insensitive substring match against the instance name
    or the repo class name. Empty filters are no-ops.
    """
    if status:
        items = [i for i in items if i.get("status") == status]
    if repo_class:
        items = [i for i in items if i.get("repo_class_name") == repo_class]
    if search:
        needle = search.lower()
        items = [
            i
            for i in items
            if needle in i.get("repo_instance_name", "").lower()
            or needle in i.get("repo_class_name", "").lower()
        ]
    return items


def bom_facets(items: list) -> dict:
    """Distinct statuses and repo classes present in a BOM.

    Must be computed from the *unfiltered* set so the UI (and an MCP caller)
    can pick the next filter without re-fetching.
    """
    return {
        "statuses": sorted({i.get("status", "") for i in items if i.get("status")}),
        "repo_classes": sorted(
            {i.get("repo_class_name", "") for i in items if i.get("repo_class_name")}
        ),
    }


def summarize_bom(items: list) -> dict:
    """Counts by status and by repo class -- a token-cheap BOM overview."""
    by_status: dict = {}
    by_repo_class: dict = {}
    for item in items:
        status = item.get("status") or "UNKNOWN"
        by_status[status] = by_status.get(status, 0) + 1
        rc = item.get("repo_class_name") or ""
        if rc:
            by_repo_class[rc] = by_repo_class.get(rc, 0) + 1
    return {
        "total": len(items),
        "by_status": dict(sorted(by_status.items())),
        "by_repo_class": [
            {"repo_class": k, "count": v}
            for k, v in sorted(by_repo_class.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
    }


def reverse_dependency_index(items: list) -> dict:
    """Map each instance to the instances that depend on it.

    Built from the same already-resolved ``dependencies`` maps that
    ``build_bom_dag_elements`` walks, so it costs one BOM fetch and no
    role-classification calls. Targets not present in the BOM are skipped --
    they are reported separately as unresolved by the caller.
    """
    known = {i.get("repo_instance_name") for i in items}
    index: dict = {}
    for item in items:
        name = item.get("repo_instance_name")
        for role, targets in (item.get("dependencies") or {}).items():
            target_list = targets if isinstance(targets, list) else [targets]
            for target in target_list:
                if target in known:
                    index.setdefault(target, []).append(
                        {"instance": name, "role": role}
                    )
    for dependents in index.values():
        dependents.sort(key=lambda d: (d["instance"] or "", d["role"] or ""))
    return index
