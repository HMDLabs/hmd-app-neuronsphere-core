"""Decorators for view access control and audit logging."""
import logging
import time
import uuid
from functools import wraps

from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import render

from .services.audit import record_audit
from .services.authz import (
    user_has_deployment_set_access,
    user_has_environment_access,
)

logger = logging.getLogger(__name__)


def get_client_ip(request):
    """Extract client IP from request.

    Args:
        request: Django HTTP request

    Returns:
        Client IP address string
    """
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _environment_denied_response(request, environment, role_required, response_style):
    """Render an access denial in the shape the caller can actually consume.

    ``access_denied.html`` extends ``base.html``. Swapping a whole page into an
    HTMX target, or returning it to a fetch() expecting JSON, turns a 403 into a
    rendering bug -- so the shape is declared per view rather than assumed.
    """
    context = {"environment": environment, "role_required": role_required}
    if response_style == "json":
        return JsonResponse(
            {
                "error": f"You do not have {role_required} access to environment "
                f"'{environment}'."
            },
            status=403,
        )
    template = (
        "deployments/partials/access_denied.html"
        if response_style == "partial"
        else "deployments/access_denied.html"
    )
    return render(request, template, context, status=403)


def require_environment_access(
    role_required="viewer",
    *,
    param="environment",
    when_missing="deny",
    response="page",
):
    """Check the caller's access to the environment(s) a view acts on.

    Args:
        role_required: 'viewer' or 'deploy'.
        param: name of the parameter holding the environment, or a tuple of names
            when a view spans more than one (the compare views take ``from``/``to``).
            Every named value is checked; first failure wins. Each is resolved from
            view kwargs, then POST, then GET -- so an internally delegated call must
            pass the environment as a *keyword* argument to be seen.
        when_missing: 'deny' refuses when no value is present, which is right for a
            view that cannot function without one. 'defer' hands off to the view,
            for the HTMX partials that render a "pick an environment" hint instead.
            Deferring is safe precisely because no environment means no environment
            data is fetched.
        response: shape of the denial -- 'page' (full 403 page), 'partial' (a small
            fragment for an HTMX target), or 'json'.

    Authorization goes through ``services.authz.user_has_environment_access`` so
    the views, the MCP tools, and anything added later share one definition of
    "can this user see this environment".
    """
    params = (param,) if isinstance(param, str) else tuple(param)

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            user = request.user

            for name in params:
                environment = kwargs.get(name)
                if not environment:
                    environment = request.POST.get(name)
                if not environment:
                    environment = request.GET.get(name)
                environment = (environment or "").strip()

                if not environment:
                    if when_missing == "defer":
                        continue
                    return HttpResponseForbidden("Environment not specified")

                if not user_has_environment_access(user, environment, role_required):
                    logger.warning(
                        f"Access denied: {user.username} lacks {role_required} "
                        f"access to {environment}"
                    )
                    return _environment_denied_response(
                        request, environment, role_required, response
                    )

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def require_deployment_set_access(
    deploy_required=False,
    *,
    param="deployment_set",
    when_missing="deny",
    response="page",
):
    """Check the caller's access to the deployment set a view acts on.

    Args:
        deploy_required: require deploy rights rather than view rights.
        param: name of the parameter holding the deployment set. Resolved from
            view kwargs, then POST, then GET.
        when_missing: 'deny' refuses when no value is present. 'defer' hands off to
            the view, for a view where the set is genuinely an optional filter.
        response: 'page', 'partial', or 'json'.

    ``when_missing`` defaults to 'deny'. This decorator previously called the view
    unconditionally when it found no deployment set, which meant applying it to a
    view that reads the set from anywhere it does not look would protect nothing
    while appearing to. Opting out of the check is now something a view has to say.
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            deployment_set = kwargs.get(param)
            if not deployment_set:
                deployment_set = request.POST.get(param)
            if not deployment_set:
                deployment_set = request.GET.get(param)
            deployment_set = (deployment_set or "").strip()

            role_label = "deploy" if deploy_required else "view"

            if not deployment_set:
                if when_missing == "defer":
                    return view_func(request, *args, **kwargs)
                return HttpResponseForbidden("Deployment set not specified")

            user = request.user

            if not user_has_deployment_set_access(
                user, deployment_set, deploy_required
            ):
                logger.warning(
                    f"Access denied: {user.username} lacks {role_label} access "
                    f"to deployment set {deployment_set}"
                )
                context = {
                    "deployment_set": deployment_set,
                    "role_required": role_label,
                }
                if response == "json":
                    return JsonResponse(
                        {
                            "error": f"You do not have {role_label} access to "
                            f"deployment set '{deployment_set}'."
                        },
                        status=403,
                    )
                template = (
                    "deployments/partials/access_denied.html"
                    if response == "partial"
                    else "deployments/access_denied.html"
                )
                return render(request, template, context, status=403)

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def audit_action(action_type):
    """Decorator to log actions to audit log.

    Args:
        action_type: AuditLog.Action value

    Returns:
        Decorator function
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            start_time = time.time()
            correlation_id = str(uuid.uuid4())

            # Add correlation ID to request for use in logging
            request.correlation_id = correlation_id

            success = True
            error_message = None
            response = None

            try:
                response = view_func(request, *args, **kwargs)
                if response is not None:
                    success = response.status_code < 400
                return response
            except Exception as e:
                success = False
                error_message = str(e)
                raise
            finally:
                duration_ms = int((time.time() - start_time) * 1000)

                # Determine target from kwargs
                target_parts = []
                if "environment" in kwargs:
                    target_parts.append(kwargs["environment"])
                if "instance_name" in kwargs:
                    target_parts.append(kwargs["instance_name"])
                if "csd_id" in kwargs:
                    target_parts.append(kwargs["csd_id"])

                target = ":".join(target_parts) if target_parts else "N/A"

                record_audit(
                    user=request.user,
                    action=action_type,
                    target=target,
                    details={
                        "method": request.method,
                        "path": request.path,
                        "query_params": dict(request.GET),
                    },
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get("HTTP_USER_AGENT", ""),
                    correlation_id=correlation_id,
                    success=success,
                    error_message=error_message,
                    duration_ms=duration_ms,
                )

        return wrapper

    return decorator
