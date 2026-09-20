"""The ``@read_tool`` decorator -- the single seam every MCP tool goes through.

A tool body is a plain sync function taking a ``ToolContext`` plus its declared
arguments. Everything around it happens here exactly once:

    resolve caller -> threadpool hop -> load user -> AUTHORIZE -> build client
      -> run the tool -> write an AuditLog row -> close connections

Authorization is deliberately *opt-out*: a tool declares which of its parameters
names an environment, and the check is performed by this decorator rather than
by the tool body. Six GUI endpoints accepted an arbitrary ``?environment=``
behind only ``@login_required`` before NERD008 SPEC013 closed them; making the
check structural is how this surface avoids acquiring that class of bug in the
first place, rather than having to go looking for it. ``test_mcp_registry``
asserts the invariant.
"""
import functools
import inspect
import logging
import time
import uuid
from typing import Optional

from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_http_request

from .context import run_in_django
from .principal import resolve_principal

logger = logging.getLogger(__name__)

#: Marks a wrapped tool with the environment parameter(s) it authorizes on, so
#: the registry test can verify every environment-scoped tool declares them.
ENVIRONMENT_ARG_ATTR = "_ns_mcp_environment_arg"


def environment_args(fn) -> tuple:
    """The environment parameters ``fn`` authorizes on, always as a tuple.

    ``environment_arg`` is declared as a bare string in the common single-
    environment case and as a tuple by the tools that take two (compare_
    environments); callers that need to reason about the set want one shape.
    """
    declared = getattr(fn, ENVIRONMENT_ARG_ATTR, None)
    if not declared:
        return ()
    if isinstance(declared, str):
        return (declared,)
    return tuple(declared)


class ToolContext:
    """What a tool body needs: the caller, their Django user, and an API client."""

    __slots__ = ("user", "principal", "client")

    def __init__(self, user, principal, client):
        self.user = user
        self.principal = principal
        self.client = client


def _request_metadata():
    """Client IP and user agent for the audit row; tolerant of no HTTP request."""
    try:
        request = get_http_request()
    except Exception:  # pragma: no cover - no HTTP context (in-memory client)
        return None, ""
    forwarded = request.headers.get("x-forwarded-for")
    ip = (
        forwarded.split(",")[0].strip()
        if forwarded
        else (request.client.host if request.client else None)
    )
    return ip, request.headers.get("user-agent", "")


def _build_client(principal):
    """An API client carrying the right downstream identity.

    Under the default ``passthrough`` mode an Okta principal forwards the caller's own
    token, so hmd-ms-deployment applies its RBAC to the *user* -- matching
    ``get_api_client_for_request``. An API-key principal has no user token to forward
    and falls back to the service account under either mode; authorization still
    happens here, against the key's owner.

    ``MCP_DOWNSTREAM_TOKEN_MODE=service`` forces every downstream call onto the service
    account. It exists as the fallback for a deployment where forwarding does not work
    -- if hmd-ms-deployment does not accept the caller's token, which turns on whether
    its `cid` is a trusted human client there.
    """
    from django.conf import settings

    from deployments.services.api_client import DeploymentAPIClient
    from deployments.services.auth import get_api_client

    if principal.is_api_key:
        return get_api_client()
    if getattr(settings, "MCP_DOWNSTREAM_TOKEN_MODE", "passthrough") == "service":
        return get_api_client()
    return DeploymentAPIClient(auth_token=principal.raw_token)


def clamp_limit(limit: Optional[int] = None) -> int:
    """Bound a caller-supplied page size to the configured range.

    A model will happily ask for ``limit=100000``; a real BOM is large enough
    that honouring it would blow the context it is being read into. Anything
    missing or unparseable falls back to ``MCP_DEFAULT_PAGE_SIZE``, and anything
    oversized is clamped rather than rejected -- a truncated answer is more
    useful to the caller than an error.
    """
    from django.conf import settings

    try:
        value = int(limit)
    except (TypeError, ValueError):
        return settings.MCP_DEFAULT_PAGE_SIZE
    return max(1, min(value, settings.MCP_MAX_PAGE_SIZE))


def read_tool(*, action, environment_arg: str = None, role: str = "viewer"):
    """Wrap a sync tool body with identity, authorization, and auditing.

    Args:
        action: an ``AuditLog.Action`` value recorded for every call.
        environment_arg: name of the parameter holding the environment to
            authorize against, or a tuple of names when a tool spans more than
            one environment -- every one of them is checked, first failure
            wins. Omit only for genuinely global catalog reads.
        role: ``"viewer"`` for reads; anything else requires deploy rights.
    """

    def decorator(fn):
        signature = inspect.signature(fn)
        parameters = list(signature.parameters.values())
        if not parameters:
            raise TypeError(
                f"{fn.__name__} must accept a ToolContext as its first parameter"
            )
        # The context is supplied by this decorator, so it must not appear in the
        # MCP input schema FastMCP derives from the signature.
        public_signature = signature.replace(parameters=parameters[1:])

        @functools.wraps(fn)
        async def wrapper(**kwargs):
            principal = resolve_principal()
            ip_address, user_agent = _request_metadata()
            return await run_in_django(
                _invoke,
                fn,
                principal,
                kwargs,
                action,
                environment_arg,
                role,
                ip_address,
                user_agent,
            )

        wrapper.__signature__ = public_signature
        setattr(wrapper, ENVIRONMENT_ARG_ATTR, environment_arg)
        return wrapper

    return decorator


def _invoke(
    fn, principal, kwargs, action, environment_arg, role, ip_address, user_agent
):
    """Authorize, run the tool, and audit. Runs in the worker thread."""
    from django.contrib.auth.models import User

    from deployments.services.audit import build_target, record_audit
    from deployments.services.authz import AccessDenied, assert_environment_access

    correlation_id = str(uuid.uuid4())
    started = time.time()
    env_args = (
        (environment_arg,) if isinstance(environment_arg, str) else environment_arg
    ) or ()
    # The audit row records one environment; the first declared is the subject
    # of the call (the *source* environment, for the two-environment tools).
    environment = kwargs.get(env_args[0]) if env_args else None
    success = True
    error_message = None
    user = None

    try:
        try:
            user = User.objects.get(pk=principal.user_id)
        except User.DoesNotExist:
            raise ToolError(
                "The account behind this credential no longer exists."
            ) from None

        for arg in env_args:
            try:
                assert_environment_access(user, kwargs.get(arg), role)
            except AccessDenied as exc:
                raise ToolError(str(exc)) from None

        return fn(ToolContext(user, principal, _build_client(principal)), **kwargs)
    except ToolError as exc:
        success = False
        error_message = str(exc)
        raise
    except Exception as exc:
        success = False
        error_message = f"{type(exc).__name__}: {exc}"
        logger.exception("MCP tool %s failed", fn.__name__)
        # Surface a clean message rather than leaking internals to the caller.
        raise ToolError(f"{fn.__name__} failed: {exc}") from None
    finally:
        record_audit(
            user=user,
            action=action,
            target=build_target(
                environment=environment, instance_name=kwargs.get("instance_name")
            ),
            details={
                "transport": "mcp",
                "tool": fn.__name__,
                "auth_mode": principal.auth_mode,
                "arguments": _redact(kwargs),
            },
            ip_address=ip_address,
            user_agent=user_agent,
            correlation_id=correlation_id,
            success=success,
            error_message=error_message,
            duration_ms=int((time.time() - started) * 1000),
        )


#: Arguments safe to record verbatim in the audit log. An allowlist rather than a
#: denylist so a future tool cannot leak a payload by adding a parameter.
_AUDITABLE_ARGS = frozenset(
    {
        "environment",
        "from_environment",
        "to_environment",
        "instance_name",
        "repo_class",
        "repo_class_name",
        "version",
        "namespace",
        "resource_definition",
        "resource_definition_name",
        "status",
        "search",
        "detail",
        "sort_by",
        "sort_dir",
        "history_limit",
        "direction",
        "limit",
        "offset",
        "include_subtypes",
        "transitive",
        "path",
        "keys_only",
        "query",
        "q",
        "resource_namespace",
        "version_spec",
        "tags",
    }
)


def _redact(kwargs: dict) -> dict:
    return {k: v for k, v in kwargs.items() if k in _AUDITABLE_ARGS}
