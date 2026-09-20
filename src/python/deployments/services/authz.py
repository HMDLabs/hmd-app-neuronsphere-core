"""Environment and DeploymentSet authorization, independent of the transport.

The GUI enforces access with view decorators that render ``access_denied.html``;
the MCP tool layer needs the same decision as a plain call that raises. Both go
through the functions here so there is exactly one definition of "can this user
see this environment".

Kept free of Django imports at module scope so it can be unit-tested without a
configured settings module; the permission models are imported lazily.
"""


class AccessDenied(Exception):
    """Base class for an authorization failure."""

    def __init__(self, message, role_required="viewer"):
        super().__init__(message)
        self.message = message
        self.role_required = role_required


class EnvironmentAccessDenied(AccessDenied):
    def __init__(self, environment, role_required="viewer"):
        self.environment = environment
        super().__init__(
            f"You do not have {role_required} access to environment "
            f"'{environment}'.",
            role_required,
        )


class DeploymentSetAccessDenied(AccessDenied):
    def __init__(self, deployment_set, role_required="view"):
        self.deployment_set = deployment_set
        super().__init__(
            f"You do not have {role_required} access to deployment set "
            f"'{deployment_set}'.",
            role_required,
        )


def user_has_environment_access(user, environment: str, role: str = "viewer") -> bool:
    """Whether ``user`` may act on ``environment`` at ``role``.

    Superusers short-circuit to True, matching the view decorator. ``role`` is
    "viewer" for reads; anything else is treated as requiring deploy rights.
    """
    from ..models import UserEnvironmentPermission

    if getattr(user, "is_superuser", False):
        return True
    if role == "viewer":
        return UserEnvironmentPermission.user_can_view(user, environment)
    return UserEnvironmentPermission.user_can_deploy(user, environment)


def assert_environment_access(user, environment: str, role: str = "viewer") -> None:
    """Raise ``EnvironmentAccessDenied`` unless ``user`` may act on ``environment``.

    The raising counterpart of the ``require_environment_access`` view decorator,
    for callers that render their own error (the MCP tools).
    """
    if not environment:
        raise EnvironmentAccessDenied("<unspecified>", role)
    if not user_has_environment_access(user, environment, role):
        raise EnvironmentAccessDenied(environment, role)


def user_has_deployment_set_access(
    user, deployment_set: str, deploy: bool = False
) -> bool:
    """Whether ``user`` may view (or deploy to) ``deployment_set``."""
    from ..models import DeploymentSetPermission

    if getattr(user, "is_superuser", False):
        return True
    if deploy:
        return DeploymentSetPermission.user_can_deploy_to_set(user, deployment_set)
    return DeploymentSetPermission.user_can_view_set(user, deployment_set)


def assert_deployment_set_access(
    user, deployment_set: str, deploy: bool = False
) -> None:
    """Raise ``DeploymentSetAccessDenied`` unless ``user`` may act on the set."""
    if not user_has_deployment_set_access(user, deployment_set, deploy):
        raise DeploymentSetAccessDenied(deployment_set, "deploy" if deploy else "view")
