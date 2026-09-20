"""Dependency-role classification and picker context.

Pure functions extracted from ``views.py`` so the GUI views and the MCP tool
layer share one implementation. No Django or request state.

Note: ``classify_dependency_roles`` issues one ``find_repo_class_versions`` and
one ``suggest_resource_dependencies`` call per (repo_class, version). Call it for
a single instance only -- fanning it out across a whole BOM is the pattern that
caused the DAG gateway timeouts fixed in commit e4de1e1.
"""


def classify_dependency_roles(
    client, repo_class_name: str, version: str, environment: str = None
):
    """Classify a RepoClassVersion's declared dependency roles by wiring kind.

    Returns ``(classified, matched)``:
    - ``classified``: ``{role_name: {"kind": "resource"|"repo_class",
      "compatible_class_name": str, "required": bool, "resource": dict|None}}``.
      A role absent from ``classified`` isn't declared by this class/version at
      all — callers should treat that as kind "instance" (a direct/raw pointer
      kept on the edge but not backed by any current role declaration; mirrors
      the "stale" handling below).
    - ``matched``: the resolved RepoClassVersion dict from
      ``find_repo_class_versions``, or ``None`` if the repo class/version
      couldn't be resolved at all (distinct from a resolved version that simply
      declares zero roles).

    Resource-based declarations (``suggest_resource_dependencies``) are
    authoritative over class-based ones (``find_repo_class_versions(...).dependencies``)
    per NERD0004 SPEC0008: a role declared by both is classified "resource".
    Discovering them requires a target ``environment`` (candidates are resolved
    against that environment's live state) — callers without one get repo_class-only
    classification, skipping the resource lookup rather than issuing a call that's
    guaranteed to fail environment resolution.
    """
    response = client.find_repo_class_versions(repo_class_name)
    matched = None
    if response.success and isinstance(response.data, list):
        for rcv in response.data:
            if rcv.get("version") == version:
                matched = rcv
                break

    dependencies = (matched or {}).get("dependencies") or {}

    # Resource-based dependency roles (NERD0004 SPEC0008) are NOT carried in the
    # class-name ``dependencies`` map — discover them via suggest_resource_dependencies
    # for the resolved RCV. Best-effort: a failing/absent call must not break
    # callers (guard on the method and on ``.success``).
    resource_by_role: dict = {}
    rcv_identifier = (matched or {}).get("identifier")
    suggest = getattr(client, "suggest_resource_dependencies", None)
    if environment and rcv_identifier and callable(suggest):
        try:
            sresp = suggest(environment, repo_class_version_id=rcv_identifier)
            if getattr(sresp, "success", False) and isinstance(sresp.data, dict):
                resource_by_role = sresp.data
        except Exception:  # pragma: no cover - defensive; never break callers
            resource_by_role = {}

    classified: dict = {}
    for role_name, meta in dependencies.items():
        if not isinstance(meta, dict):
            continue
        classified[role_name] = {
            "kind": "repo_class",
            "compatible_class_name": meta.get("repo_class_name", ""),
            "required": str(meta.get("required", "false")).lower() == "true",
            "resource": None,
        }

    # Resource-based roles. A role may be resource-only (not in the class-name
    # dependencies) or, when a role declared both, the resource requirement is
    # authoritative — so it augments the existing class-based entry.
    for role_name, rinfo in (resource_by_role or {}).items():
        if not isinstance(rinfo, dict):
            continue
        producer_class = rinfo.get("suggested_repo_class_name") or ""
        resource_meta = {
            "resource_definition": rinfo.get("resource_definition") or {},
            "version_spec": rinfo.get("version_spec"),
            "tag_selector": rinfo.get("tag_selector"),
            "suggested_repo_class_name": producer_class,
        }
        existing = classified.get(role_name)
        if existing is not None:
            existing.update(
                {
                    "kind": "resource",
                    "compatible_class_name": producer_class,
                    "required": existing["required"] or bool(rinfo.get("required")),
                    "resource": resource_meta,
                }
            )
        else:
            classified[role_name] = {
                "kind": "resource",
                "compatible_class_name": producer_class,
                "required": bool(rinfo.get("required")),
                "resource": resource_meta,
            }

    return classified, matched


def build_role_picker_context(
    client,
    draft,
    repo_class: str,
    version: str,
    selected_deps: dict = None,
    picker_id: str = "add",
    environment: str = None,
) -> dict:
    """Build the template context for partials/dependency_picker.html.

    Shared by the Add Item flow (no preselection) and the per-item Edit flow
    (selected_deps reflects the item's current dependencies dict). ``environment``
    is optional and currently unset by all callers: ChangeSetDrafts are
    environment-agnostic (portable across DeploymentSets), so there's no single
    environment to resolve resource-dependency candidates against here — this
    picker classifies by repo-class-declared roles only until that's designed.
    """
    selected_deps = selected_deps or {}

    classified, matched = classify_dependency_roles(
        client, repo_class, version, environment
    )

    in_draft_by_class: dict = {}
    for item in draft.content or []:
        cls = item.get("repo_class_name", "")
        in_draft_by_class.setdefault(cls, []).append(item.get("repo_instance_name", ""))

    def _normalize_selected(raw_sel) -> list:
        if raw_sel is None:
            return []
        if isinstance(raw_sel, list):
            return [str(s) for s in raw_sel if s]
        return [str(raw_sel)] if raw_sel else []

    roles = []
    known_roles = set(classified.keys())
    for role_name, info in classified.items():
        compatible_class = info["compatible_class_name"]
        candidates = (
            in_draft_by_class.get(compatible_class, []) if compatible_class else []
        )

        selected = _normalize_selected(selected_deps.get(role_name))

        if not selected or all(s in candidates for s in selected):
            initial_source = "draft"
        else:
            initial_source = "bom"

        roles.append(
            {
                "role": role_name,
                "compatible_class_name": compatible_class,
                "required": info["required"],
                "in_draft_candidates": candidates,
                "selected": selected,
                "initial_source": initial_source,
                "stale": False,
                "is_resource": info["kind"] == "resource",
                "resource": info["resource"],
            }
        )

    # Preserve any existing dependency whose role isn't declared by the resolved
    # version (or when the version couldn't be resolved at all). These are rendered
    # as editable rows so the instance's current wiring is shown, kept on save, and
    # re-pickable — rather than being silently dropped. compatible_class is unknown,
    # so the BOM candidate search lists all classes (api_dep_candidates handles an
    # empty repo_class). in_draft candidates are limited to the current selection so
    # values already in the draft render as checked; the rest are preserved via the
    # template's BOM hidden-input block.
    for role_name, raw_sel in selected_deps.items():
        if role_name in known_roles:
            continue
        selected = _normalize_selected(raw_sel)
        if not selected:
            continue
        # Render as a BOM-sourced row with no in-draft candidates so every current
        # value is emitted via the template's hidden-input path and preserved on
        # save. The user can still re-pick a different target from a DeploymentSet.
        roles.append(
            {
                "role": role_name,
                "compatible_class_name": "",
                "required": False,
                "in_draft_candidates": [],
                "selected": selected,
                "initial_source": "bom",
                "stale": True,
                "is_resource": False,
                "resource": None,
            }
        )

    return {
        "draft": draft,
        "repo_class": repo_class,
        "version": version,
        "roles": roles,
        "no_version": matched is None,
        "picker_id": picker_id,
    }


def parse_deps_from_post(post) -> dict:
    """Collect ``dep_<role>`` form fields into a role -> instance(s) map.

    A role with one selected instance stores as a string; two or more store as
    a list, matching the wire format produced by deploy_bom_creator. Empty,
    whitespace-only, and duplicate values are dropped.
    """
    deps = {}
    roles = {k[len("dep_") :] for k in post.keys() if k.startswith("dep_")}
    for role in roles:
        if not role:
            continue
        vals = [v.strip() for v in post.getlist(f"dep_{role}") if v and v.strip()]
        seen, uniq = set(), []
        for v in vals:
            if v not in seen:
                seen.add(v)
                uniq.append(v)
        if len(uniq) == 1:
            deps[role] = uniq[0]
        elif len(uniq) >= 2:
            deps[role] = uniq
    return deps


def preserve_required_deps(parsed: dict, existing: dict, classified: dict) -> dict:
    """Re-inject required dependency roles that a save would otherwise drop.

    Required roles must stay wired to keep a ChangeSet applyable, so the picker
    offers no remove control for them. This guards the save path against a
    crafted or stale POST: for every role the resolved version marks
    ``required``, if it's missing/empty in ``parsed`` but had a prior value in
    ``existing``, restore that prior value. Re-wiring a required role to a
    different target is untouched (the new value is present in ``parsed``), and a
    required role with no prior value is left as-is (nothing to restore).
    """
    for role, info in (classified or {}).items():
        if not (info or {}).get("required"):
            continue
        if parsed.get(role):
            continue
        prior = (existing or {}).get(role)
        if prior:
            parsed[role] = prior
    return parsed
