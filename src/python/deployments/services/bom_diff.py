"""BOM diff utilities for ChangeSet workflows.

Pure Python module with no Django ORM dependencies. Computes diffs between
ChangeSet items and current BOM state, and computes environment-vs-environment
diffs for the environment-compare view.
"""


def compute_json_diff(old_dict, new_dict):
    """Compute key-level diff between two dicts.

    Returns:
        dict with keys: added, removed, changed. Changed values include old and new.
    """
    old_dict = old_dict or {}
    new_dict = new_dict or {}

    old_keys = set(old_dict.keys())
    new_keys = set(new_dict.keys())

    added = {k: new_dict[k] for k in sorted(new_keys - old_keys)}
    removed = {k: old_dict[k] for k in sorted(old_keys - new_keys)}
    changed = {}
    for k in sorted(old_keys & new_keys):
        if old_dict[k] != new_dict[k]:
            changed[k] = {"old": old_dict[k], "new": new_dict[k]}

    return {"added": added, "removed": removed, "changed": changed}


def _normalize_dep_value(value):
    """Normalize a dependency role value for set-equality comparison.

    A role's value may be a single instance name (``str``) or a list of names
    (``list[str]``). For comparison purposes only, both are reduced to a sorted
    tuple of strings. ``None``/empty becomes ``()``. The original value is kept
    in the diff output unchanged.
    """
    if value is None:
        return ()
    if isinstance(value, list):
        return tuple(sorted(str(v) for v in value if v not in (None, "")))
    return (str(value),)


def compute_dependency_diff(old_deps, new_deps):
    """Compute diff between two dependency maps (role -> instance_name | list).

    Treats a single-string value and a one-element list with the same name as
    equal, and treats lists with the same members in different order as equal.

    Returns:
        dict with keys: added, removed, changed.
    """
    old_deps = old_deps or {}
    new_deps = new_deps or {}

    old_keys = set(old_deps.keys())
    new_keys = set(new_deps.keys())

    added = {k: new_deps[k] for k in sorted(new_keys - old_keys)}
    removed = {k: old_deps[k] for k in sorted(old_keys - new_keys)}
    changed = {}
    for k in sorted(old_keys & new_keys):
        if _normalize_dep_value(old_deps[k]) != _normalize_dep_value(new_deps[k]):
            changed[k] = {"old": old_deps[k], "new": new_deps[k]}

    return {"added": added, "removed": removed, "changed": changed}


def compute_bom_impact(changeset_items, current_bom_dict):
    """Compute the impact of a ChangeSet against the current BOM.

    Args:
        changeset_items: list of ChangeSet item dicts (from ChangeSetDraft.content)
        current_bom_dict: dict keyed by repo_instance_name from current BOM

    Returns:
        list of impact records, each with:
            - repo_instance_name
            - repo_class_name
            - change_type: "NEW", "MODIFIED", or "UNCHANGED"
            - version_change: {"old": str, "new": str} or None
            - config_diff: result of compute_json_diff or None
            - dependency_diff: result of compute_dependency_diff or None
            - current: the current BOM entry (or None for NEW)
            - proposed: the ChangeSet item
    """
    if not changeset_items:
        return []

    current_bom_dict = current_bom_dict or {}
    impacts = []

    for item in changeset_items:
        instance_name = item.get("repo_instance_name", "")
        current = current_bom_dict.get(instance_name)

        if current is None:
            impacts.append(
                {
                    "repo_instance_name": instance_name,
                    "repo_class_name": item.get("repo_class_name", ""),
                    "change_type": "NEW",
                    "version_change": None,
                    "config_diff": None,
                    "dependency_diff": None,
                    "current": None,
                    "proposed": item,
                }
            )
            continue

        # Compare versions
        old_version = current.get("repo_class_version", "")
        new_version = item.get("repo_class_version", "")
        version_change = None
        if old_version != new_version:
            version_change = {"old": old_version, "new": new_version}

        # Compare configurations
        old_config = current.get("instance_configuration") or {}
        new_config = item.get("instance_configuration") or {}
        config_diff = compute_json_diff(old_config, new_config)
        has_config_changes = any(
            [
                config_diff["added"],
                config_diff["removed"],
                config_diff["changed"],
            ]
        )

        # Compare dependencies
        old_deps = current.get("dependencies") or {}
        new_deps = item.get("dependencies") or {}
        dep_diff = compute_dependency_diff(old_deps, new_deps)
        has_dep_changes = any(
            [
                dep_diff["added"],
                dep_diff["removed"],
                dep_diff["changed"],
            ]
        )

        change_type = "UNCHANGED"
        if version_change or has_config_changes or has_dep_changes:
            change_type = "MODIFIED"

        impacts.append(
            {
                "repo_instance_name": instance_name,
                "repo_class_name": item.get("repo_class_name", ""),
                "change_type": change_type,
                "version_change": version_change,
                "config_diff": config_diff if has_config_changes else None,
                "dependency_diff": dep_diff if has_dep_changes else None,
                "current": current,
                "proposed": item,
            }
        )

    return impacts


def summarize_impact(impacts):
    """Summarize impact list into counts.

    Returns:
        dict with keys: new, modified, unchanged
    """
    counts = {"new": 0, "modified": 0, "unchanged": 0}
    for impact in impacts:
        change_type = impact.get("change_type", "UNCHANGED").lower()
        if change_type in counts:
            counts[change_type] += 1
    return counts


def compute_environment_diff(api_response):
    """Categorize a /apiop/compare_environments response into source/target/modified buckets.

    The hmd-ms-deployment service returns:
        {
            "deploy_change_set": [items present in source but absent or different in target],
            "removed_instances": [instance names present in target but not source],
            "existing_change_set": [target items that match each modified source item by name]
        }

    This helper splits ``deploy_change_set`` into ``only_in_source`` (no matching
    target item) and ``modified`` (matching target item, with computed deltas),
    and surfaces ``removed_instances`` as ``only_in_target``.

    Args:
        api_response: dict from compare_environments

    Returns:
        dict with keys:
            - only_in_source: list of source items
            - only_in_target: list of {repo_instance_name} dicts
            - modified: list of {instance, version_change, config_diff,
                                 dependency_diff, source, target}
    """
    api_response = api_response or {}
    source_items = api_response.get("deploy_change_set") or []
    target_items = api_response.get("existing_change_set") or []
    removed_names = api_response.get("removed_instances") or []

    target_by_name = {}
    for t in target_items:
        if not t:
            continue
        name = t.get("repo_instance_name")
        if name:
            target_by_name[name] = t

    only_in_source = []
    modified = []

    for item in source_items:
        name = item.get("repo_instance_name", "")
        target = target_by_name.get(name)
        if target is None:
            only_in_source.append(item)
            continue

        old_version = target.get("repo_class_version", "")
        new_version = item.get("repo_class_version", "")
        version_change = None
        if old_version != new_version:
            version_change = {"old": old_version, "new": new_version}

        config_diff = compute_json_diff(
            target.get("instance_configuration") or {},
            item.get("instance_configuration") or {},
        )
        has_config_changes = any(
            [
                config_diff["added"],
                config_diff["removed"],
                config_diff["changed"],
            ]
        )

        dep_diff = compute_dependency_diff(
            target.get("dependencies") or {},
            item.get("dependencies") or {},
        )
        has_dep_changes = any(
            [
                dep_diff["added"],
                dep_diff["removed"],
                dep_diff["changed"],
            ]
        )

        modified.append(
            {
                "repo_instance_name": name,
                "repo_class_name": item.get("repo_class_name", ""),
                "version_change": version_change,
                "config_diff": config_diff if has_config_changes else None,
                "dependency_diff": dep_diff if has_dep_changes else None,
                "source": item,
                "target": target,
            }
        )

    only_in_target = [{"repo_instance_name": n} for n in removed_names]

    return {
        "only_in_source": only_in_source,
        "only_in_target": only_in_target,
        "modified": modified,
    }
