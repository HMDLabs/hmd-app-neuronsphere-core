"""Service for fetching environments from the deployment API."""
import logging
from typing import List

from django.contrib.auth.models import AbstractUser

from ..models import UserEnvironmentPermission
from .api_client import DeploymentAPIClient

logger = logging.getLogger(__name__)


def get_all_environments(client: DeploymentAPIClient) -> List[str]:
    """Fetch all environment types from the deployment service.

    Returns an empty list if the API call fails or returns no data.
    """
    response = client.list_environments()
    if not response.success:
        logger.warning("list_environments API call failed: %s", response.error)
        return []
    if not response.data:
        logger.warning("list_environments returned no data")
        return []

    raw_entities = response.data if isinstance(response.data, list) else []
    environments = []
    for entity in raw_entities:
        env_type = entity.get("content", {}).get("type") or entity.get("type")
        if env_type:
            environments.append(env_type)

    if raw_entities and not environments:
        sample_keys = sorted((raw_entities[0] or {}).keys())
        logger.warning(
            "list_environments returned %d entities but none had content.type or type; "
            "sample entity top-level keys=%s",
            len(raw_entities),
            sample_keys,
        )

    return sorted(environments)


def get_user_environments(user: AbstractUser, client: DeploymentAPIClient) -> List[str]:
    """Get environments accessible to a user.

    Superusers see all environments from the deployment service.
    Regular users see only environments they have permissions for.
    """
    if user.is_superuser:
        environments = get_all_environments(client)
        logger.info(
            "Resolved environments for %s via superuser path: is_superuser=True count=%d envs=%s",
            user.username,
            len(environments),
            environments,
        )
        return environments

    environments = UserEnvironmentPermission.get_user_environments(user)
    logger.info(
        "Resolved environments for %s via permission table: is_superuser=False count=%d envs=%s",
        user.username,
        len(environments),
        environments,
    )
    if not environments:
        logger.warning(
            "User %s has no environment permissions; environment list will be empty. "
            "Verify OKTA_GROUP_MAPPING and the user's Okta group membership.",
            user.username,
        )
        return []
    return environments
