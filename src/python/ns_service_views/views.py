"""The Services pages and the partial proxy (NERD007 SPEC001-SPEC003, SPEC007).

Pages live at ``/services/<env>/<instance>/`` so that a partial's relative
HTMX URLs, written as ``views/...``, resolve to this app's proxy route.
"""

import logging
from collections import OrderedDict

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from deployments.decorators import require_environment_access
from deployments.services.auth import get_api_client_for_request
from deployments.services.environment_service import get_user_environments

from . import discovery, proxy
from .permissions import (
    enforcing,
    missing_permissions,
    permissions_for,
    user_bearer_token,
    user_groups,
    visible_views,
)

logger = logging.getLogger(__name__)


def _fragment(message, status):
    return render(
        None,
        "ns_service_views/error_fragment.html",
        {"message": message},
        status=status,
    )


def _proxy_url(environment, instance, view):
    rest = view["path"][len(discovery.VIEW_PATH_PREFIX) :]
    return reverse("ns_service_views:proxy", args=[environment, instance, rest])


@login_required
def index(request):
    client = get_api_client_for_request(request)
    environments = get_user_environments(request.user, client)
    environment = request.GET.get("environment") or (
        environments[0] if environments else ""
    )
    if environment:
        return redirect("ns_service_views:service_list", environment=environment)
    return render(request, "ns_service_views/service_list.html", {"services": []})


@login_required
@require_environment_access("viewer")
def service_list(request, environment):
    client = get_api_client_for_request(request)
    groups = user_groups(request.user)
    services = []
    for svc in discovery.inventory(client, environment):
        views = visible_views(svc, groups)
        if views:
            services.append({"service": svc, "views": views})
    return render(
        request,
        "ns_service_views/service_list.html",
        {
            "environment": environment,
            "environments": get_user_environments(request.user, client),
            "services": services,
        },
    )


@login_required
@require_environment_access("viewer")
def service_detail(request, environment, instance):
    client = get_api_client_for_request(request)
    svc = discovery.find_service(client, environment, instance)
    if svc is None:
        return render(
            request,
            "ns_service_views/service_missing.html",
            {"environment": environment, "instance": instance},
            status=404,
        )
    groups = OrderedDict()
    for view in visible_views(svc, user_groups(request.user)):
        entry = dict(view, url=_proxy_url(environment, instance, view))
        groups.setdefault(view.get("group") or "Views", []).append(entry)
    selected = request.GET.get("view")
    initial = next(
        (v for vs in groups.values() for v in vs if v["id"] == selected),
        next((vs[0] for vs in groups.values()), None),
    )
    return render(
        request,
        "ns_service_views/service_detail.html",
        {
            "environment": environment,
            "service": svc,
            "groups": groups,
            "initial": initial,
        },
    )


@login_required
@require_environment_access("viewer", response="partial")
@require_http_methods(["GET", "POST"])
def proxy_view(request, environment, instance, rest):
    client = get_api_client_for_request(request)
    svc = discovery.find_service(client, environment, instance)
    view = svc.view_at(discovery.VIEW_PATH_PREFIX + rest) if svc else None
    if view is None:
        # Only what the inventory lists is ever forwarded: the proxy cannot be
        # pointed at an arbitrary service or path.
        return _fragment("This view is not available in this environment.", 404)

    if enforcing():
        granted = permissions_for(user_groups(request.user), svc.group_permissions)
        missing = missing_permissions(view, granted)
        if missing:
            return _fragment(
                f"You don't have permission to view this. It requires: "
                f"{', '.join(missing)}.",
                403,
            )

    try:
        upstream = proxy.forward(
            request.method,
            svc.base_url + view["path"],
            params=request.GET.dict(),
            data=request.POST.dict() if request.method == "POST" else None,
            token=user_bearer_token(request.user),
        )
    except proxy.UpstreamError as e:
        logger.warning("Service view %s/%s failed: %s", instance, view["id"], e.message)
        return _fragment(e.message, 502)

    if upstream.status_code >= 500:
        logger.warning(
            "Service view %s/%s returned %s", instance, view["id"], upstream.status_code
        )
        return _fragment(
            f"The service returned an error ({upstream.status_code}).", 502
        )

    content_type = upstream.headers.get("content-type", "text/html; charset=utf-8")
    body = upstream.content
    if content_type.startswith("text/html"):
        body = proxy.strip_asset_tags(upstream.text)
    response = HttpResponse(
        body, status=upstream.status_code, content_type=content_type
    )
    response["X-NS-Service"] = instance
    return response
