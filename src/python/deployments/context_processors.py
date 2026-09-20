"""Context processors for deployment GUI templates."""
import re

from django.conf import settings

from .services.auth import get_api_client_for_request
from .services.environment_service import get_user_environments


def sidebar_context(request):
    """Provide sidebar navigation data to all templates.

    Returns sidebar_environments, active_section, and active_environment
    for use by the sidebar partial template.
    """
    if not hasattr(request, "user") or not request.user.is_authenticated:
        return {}

    # Get user's accessible environments from the deployment service
    client = get_api_client_for_request(request)
    environments = get_user_environments(request.user, client)

    # Determine active section from URL path
    path = request.path
    if path == "/" or path.startswith("/dashboard"):
        active_section = "dashboard"
    elif path.startswith("/environments") or path.startswith("/bom/"):
        active_section = "environments"
    elif path.startswith("/changeset"):
        active_section = "changesets"
    elif path.startswith("/repo-classes"):
        active_section = "repo_classes"
    elif path.startswith("/resources"):
        active_section = "resources"
    else:
        active_section = ""
        # Sections an extra app contributes (settings.EXTENSION_SECTIONS).
        for section, prefix in getattr(settings, "EXTENSION_SECTIONS", {}).items():
            if path.startswith(prefix):
                active_section = section
                break

    # Extract active environment from BOM URLs like /bom/<env>/
    active_environment = ""
    match = re.match(r"^/bom/([^/]+)/", path)
    if match:
        active_environment = match.group(1)

    return {
        "sidebar_environments": environments,
        "active_section": active_section,
        "active_environment": active_environment,
    }
