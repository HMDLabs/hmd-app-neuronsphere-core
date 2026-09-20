"""Views for NeuronSphere Deployment GUI."""
import copy
import json
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import urlencode
from django.views.decorators.http import require_GET, require_POST

from .decorators import audit_action, require_environment_access
from .services.authz import (
    user_has_deployment_set_access,
    user_has_environment_access,
)
from .models import (
    AuditLog,
    ChangeSetApplication,
    ChangeSetDraft,
    DeploymentSetPermission,
    UserEnvironmentPermission,
    UserPreference,
    sanitize_changeset_item,
)
from .services.auth import get_api_client_for_request
from .services.bom_query import (
    bom_facets,
    build_bom_dag_elements as _build_bom_dag_elements,
    filter_bom,
    sort_bom,
)
from .services.dependency_roles import (
    build_role_picker_context as _build_role_picker_context,
    classify_dependency_roles as _classify_dependency_roles,
    parse_deps_from_post as _parse_deps_from_post,
    preserve_required_deps as _preserve_required_deps,
)
from .services.environment_service import get_user_environments
from .services.instance_detail import (
    INSTANCE_METADATA_KEYS as _INSTANCE_METADATA_KEYS,
    build_instance_detail_sections as _build_instance_detail_sections,
)
from .services.pagination import (
    build_pagination,
    offset_for_page,
    parse_page,
)
from .services.repo_class_detail import (
    CAPABILITY_KINDS,
    build_capability_rows,
    build_repo_class_version_detail_sections as _build_repo_class_version_detail_sections,
    environments_for_deployment_set as _environments_for_deployment_set,
    search_repo_classes,
)
from .services.resource_query import (
    decode_resource_outputs,
    filter_resource_definitions as _filter_resource_definitions,
    query_resources,
)
from .services.telemetry_client import TelemetryClient

logger = logging.getLogger(__name__)


# ============== Dashboard Views ==============


@login_required
def dashboard(request):
    """Dashboard landing page shell.

    Environment status and recent deployments are fetched by the browser
    afterwards via lazy-loaded HTMX partials (see dashboard_env_status_partial
    and dashboard_recent_deployments_partial) so first paint isn't blocked on
    per-environment telemetry checks or the recent-deployments API call.
    """
    return render(request, "deployments/dashboard.html", {})


@login_required
@require_GET
def dashboard_env_status_partial(request):
    """HTMX partial for the (initial + auto-refreshing) environment status cards."""
    client = get_api_client_for_request(request)
    environments = get_user_environments(request.user, client)

    telemetry = TelemetryClient()
    env_statuses = telemetry.get_all_environment_statuses(environments)

    return render(
        request,
        "deployments/partials/dashboard_env_cards.html",
        {
            "environments": environments,
            "env_statuses": env_statuses,
        },
    )


# ============== BOM Views ==============


@login_required
def environment_list(request):
    """List available environments for user."""
    client = get_api_client_for_request(request)
    environments = get_user_environments(request.user, client)

    return render(
        request,
        "deployments/environment_list.html",
        {"environments": environments},
    )


@login_required
@require_environment_access("viewer")
@audit_action(AuditLog.Action.VIEW_BOM)
def bom_list(request, environment: str):
    """Display BOM for an environment."""
    client = get_api_client_for_request(request)
    response = client.get_deployment_bom(environment)

    if not response.success:
        if request.htmx:
            return render(
                request,
                "deployments/bom_table_error.html",
                {
                    "environment": environment,
                    "error": response.error,
                },
            )
        messages.error(request, f"Failed to load BOM: {response.error}")
        can_deploy = UserEnvironmentPermission.user_can_deploy(
            request.user, environment
        )
        empty_page = Paginator([], 50).get_page(1)
        return render(
            request,
            "deployments/bom_list.html",
            {
                "environment": environment,
                "bom": empty_page,
                "sort_by": "repo_instance_name",
                "sort_dir": "asc",
                "status_filter": "",
                "class_filter": "",
                "search": "",
                "filter_qs": "",
                "all_statuses": [],
                "all_classes": [],
                "can_deploy": can_deploy,
            },
        )

    bom_data = response.data if isinstance(response.data, list) else []

    # Sorting
    sort_by = request.GET.get("sort", "repo_instance_name")
    sort_dir = request.GET.get("dir", "asc")
    bom_data = sort_bom(bom_data, sort_by, sort_dir)

    # Filtering
    status_filter = request.GET.get("status") or ""
    class_filter = request.GET.get("repo_class") or ""
    search = request.GET.get("search", "").lower()
    bom_data = filter_bom(
        bom_data, search=search, status=status_filter, repo_class=class_filter
    )

    # Pagination
    try:
        prefs = request.user.preferences
        per_page = prefs.items_per_page
    except UserPreference.DoesNotExist:
        per_page = 50

    paginator = Paginator(bom_data, per_page)
    page = request.GET.get("page", 1)
    bom_page = paginator.get_page(page)

    # Get unique values for filters (from original unfiltered data)
    original_data = response.data if isinstance(response.data, list) else []
    facets = bom_facets(original_data)
    all_statuses = facets["statuses"]
    all_classes = facets["repo_classes"]

    # Check user permissions
    can_deploy = UserEnvironmentPermission.user_can_deploy(request.user, environment)

    # Encoded filter params shared by pagination and sort links
    filter_qs = urlencode(
        {"search": search, "status": status_filter, "repo_class": class_filter}
    )

    context = {
        "environment": environment,
        "bom": bom_page,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
        "status_filter": status_filter,
        "class_filter": class_filter,
        "search": search,
        "filter_qs": filter_qs,
        "all_statuses": all_statuses,
        "all_classes": all_classes,
        "can_deploy": can_deploy,
    }

    # Return partial for HTMX requests
    if request.htmx:
        return render(request, "deployments/bom_table.html", context)

    return render(request, "deployments/bom_list.html", context)


@login_required
@require_GET
def bom_table(request, environment: str):
    """HTMX partial for BOM table refresh."""
    # Pass environment as a keyword arg: bom_list is wrapped by
    # @require_environment_access, whose decorator resolves the environment from
    # kwargs/POST/GET. A positional arg lands in *args and is invisible to it, which
    # made every HTMX table refresh 403 with "Environment not specified".
    return bom_list(request, environment=environment)


@login_required
@require_POST
@require_environment_access("deploy")
@audit_action(AuditLog.Action.CREATE_CHANGESET)
def bom_create_changeset(request, environment: str):
    """Create a new ChangeSet draft pre-populated from selected BOM instances.

    Mirrors ``environment_compare_create_changeset`` but sources items from a
    single environment's BOM rather than a diff. Each selected instance is
    copied verbatim (name, class, version, deployment_id, configuration,
    dependencies) so the resulting draft is ready to edit on the draft page.
    """
    name = (request.POST.get("name") or "").strip()
    selected = request.POST.getlist("selected")

    if not name:
        messages.error(request, "Provide a name for the new ChangeSet.")
        return redirect("deployments:bom_list", environment=environment)
    if not selected:
        messages.error(request, "Select at least one instance to include.")
        return redirect("deployments:bom_list", environment=environment)

    client = get_api_client_for_request(request)
    response = client.get_deployment_bom(environment)
    if not response.success:
        messages.error(
            request, response.error or f"Failed to load BOM for {environment}."
        )
        return redirect("deployments:bom_list", environment=environment)

    bom_data = response.data if isinstance(response.data, list) else []
    selected_set = set(selected)
    selected_items = [
        item for item in bom_data if item.get("repo_instance_name") in selected_set
    ]

    if not selected_items:
        messages.error(
            request, "None of the selected instances were found in the current BOM."
        )
        return redirect("deployments:bom_list", environment=environment)

    draft = ChangeSetDraft.objects.create(
        user=request.user,
        name=name,
        content=[sanitize_changeset_item(item) for item in selected_items],
        status=ChangeSetDraft.Status.DRAFT,
    )

    messages.success(
        request,
        f"Created ChangeSet '{draft.name}' with {len(selected_items)} instance(s) from {environment}.",
    )
    return redirect("deployments:changeset_draft", draft_id=draft.pk)


@login_required
@require_GET
@require_environment_access("viewer")
def bom_dag_data(request, environment: str):
    """Return BOM dependency graph as JSON for Cytoscape.js.

    The assembled {nodes, edges} JSON only changes when the BOM changes, so it's
    cached the same way the BOM itself is (same TTL, invalidated alongside it by
    ``invalidate_bom_cache`` on ChangeSet apply) — this avoids re-fetching and
    re-assembling the BOM on every DAG-tab load.
    """
    client = get_api_client_for_request(request)
    cache_key = f"bom_dag:{environment}"
    cached = cache.get(cache_key)
    if cached is not None:
        return JsonResponse({"elements": cached})

    response = client.get_deployment_bom(environment)

    if not response.success:
        return JsonResponse({"error": response.error}, status=502)

    bom_data = response.data if isinstance(response.data, list) else []

    elements = _build_bom_dag_elements(bom_data)
    cache.set(cache_key, elements, settings.DEPLOYMENT_BOM_CACHE_TTL)
    return JsonResponse({"elements": elements})


@login_required
@require_environment_access("viewer")
@audit_action(AuditLog.Action.VIEW_INSTANCE)
def instance_detail(request, environment: str, instance_name: str):
    """Show detailed instance information."""
    client = get_api_client_for_request(request)

    # Get instance config
    config_response = client.get_deployment_config(environment, instance_name)
    config = config_response.data if config_response.success else {}

    # Get deployment history. The service wraps the records in
    # {"repo_instance": {...}, "history": [...]}, so unwrap the list here.
    history_response = client.get_deployment_history(environment, instance_name)
    history_data = history_response.data if history_response.success else {}
    if isinstance(history_data, dict):
        history_list = history_data.get("history", [])
    else:
        history_list = history_data or []

    sections = _build_instance_detail_sections(
        client, config, history_list, environment
    )

    context = {
        "environment": environment,
        "instance_name": instance_name,
        "config": config,
        "details": sections["details"],
        "configuration": sections["configuration"],
        "dependency_rows": sections["dependency_rows"],
        "history": history_list,
        "config_error": config_response.error if not config_response.success else None,
        "history_error": history_response.error
        if not history_response.success
        else None,
        "can_deploy": UserEnvironmentPermission.user_can_deploy(
            request.user, environment
        ),
    }

    if request.htmx:
        return render(
            request, "deployments/partials/instance_detail_panel.html", context
        )

    return render(request, "deployments/instance_detail.html", context)


# ============== ChangeSet Views ==============


@login_required
def changeset_list(request):
    """List user's ChangeSet drafts."""
    drafts = ChangeSetDraft.objects.filter(user=request.user).order_by("-updated_at")

    return render(
        request,
        "deployments/changeset_list.html",
        {"drafts": drafts},
    )


@login_required
def changeset_create(request):
    """Create a new ChangeSet draft. Only a name is required;
    DeploymentSet is chosen at apply time."""
    if request.method == "POST":
        name = request.POST.get("name", "").strip()

        if not name:
            messages.error(request, "ChangeSet name is required")
            return redirect("deployments:changeset_create")

        draft, created = ChangeSetDraft.objects.update_or_create(
            user=request.user,
            name=name,
            defaults={"content": []},
        )

        action = "created" if created else "updated"
        messages.success(request, f"ChangeSet '{name}' {action}")

        copy_instance = request.POST.get("copy_instance", "")
        if copy_instance:
            return redirect(
                f"{draft.pk}/?copy_instance={copy_instance}"
                f"&copy_class={request.POST.get('copy_class', '')}"
                f"&copy_version={request.POST.get('copy_version', '')}"
                f"&copy_deployment_id={request.POST.get('copy_deployment_id', '')}"
            )
        return redirect("deployments:changeset_draft", draft_id=draft.pk)

    copy_params = {}
    if request.GET.get("copy_instance"):
        copy_params = {
            "copy_instance": request.GET.get("copy_instance", ""),
            "copy_class": request.GET.get("copy_class", ""),
            "copy_version": request.GET.get("copy_version", ""),
            "copy_deployment_id": request.GET.get("copy_deployment_id", ""),
        }

    return render(
        request,
        "deployments/changeset_create.html",
        {"copy_params": copy_params},
    )


@login_required
def changeset_draft(request, draft_id: int):
    """View a specific ChangeSet draft for editing."""
    draft = get_object_or_404(ChangeSetDraft, pk=draft_id, user=request.user)

    # Check for copy-from-BOM pre-population params
    copy_params = {}
    if request.GET.get("copy_instance"):
        copy_params = {
            "copy_instance": request.GET.get("copy_instance", ""),
            "copy_class": request.GET.get("copy_class", ""),
            "copy_version": request.GET.get("copy_version", ""),
            "copy_deployment_id": request.GET.get("copy_deployment_id", ""),
        }

    return render(
        request,
        "deployments/changeset_draft.html",
        {"draft": draft, "copy_params": copy_params},
    )


@login_required
@require_POST
def changeset_add_item(request, draft_id: int):
    """Add item to ChangeSet draft (HTMX).

    Dependencies are submitted as ``dep_<role>`` form fields, one per declared
    role. Empty values are dropped.
    """
    try:
        draft = ChangeSetDraft.objects.get(pk=draft_id, user=request.user)
    except ChangeSetDraft.DoesNotExist:
        return HttpResponse("No draft found", status=404)

    instance_name = request.POST.get("instance_name", "").strip()
    repo_class = request.POST.get("repo_class", "").strip()
    version = request.POST.get("version", "").strip()
    deployment_id = request.POST.get("deployment_id", "aaa").strip() or "aaa"
    config_json = request.POST.get("instance_configuration", "{}").strip()

    if not all([instance_name, repo_class, version]):
        return HttpResponse(
            "Instance name, repo class, and version are required", status=400
        )

    try:
        configuration = json.loads(config_json) if config_json else {}
    except json.JSONDecodeError:
        return HttpResponse("Invalid configuration JSON", status=400)

    dependencies = _parse_deps_from_post(request.POST)

    item = {
        "repo_instance_name": instance_name,
        "repo_class_name": repo_class,
        "repo_class_version": version,
        "deployment_id": deployment_id,
        "instance_configuration": configuration,
        "dependencies": dependencies,
    }

    if draft.content is None:
        draft.content = []
    draft.content.append(item)
    draft.save()

    # Return the item list plus out-of-band header refresh so the Apply button,
    # Review link, and change count react to draft.content without a page reload.
    return render(
        request,
        "deployments/partials/changeset_items_response.html",
        {"draft": draft},
    )


@login_required
@require_POST
def changeset_remove_item(request, draft_id: int, index: int):
    """Remove item from ChangeSet draft (HTMX)."""
    try:
        draft = ChangeSetDraft.objects.get(pk=draft_id, user=request.user)
    except ChangeSetDraft.DoesNotExist:
        return HttpResponse("No draft found", status=404)

    if draft.content and 0 <= index < len(draft.content):
        draft.content.pop(index)
        draft.save()

    # OOB header refresh so removing the last item hides the Apply/Review actions.
    return render(
        request,
        "deployments/partials/changeset_items_response.html",
        {"draft": draft},
    )


@login_required
def changeset_review(request, draft_id: int):
    """Review ChangeSet before applying."""
    draft = get_object_or_404(ChangeSetDraft, pk=draft_id, user=request.user)

    if draft.status == ChangeSetDraft.Status.DRAFT:
        draft.status = ChangeSetDraft.Status.IN_REVIEW
        draft.save(update_fields=["status", "updated_at"])

    return render(
        request,
        "deployments/changeset_review.html",
        {"draft": draft},
    )


@login_required
@require_GET
@require_environment_access("viewer", when_missing="defer", response="partial")
def changeset_bom_impact(request, draft_id: int):
    """HTMX partial: compute and render BOM impact diff for a ChangeSet draft.

    Takes ?environment=<env> to select which environment's BOM to diff against.
    Without one, renders a hint to pick an environment.
    """
    draft = get_object_or_404(ChangeSetDraft, pk=draft_id, user=request.user)
    environment = request.GET.get("environment", "").strip()

    if not environment:
        return render(
            request,
            "deployments/partials/bom_impact.html",
            {
                "impacts": [],
                "summary": {"new": 0, "modified": 0, "unchanged": 0},
                "bom_available": False,
                "environment": "",
            },
        )

    from .services.bom_diff import compute_bom_impact, summarize_impact

    client = get_api_client_for_request(request)
    bom_response = client.get_deployment_bom(environment)

    current_bom_dict = {}
    if bom_response.success and bom_response.data:
        current_bom_dict = {
            item["repo_instance_name"]: item for item in bom_response.data
        }

    impacts = compute_bom_impact(draft.sanitized_content, current_bom_dict)
    summary = summarize_impact(impacts)

    return render(
        request,
        "deployments/partials/bom_impact.html",
        {
            "impacts": impacts,
            "summary": summary,
            "bom_available": bom_response.success,
            "environment": environment,
        },
    )


@login_required
@require_GET
def changeset_validate(request, draft_id: int):
    """HTMX partial: validate ChangeSet via deployment API and render results."""
    draft = get_object_or_404(ChangeSetDraft, pk=draft_id, user=request.user)

    # Client-side validation: check for empty changeset
    errors = []
    warnings = []

    if not draft.content:
        errors.append(
            {
                "type": "empty_changeset",
                "instance": "",
                "message": "ChangeSet has no changes to apply.",
            }
        )

    # Check for duplicate instance names within the changeset
    instance_names = [
        item.get("repo_instance_name", "") for item in (draft.content or [])
    ]
    seen = set()
    for name in instance_names:
        if name in seen:
            errors.append(
                {
                    "type": "duplicate_instance",
                    "instance": name,
                    "message": f"Instance '{name}' appears multiple times in the ChangeSet.",
                }
            )
        seen.add(name)

    # Check for missing required fields
    for item in draft.content or []:
        if not item.get("repo_instance_name"):
            errors.append(
                {
                    "type": "missing_field",
                    "instance": "",
                    "message": "An item is missing the instance name.",
                }
            )
        if not item.get("repo_class_name"):
            errors.append(
                {
                    "type": "missing_field",
                    "instance": item.get("repo_instance_name", "unknown"),
                    "message": f"Instance '{item.get('repo_instance_name', 'unknown')}' is missing the repo class.",
                }
            )
        if not item.get("repo_class_version"):
            errors.append(
                {
                    "type": "missing_field",
                    "instance": item.get("repo_instance_name", "unknown"),
                    "message": f"Instance '{item.get('repo_instance_name', 'unknown')}' is missing the version.",
                }
            )

    # Server-side validation via API (only if client-side passes)
    api_valid = True
    api_errors = []
    api_warnings = []
    api_available = True

    if not errors and draft.content:
        client = get_api_client_for_request(request)
        response = client.validate_changeset(draft.sanitized_content)
        if response.success and response.data:
            api_valid = response.data.get("valid", True)
            api_errors = response.data.get("errors", [])
            api_warnings = response.data.get("warnings", [])
        elif not response.success:
            # API endpoint may not exist yet — treat as unavailable
            api_available = False
            if response.status_code != 404:
                warnings.append(
                    {
                        "type": "validation_unavailable",
                        "instance": "",
                        "message": "Server-side validation is currently unavailable. Proceed with caution.",
                    }
                )

    all_errors = errors + api_errors
    all_warnings = warnings + api_warnings
    is_valid = len(all_errors) == 0 and api_valid

    return render(
        request,
        "deployments/partials/changeset_validation.html",
        {
            "is_valid": is_valid,
            "errors": all_errors,
            "warnings": all_warnings,
            "api_available": api_available,
        },
    )


@login_required
@require_POST
@audit_action(AuditLog.Action.CLONE_CHANGESET)
def changeset_clone(request, draft_id: int):
    """Clone a ChangeSet draft. Plain content copy with status=DRAFT — no
    BOM-based instance name remapping."""
    source = get_object_or_404(ChangeSetDraft, pk=draft_id, user=request.user)

    base_name = f"{source.name} (copy)"
    name = base_name
    suffix = 2
    while ChangeSetDraft.objects.filter(user=request.user, name=name).exists():
        name = f"{base_name} {suffix}"
        suffix += 1

    clone = ChangeSetDraft.objects.create(
        user=request.user,
        name=name,
        content=[sanitize_changeset_item(item) for item in (source.content or [])],
        status=ChangeSetDraft.Status.DRAFT,
    )

    messages.success(request, f"ChangeSet cloned as '{clone.name}'")
    return redirect("deployments:changeset_draft", draft_id=clone.pk)


@login_required
@require_POST
@audit_action(AuditLog.Action.REJECT_CHANGESET)
def changeset_reject(request, draft_id: int):
    """Reject a ChangeSet draft with a reason."""
    draft = get_object_or_404(ChangeSetDraft, pk=draft_id, user=request.user)
    reason = request.POST.get("rejection_reason", "").strip()

    draft.status = ChangeSetDraft.Status.REJECTED
    draft.rejection_reason = reason
    draft.save(update_fields=["status", "rejection_reason", "updated_at"])

    messages.info(request, f"ChangeSet '{draft.name}' has been rejected.")
    return redirect("deployments:changeset_list")


@login_required
@require_POST
@audit_action(AuditLog.Action.REOPEN_CHANGESET)
def changeset_reopen(request, draft_id: int):
    """Reopen a rejected ChangeSet draft for editing."""
    draft = get_object_or_404(ChangeSetDraft, pk=draft_id, user=request.user)

    if draft.status != ChangeSetDraft.Status.REJECTED:
        messages.error(request, "Only rejected ChangeSets can be reopened.")
        return redirect("deployments:changeset_draft", draft_id=draft_id)

    draft.status = ChangeSetDraft.Status.DRAFT
    draft.rejection_reason = ""
    draft.save(update_fields=["status", "rejection_reason", "updated_at"])

    messages.success(
        request, f"ChangeSet '{draft.name}' has been reopened for editing."
    )
    return redirect("deployments:changeset_draft", draft_id=draft_id)


# ============== ChangeSet Backward-Compat Redirects ==============


@login_required
def changeset_draft_redirect(request):
    """Redirect old /changeset/draft/ URL to ID-based URL."""
    try:
        draft = ChangeSetDraft.objects.filter(user=request.user).latest("updated_at")
        return redirect("deployments:changeset_draft", draft_id=draft.pk)
    except ChangeSetDraft.DoesNotExist:
        messages.info(request, "No draft found. Create a new ChangeSet.")
        return redirect("deployments:changeset_create")


@login_required
def changeset_review_redirect(request):
    """Redirect old /changeset/review/ URL to ID-based URL."""
    try:
        draft = ChangeSetDraft.objects.filter(user=request.user).latest("updated_at")
        return redirect("deployments:changeset_review", draft_id=draft.pk)
    except ChangeSetDraft.DoesNotExist:
        messages.info(request, "No draft found. Create a new ChangeSet.")
        return redirect("deployments:changeset_create")


# ============== Environment Comparison ==============


@login_required
def environment_compare(request):
    """Compare two environments side-by-side.

    GET with ``?from=<env>&to=<env>`` renders the categorized diff.
    Without query params, renders the env-pair selection form.
    """
    client = get_api_client_for_request(request)
    environments = get_user_environments(request.user, client)

    from_env = (request.GET.get("from") or "").strip()
    to_env = (request.GET.get("to") or "").strip()

    diff = None
    error = None

    if from_env and to_env:
        if not user_has_environment_access(request.user, from_env):
            error = (
                f"You don't have view permission for source environment '{from_env}'."
            )
        elif not user_has_environment_access(request.user, to_env):
            error = f"You don't have view permission for target environment '{to_env}'."
        else:
            response = client.compare_environments(from_env=from_env, to_env=to_env)
            if not response.success:
                error = response.error or "Failed to compare environments."
            else:
                from .services.bom_diff import compute_environment_diff

                diff = compute_environment_diff(response.data or {})

    return render(
        request,
        "deployments/environment_compare.html",
        {
            "environments": environments,
            "from_env": from_env,
            "to_env": to_env,
            "diff": diff,
            "error": error,
        },
    )


@login_required
@require_POST
@require_environment_access("viewer", param=("from_env", "to_env"))
@audit_action(AuditLog.Action.CREATE_CHANGESET)
def environment_compare_create_changeset(request):
    """Create a ChangeSet draft from selected diff items.

    Expects POST fields:
        from_env, to_env, name, selected[]: instance names to include.

    The generated ChangeSet is deployment-set-agnostic — the user picks a
    DeploymentSet at apply time.
    """
    from_env = (request.POST.get("from_env") or "").strip()
    to_env = (request.POST.get("to_env") or "").strip()
    name = (request.POST.get("name") or "").strip()
    selected = request.POST.getlist("selected")

    if not (from_env and to_env and name):
        messages.error(
            request, "Source, target, and name are required to generate a ChangeSet."
        )
        return redirect(
            f"{request.path.rsplit('/create-changeset/', 1)[0]}/?from={from_env}&to={to_env}"
        )

    client = get_api_client_for_request(request)
    response = client.compare_environments(from_env=from_env, to_env=to_env)
    if not response.success:
        messages.error(request, response.error or "Failed to compare environments.")
        return redirect("deployments:environment_compare")

    from .services.bom_diff import compute_environment_diff

    diff = compute_environment_diff(response.data or {})

    selected_set = set(selected)
    selected_items = [
        i
        for i in (diff["only_in_source"] + [m["source"] for m in diff["modified"]])
        if i.get("repo_instance_name") in selected_set
    ]

    if not selected_items:
        messages.error(request, "Select at least one item to include in the ChangeSet.")
        return redirect(
            f"{request.build_absolute_uri('?').rstrip('?')}?from={from_env}&to={to_env}"
        )

    draft = ChangeSetDraft.objects.create(
        user=request.user,
        name=name,
        content=[sanitize_changeset_item(item) for item in selected_items],
        status=ChangeSetDraft.Status.DRAFT,
    )

    messages.success(
        request,
        f"Generated ChangeSet '{draft.name}' with {len(selected_items)} item(s) from {from_env} diff.",
    )
    return redirect("deployments:changeset_draft", draft_id=draft.pk)


@login_required
@require_GET
@require_environment_access("viewer", when_missing="defer", response="partial")
def api_search_instances_html(request, draft_id: int):
    """HTMX partial: search BOM instances in a chosen environment.

    Reads ``?environment=<env>&q=<query>``. Environment is required.
    """
    draft = get_object_or_404(ChangeSetDraft, pk=draft_id, user=request.user)
    query = request.GET.get("q", "").strip()
    environment = request.GET.get("environment", "").strip()

    if not environment or not query or len(query) < 2:
        return HttpResponse("")

    client = get_api_client_for_request(request)
    response = client.get_deployment_bom(environment)

    results = []
    if response.success:
        results = [
            item
            for item in (response.data or [])
            if query.lower() in item.get("repo_instance_name", "").lower()
            or query.lower() in item.get("repo_class_name", "").lower()
        ][:20]

    return render(
        request,
        "deployments/partials/instance_search_results.html",
        {"results": results, "draft": draft, "environment": environment},
    )


@login_required
@require_GET
def api_repo_class_roles(request, draft_id: int, repo_class: str, version: str):
    """HTMX partial: dependency picker rendered for a repo class + version.

    Path-param form, kept for backwards compatibility. New flows should use
    ``api_repo_class_roles_query`` which takes the values via query string.
    """
    draft = get_object_or_404(ChangeSetDraft, pk=draft_id, user=request.user)
    client = get_api_client_for_request(request)
    context = _build_role_picker_context(client, draft, repo_class, version)
    context["environments"] = get_user_environments(request.user, client)
    return render(request, "deployments/partials/dependency_picker.html", context)


@login_required
@require_GET
def api_repo_class_roles_query(request, draft_id: int):
    """HTMX partial: dependency picker via ``?repo_class=&version=`` query.

    Used by the Add Item form's version dropdown — fires on change with both
    values included, so the URL stays static and no Alpine URL rebinding is
    needed.
    """
    draft = get_object_or_404(ChangeSetDraft, pk=draft_id, user=request.user)
    repo_class = request.GET.get("repo_class", "").strip()
    version = request.GET.get("version", "").strip()
    if not repo_class or not version:
        return HttpResponse("")

    selected_deps = {}
    raw = request.GET.get("selected_deps", "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                selected_deps = parsed
        except json.JSONDecodeError:
            pass

    client = get_api_client_for_request(request)
    context = _build_role_picker_context(
        client, draft, repo_class, version, selected_deps=selected_deps
    )
    context["environments"] = get_user_environments(request.user, client)
    return render(request, "deployments/partials/dependency_picker.html", context)


@login_required
@require_GET
def api_repo_class_options(request):
    """HTMX partial: ``<option>`` list of all repo classes for the class dropdown."""
    client = get_api_client_for_request(request)
    response = client.list_repo_classes()
    repo_classes = []
    if response.success and isinstance(response.data, list):
        repo_classes = sorted(
            response.data, key=lambda rc: rc.get("repo_class_name", "")
        )
    return render(
        request,
        "deployments/partials/repo_class_options.html",
        {"repo_classes": repo_classes},
    )


def _parse_item_index(raw):
    """Parse ``?item_index=`` into a non-negative int, or None when absent/bad.

    None means "the page-level picker" (the Add Instance form), which uses the
    unsuffixed element ids.
    """
    try:
        index = int(raw)
    except (TypeError, ValueError):
        return None
    return index if index >= 0 else None


def version_results_id(item_index=None):
    """Element id of the version picker's results container."""
    return "version-results" if item_index is None else f"version-results-{item_index}"


def version_input_id(item_index=None):
    """Element id of the hidden input carrying the picked version."""
    return "version_input" if item_index is None else f"version_input_{item_index}"


@login_required
@require_GET
def api_repo_class_versions_options(request):
    """HTMX partial: a searchable, paginated list of versions for a repo class.

    Reads ``?repo_class=<name>``, a version filter, and ``?page=``. Backed by the
    paged microservice endpoint so only one page of versions is fetched/rendered
    (and no per-version dependency resolution).

    The filter is accepted as ``?q=`` or ``?version_q=``: htmx submits a search
    input under its own ``name``, and the ChangeSet "Add Instance" box is named
    ``version_q``, so reading only ``q`` silently ignored everything the user
    typed there.

    ``?item_index=`` scopes the rendered element ids to one ChangeSet item, so
    several "Edit instance" panels can hold independent pickers on one page. The
    ids are *derived* from the index rather than taken from the query string, so
    nothing caller-supplied is reflected into the markup.
    """
    repo_class = request.GET.get("repo_class", "").strip()
    q = (request.GET.get("q") or request.GET.get("version_q") or "").strip()
    item_index = _parse_item_index(request.GET.get("item_index"))
    versions = []
    pagination = None
    if repo_class:
        limit = 50
        page = parse_page(request.GET.get("page"))
        offset = offset_for_page(page, limit)
        client = get_api_client_for_request(request)
        response = client.find_repo_class_versions_page(
            repo_class, q=q, limit=limit, offset=offset
        )
        if response.success and isinstance(response.data, dict):
            data = response.data
            versions = [
                v.get("version") for v in data.get("items", []) if v.get("version")
            ]
            pagination = build_pagination(data.get("total", 0), limit, offset, page)
    return render(
        request,
        "deployments/partials/repo_class_versions_results.html",
        {
            "versions": versions,
            "repo_class": repo_class,
            "q": q,
            "pagination": pagination,
            "item_index": item_index,
            "results_id": version_results_id(item_index),
            "input_id": version_input_id(item_index),
        },
    )


@login_required
@require_GET
def changeset_edit_item_deps(request, draft_id: int, index: int):
    """HTMX partial: dependency picker pre-populated with an existing item's deps."""
    draft = get_object_or_404(ChangeSetDraft, pk=draft_id, user=request.user)
    if not draft.content or index < 0 or index >= len(draft.content):
        return HttpResponse("Item not found", status=404)
    item = draft.content[index]
    client = get_api_client_for_request(request)
    context = _build_role_picker_context(
        client,
        draft,
        item.get("repo_class_name", ""),
        item.get("repo_class_version", ""),
        selected_deps=item.get("dependencies") or {},
        picker_id=f"edit-{index}",
    )
    context["environments"] = get_user_environments(request.user, client)
    return render(request, "deployments/partials/dependency_picker.html", context)


@login_required
@require_POST
def changeset_set_item_deps(request, draft_id: int, index: int):
    """HTMX: save updated dependencies for an existing ChangeSet item."""
    try:
        draft = ChangeSetDraft.objects.get(pk=draft_id, user=request.user)
    except ChangeSetDraft.DoesNotExist:
        return HttpResponse("No draft found", status=404)
    if not draft.content or index < 0 or index >= len(draft.content):
        return HttpResponse("Item not found", status=404)

    item = draft.content[index]
    existing = item.get("dependencies") or {}
    parsed = _parse_deps_from_post(request.POST)

    # Required dependencies must not be removable — the picker offers no remove
    # control for them, and this guards the save path against a crafted or stale
    # POST that would drop one. Classify the item's declared roles and re-inject
    # any required role that would end up empty (re-wiring to a new target is
    # untouched). Classification failures degrade to "no restore" rather than
    # blocking the save.
    client = get_api_client_for_request(request)
    classified, _ = _classify_dependency_roles(
        client,
        item.get("repo_class_name", ""),
        item.get("repo_class_version", ""),
    )
    parsed = _preserve_required_deps(parsed, existing, classified)

    item["dependencies"] = parsed
    draft.save()

    return render(
        request,
        "deployments/partials/changeset_items.html",
        {"draft": draft},
    )


@login_required
@require_GET
def changeset_edit_item_instance(request, draft_id: int, index: int):
    """HTMX partial: instance editor (version, deployment_id, configuration).

    Renders with no API round trip. The version list is fetched separately by the
    picker inside the partial (``api_repo_class_versions_options``, one page at a
    time), so opening the panel no longer blocks on pulling every version of the
    repo class -- each of which the microservice would also resolve dependencies
    for, which this editor never uses.
    """
    draft = get_object_or_404(ChangeSetDraft, pk=draft_id, user=request.user)
    if not draft.content or index < 0 or index >= len(draft.content):
        return HttpResponse("Item not found", status=404)
    item = draft.content[index]

    configuration = item.get("instance_configuration") or {}
    configuration_json = json.dumps(configuration, indent=2) if configuration else ""

    return render(
        request,
        "deployments/partials/instance_editor.html",
        {
            "draft": draft,
            "item": item,
            "index": index,
            "configuration_json": configuration_json,
            "results_id": version_results_id(index),
            "input_id": version_input_id(index),
        },
    )


@login_required
@require_POST
def changeset_set_item_instance(request, draft_id: int, index: int):
    """HTMX: save edits to an existing ChangeSet item's instance fields."""
    try:
        draft = ChangeSetDraft.objects.get(pk=draft_id, user=request.user)
    except ChangeSetDraft.DoesNotExist:
        return HttpResponse("No draft found", status=404)
    if not draft.content or index < 0 or index >= len(draft.content):
        return HttpResponse("Item not found", status=404)

    version = request.POST.get("version", "").strip()
    deployment_id = request.POST.get("deployment_id", "").strip() or "aaa"
    config_json = request.POST.get("instance_configuration", "").strip()

    if not version:
        return HttpResponse("Version is required", status=400)

    try:
        configuration = json.loads(config_json) if config_json else {}
    except json.JSONDecodeError:
        return HttpResponse("Invalid configuration JSON", status=400)

    item = draft.content[index]
    item["repo_class_version"] = version
    item["deployment_id"] = deployment_id
    item["instance_configuration"] = configuration
    draft.save()

    return render(
        request,
        "deployments/partials/changeset_items.html",
        {"draft": draft},
    )


@login_required
@require_GET
@require_environment_access("viewer", when_missing="defer", response="partial")
def api_dep_candidates(request, draft_id: int):
    """HTMX partial: list candidate instances for a dep role from an environment.

    Class-based roles: ``?environment=&repo_class=&role=`` filters the environment
    BOM by repo class. Resource-based roles: when resource selectors
    (``resource_namespace`` + ``resource_definition_name`` + ``version``, plus
    optional ``version_spec``/``tags``) are present, candidates are the instances
    that satisfy that resource type in the environment, resolved via
    ``suggest_resource_dependencies`` (inheritance- and tag-aware)."""
    draft = get_object_or_404(ChangeSetDraft, pk=draft_id, user=request.user)
    environment = request.GET.get("environment", "").strip()
    repo_class = request.GET.get("repo_class", "").strip()
    role = request.GET.get("role", "").strip()
    resource_namespace = request.GET.get("resource_namespace", "").strip()
    resource_definition_name = request.GET.get("resource_definition_name", "").strip()
    version = request.GET.get("version", "").strip()

    if not environment or not role:
        return HttpResponse("")

    client = get_api_client_for_request(request)
    candidates = []

    if resource_namespace and resource_definition_name and version:
        # Resource-based role — satisfying instances in the environment.
        response = client.suggest_resource_dependencies(
            environment,
            resource_namespace=resource_namespace,
            resource_definition_name=resource_definition_name,
            version=version,
            version_spec=request.GET.get("version_spec", "").strip() or None,
            tags=request.GET.get("tags", "").strip() or None,
        )
        if response.success and isinstance(response.data, dict):
            for cand in response.data.get("candidates", []):
                name = cand.get("name") if isinstance(cand, dict) else None
                if name:
                    candidates.append(name)
            candidates = sorted(set(candidates))
    else:
        bom_response = client.get_deployment_bom(environment)
        if bom_response.success and isinstance(bom_response.data, list):
            for item in bom_response.data:
                if not repo_class or item.get("repo_class_name") == repo_class:
                    candidates.append(item.get("repo_instance_name", ""))
            candidates = sorted(set(c for c in candidates if c))

    return render(
        request,
        "deployments/partials/dep_candidates.html",
        {
            "role": role,
            "environment": environment,
            "candidates": candidates,
        },
    )


# ============== Repo Class Views ==============


@login_required
def repo_class_list(request):
    """Browse available repo classes."""
    client = get_api_client_for_request(request)
    response = client.list_repo_classes()

    repo_classes = []
    error = None
    search = request.GET.get("search", "").strip().lower()

    if response.success and response.data:
        repo_classes = response.data if isinstance(response.data, list) else []
        repo_classes = search_repo_classes(repo_classes, search)
    elif not response.success:
        error = response.error

    # Pagination
    paginator = Paginator(repo_classes, 50)
    page = request.GET.get("page", 1)
    repo_classes_page = paginator.get_page(page)

    return render(
        request,
        "deployments/repo_class_list.html",
        {
            "repo_classes": repo_classes_page,
            "search": search,
            "error": error,
            "kind_options": CAPABILITY_KINDS,
        },
    )


@login_required
@require_GET
def capability_search(request):
    """HTMX partial: "which repo class can do X?" over the discovery catalog.

    One ``search_discovery`` call (hmd-ms-deployment NERD0013) per request,
    and none when the form is empty -- the page must not fetch the whole
    catalog just because it loaded. A catalog read, so ``login_required`` and
    nothing environment-scoped. The rows come from ``build_capability_rows``,
    which the MCP ``search_capabilities`` tool shares.
    """
    q = request.GET.get("q", "").strip()
    kind = request.GET.get("kind", "").strip()
    try:
        page = max(int(request.GET.get("page", 1)), 1)
    except (TypeError, ValueError):
        page = 1
    page_size = 50

    context = {
        "q": q,
        "kind": kind,
        "page": page,
        "rows": [],
        "summary_only": [],
        "total": 0,
        "has_previous": page > 1,
        "has_next": False,
        "error": None,
        "searched": bool(q or kind),
    }

    if kind and kind not in CAPABILITY_KINDS:
        context["error"] = (
            f"Unknown capability kind '{kind}'. "
            f"Choose one of: {', '.join(CAPABILITY_KINDS)}."
        )
    elif q or kind:
        client = get_api_client_for_request(request)
        response = client.search_discovery(
            q=q, kind=kind, limit=page_size, offset=(page - 1) * page_size
        )
        if response.success and isinstance(response.data, dict):
            data = response.data
            context["rows"] = build_capability_rows(data)
            # Classes the query hit on summary/entry point alone -- worth
            # showing, since the user asked "what can do X" and these can.
            context["summary_only"] = [
                {
                    "repo_class_name": item.get("repo_class_name") or "",
                    "version": item.get("version") or "",
                    "summary": item.get("summary") or "",
                }
                for item in (data.get("items") or [])
                if isinstance(item, dict) and not item.get("capabilities")
            ]
            total = int(data.get("total") or 0)
            context["total"] = total
            context["has_next"] = page * page_size < total
        else:
            context["error"] = response.error or "Search failed."

    return render(request, "deployments/partials/capability_results.html", context)


@login_required
def repo_class_detail(request, repo_class_name: str):
    """Show all versions for a specific repo class."""
    client = get_api_client_for_request(request)
    response = client.find_repo_class_versions(repo_class_name)

    versions = []
    error = None

    if response.success and response.data:
        versions = response.data if isinstance(response.data, list) else []
    elif not response.success:
        error = response.error

    return render(
        request,
        "deployments/repo_class_detail.html",
        {
            "repo_class_name": repo_class_name,
            "versions": versions,
            "error": error,
        },
    )


@login_required
def repo_class_version_detail(request, repo_class_name: str, version: str):
    """Show full detail for one repo class version: discovery metadata,
    default configuration, and role dependencies."""
    client = get_api_client_for_request(request)
    response = client.get_repo_class_version_detail(repo_class_name, version)

    detail = response.data if response.success else None
    sections = _build_repo_class_version_detail_sections(detail)

    return render(
        request,
        "deployments/repo_class_version_detail.html",
        {
            "repo_class_name": repo_class_name,
            "version": version,
            "detail": detail,
            "discovery": sections["discovery"],
            "dependency_rows": sections["dependency_rows"],
            "default_configuration": sections["default_configuration"],
            "created": sections["created"],
            "updated": sections["updated"],
            "error": response.error if not response.success else None,
        },
    )


# ============== Resource Views ==============


@login_required
def resource_definition_list(request):
    """Browse Resource Definitions (NERD0004), read-only.

    Global catalog — not environment-scoped (like ``repo_class_list``). Supports a
    namespace filter (server-side) and a free-text search (client-side substring on
    name/namespace). Pagination uses ``page`` (never ``pg`` — WAF history).
    """
    client = get_api_client_for_request(request)
    namespace = request.GET.get("namespace", "").strip()
    search = request.GET.get("search", "").strip().lower()

    response = client.list_resource_definitions(resource_namespace=namespace or None)

    definitions = []
    error = None
    if response.success and response.data:
        definitions = response.data if isinstance(response.data, list) else []
        definitions = _filter_resource_definitions(definitions, search)
    elif not response.success:
        error = response.error

    paginator = Paginator(definitions, 50)
    page = request.GET.get("page", 1)
    definitions_page = paginator.get_page(page)

    return render(
        request,
        "deployments/resource_definition_list.html",
        {
            "definitions": definitions_page,
            "namespace": namespace,
            "search": search,
            "error": error,
        },
    )


@login_required
def resource_definition_detail(request, rd_id: str):
    """Show a Resource Definition with its isa ancestry, effective (merged) output
    schema, and the RepoClassVersions that produce it. Read-only."""
    client = get_api_client_for_request(request)
    include_subtypes = request.GET.get("include_subtypes", "").lower() == "true"

    def_response = client.get_resource_definition(rd_id)
    ancestry_response = client.get_resource_definition_ancestry(rd_id)
    schema_response = client.get_effective_output_schema(rd_id)
    producers_response = client.get_producers(rd_id, include_subtypes=include_subtypes)

    return render(
        request,
        "deployments/resource_definition_detail.html",
        {
            "rd_id": rd_id,
            "include_subtypes": include_subtypes,
            "definition": def_response.data if def_response.success else None,
            "ancestry": ancestry_response.data if ancestry_response.success else [],
            "schema": schema_response.data if schema_response.success else None,
            "producers": producers_response.data if producers_response.success else [],
            "definition_error": def_response.error
            if not def_response.success
            else None,
            "ancestry_error": ancestry_response.error
            if not ancestry_response.success
            else None,
            "schema_error": schema_response.error
            if not schema_response.success
            else None,
            "producers_error": producers_response.error
            if not producers_response.success
            else None,
        },
    )


@login_required
def resource_list(request):
    """Browse concrete Resources (NERD0004), scoped to an environment, read-only.

    Environment is chosen via an in-page ``?environment=<type>`` picker (mirroring
    ``environment_compare``); without it the page shows a "pick an environment"
    prompt and issues no query. Once an environment is selected, the page defaults to
    a full, paginated list of that environment's resources (``?page=`` navigates).
    Tags are an optional narrowing filter *within* the selected environment:
    ``?key=&value=`` (single tag) or ``?tags=k=v,k=v`` (AND selector); tag-filtered
    results are unpaginated."""
    client = get_api_client_for_request(request)
    environments = get_user_environments(request.user, client)

    environment = (request.GET.get("environment") or "").strip()
    key = request.GET.get("key", "").strip()
    value = request.GET.get("value", "").strip()
    tags = request.GET.get("tags", "").strip()

    resources = []
    error = None
    pagination = None

    if environment:
        if not user_has_environment_access(request.user, environment):
            error = f"You don't have view permission for environment '{environment}'."
        else:
            resources, pagination, error = query_resources(
                client,
                environment,
                key=key,
                value=value,
                tags=tags,
                page=parse_page(request.GET.get("page")),
            )

    decode_resource_outputs(resources)

    return render(
        request,
        "deployments/resource_list.html",
        {
            "environments": environments,
            "environment": environment,
            "resources": resources,
            "key": key,
            "value": value,
            "tags": tags,
            "pagination": pagination,
            "error": error,
        },
    )


@login_required
@require_GET
@require_environment_access("viewer")
def instance_resources(request, environment: str, instance_name: str):
    """HTMX partial: resources produced by an instance's latest deployment.

    Resolves the newest RepoInstanceDeployment identifier from the instance's
    deployment history (sorted newest-first by the service), then lists its
    resources. Empty-state when there is no deployment or no resources."""
    client = get_api_client_for_request(request)

    history_response = client.get_deployment_history(environment, instance_name)
    history_data = history_response.data if history_response.success else {}
    if isinstance(history_data, dict):
        history_list = history_data.get("history", [])
    else:
        history_list = history_data or []

    rid = history_list[0].get("identifier") if history_list else None
    resources = []
    error = None
    if rid:
        res_response = client.get_deployment_resources(rid)
        if res_response.success:
            resources = res_response.data if isinstance(res_response.data, list) else []
        else:
            error = res_response.error
    elif not history_response.success:
        error = history_response.error

    return render(
        request,
        "deployments/partials/instance_resources.html",
        {
            "environment": environment,
            "instance_name": instance_name,
            "resources": resources,
            "error": error,
        },
    )


# ============== API Endpoints ==============


@login_required
@require_GET
@require_environment_access("viewer", when_missing="defer", response="partial")
def api_repo_class_version_resources(request):
    """HTMX partial: resource dependencies a repo class version requires/produces.

    Reads ``?repo_class_version_id=`` and an ``environment`` to resolve candidate
    producers against; renders the produced/required resource summary for the
    repo class detail page's lazy expander."""
    rcv_id = request.GET.get("repo_class_version_id", "").strip()
    environment = request.GET.get("environment", "").strip()
    if not rcv_id or not environment:
        return HttpResponse("")

    client = get_api_client_for_request(request)
    response = client.suggest_resource_dependencies(
        environment, repo_class_version_id=rcv_id
    )

    roles = []
    error = None
    if response.success and isinstance(response.data, dict):
        for role_name, info in response.data.items():
            if not isinstance(info, dict):
                continue
            roles.append({"role": role_name, **info})
    elif not response.success:
        error = response.error

    return render(
        request,
        "deployments/partials/repo_class_version_resources.html",
        {"roles": roles, "environment": environment, "error": error},
    )


@login_required
@require_GET
def api_repo_versions(request, repo_class_name: str):
    """Get available versions for a repo class (for dropdowns)."""
    client = get_api_client_for_request(request)
    response = client.find_repo_class_versions(repo_class_name)

    if response.success:
        versions = [v.get("version") for v in (response.data or []) if v.get("version")]
        return JsonResponse({"versions": versions})

    return JsonResponse({"error": response.error}, status=400)


@login_required
@require_GET
@require_environment_access("viewer", response="json")
def api_search_instances(request):
    """Search instances in one environment.

    ``environment`` is required and authorized by the decorator. It used to
    default to "dev", which searched an environment the caller had not named and
    might not be able to see.
    """
    query = request.GET.get("q", "")
    environment = request.GET.get("environment", "").strip()

    if not query:
        return JsonResponse({"results": []})

    client = get_api_client_for_request(request)
    response = client.get_deployment_bom(environment)

    if response.success:
        results = [
            {
                "name": item.get("repo_instance_name"),
                "repo_class": item.get("repo_class_name"),
                "version": item.get("repo_class_version"),
            }
            for item in (response.data or [])
            if query.lower() in item.get("repo_instance_name", "").lower()
        ][
            :20
        ]  # Limit results
        return JsonResponse({"results": results})

    return JsonResponse({"error": response.error}, status=400)


# ============== Health Check ==============


def health_check(request):
    """Kubernetes health check endpoint.

    Also reports whether the MCP server initialised and how many tools it
    registered. That gives probes and acceptance tests a cheap, unauthenticated
    way to confirm /mcp actually came up -- the endpoint itself requires a
    bearer token, so it can't be probed directly.
    """
    payload = {
        "status": "healthy",
        "service": "neuronsphere-deployment-gui",
    }

    if settings.MCP_ENABLED:
        from ns_mcp.server import get_server_stats

        stats = get_server_stats()
        # "built" is only true in a process that went through
        # deployment_gui/asgi.py, so it doubles as proof the ASGI entry point is
        # the one serving -- more reliable than inferring the transport from a
        # setting, which would still read "asgi" after a WSGI rollback.
        payload["mcp"] = {
            "enabled": True,
            "built": stats["built"],
            "mount_path": settings.MCP_MOUNT_PATH,
            "tools": stats["tools"],
            "tool_names": stats["tool_names"],
            "resources": stats["resources"],
            "resource_uris": stats["resource_uris"],
            "prompts": stats["prompts"],
            "prompt_names": stats["prompt_names"],
            "federated_servers": stats["federated"],
            # Empty unless Okta auth is configured. A client discovers where to get a
            # token from this document, so an empty list in cloud means discovery is
            # not being advertised even though the endpoint demands a bearer.
            "well_known_routes": stats["well_known_routes"],
        }
    else:
        payload["mcp"] = {"enabled": False}

    return JsonResponse(payload)
