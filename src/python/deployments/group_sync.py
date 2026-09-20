"""Identity-provider group-to-permission sync logic.

Resolves the group claim asserted by whichever IdP the user signed in through
against the configured mapping, and syncs UserEnvironmentPermission records.
Also reconciles the Django is_superuser/is_staff flags so platform admins do not
need a manual createsuperuser step.

Provider-neutral: mappings may be scoped per provider (IDP_GROUP_MAPPING /
IDP_SUPERUSER_GROUPS, keyed by provider_id) so two IdPs can use the same group
name for different things. The unscoped legacy settings (OKTA_GROUP_MAPPING /
OKTA_SUPERUSER_GROUPS) still apply to every provider, which preserves existing
single-provider behaviour exactly and is the migration-friendly reading when a
second provider is added carrying the same group names.
"""
import logging

from allauth.socialaccount.models import SocialAccount
from django.conf import settings
from django.db import transaction

from .models import AuditLog, UserEnvironmentPermission

logger = logging.getLogger(__name__)

# Role hierarchy for resolving conflicts (higher index wins)
ROLE_HIERARCHY = {
    UserEnvironmentPermission.Role.VIEWER: 0,
    UserEnvironmentPermission.Role.DEPLOYER: 1,
    UserEnvironmentPermission.Role.ADMIN: 2,
}


def _mapping_for(provider):
    """Group->{env: role} visible to ``provider``.

    The provider-scoped entries win over the unscoped legacy mapping on a group
    name collision, so a deployment can override one provider's meaning of a
    group without disturbing the others.
    """
    unscoped = getattr(settings, "OKTA_GROUP_MAPPING", {}) or {}
    scoped = (getattr(settings, "IDP_GROUP_MAPPING", {}) or {}).get(provider, {})
    return {**unscoped, **scoped}


def _superuser_groups_for(provider):
    """Group names that confer superuser under ``provider``."""
    unscoped = getattr(settings, "OKTA_SUPERUSER_GROUPS", []) or []
    scoped = (getattr(settings, "IDP_SUPERUSER_GROUPS", {}) or {}).get(provider, [])
    return list(unscoped) + list(scoped)


def sync_idp_permissions(user, group_names, request=None, provider=None):
    """Sync a user's IdP-sourced environment permissions from group claims.

    Resolves the user's groups to environment+role pairs and replaces all
    IdP-sourced permissions for the user. Manual permissions are untouched.

    Args:
        user: Django User instance
        group_names: Group names from the provider's groups claim
        request: Optional Django request (for audit log IP/user-agent)
        provider: provider_id the user signed in through, selecting the
            provider-scoped mapping. None uses only the unscoped mapping.
    """
    okta_group_names = group_names
    _reconcile_superuser(user, okta_group_names, request, provider)

    mapping = _mapping_for(provider)
    if not mapping:
        logger.debug(
            "No group mapping configured for provider=%s, skipping sync for %s",
            provider,
            user.username,
        )
        return

    if not okta_group_names:
        logger.debug(
            "No Okta groups for %s, clearing Okta-sourced permissions", user.username
        )
        _apply_permissions(user, {}, request)
        return

    # Resolve groups to environment+role pairs, highest role wins per environment
    resolved = {}
    matched_groups = []
    for group_name in okta_group_names:
        env_roles = mapping.get(group_name)
        if not env_roles:
            continue
        matched_groups.append(group_name)
        for environment, role in env_roles.items():
            if role not in ROLE_HIERARCHY:
                logger.warning(
                    "Invalid role '%s' in group mapping for group '%s' env '%s', skipping",
                    role,
                    group_name,
                    environment,
                )
                continue
            existing_role = resolved.get(environment)
            if (
                existing_role is None
                or ROLE_HIERARCHY[role] > ROLE_HIERARCHY[existing_role]
            ):
                resolved[environment] = role

    logger.info(
        "Okta group sync for %s: matched groups=%s, resolved permissions=%s",
        user.username,
        matched_groups,
        resolved,
    )

    _apply_permissions(user, resolved, request, matched_groups)


def _apply_permissions(user, resolved_permissions, request=None, matched_groups=None):
    """Replace Okta-sourced permissions for a user.

    Args:
        user: Django User instance
        resolved_permissions: Dict of {environment: role} to set
        request: Optional Django request for audit logging
        matched_groups: List of matched Okta group names for audit details
    """
    with transaction.atomic():
        # Delete all existing Okta-sourced permissions for this user
        deleted_count, _ = UserEnvironmentPermission.objects.filter(
            user=user,
            source=UserEnvironmentPermission.Source.OKTA,
        ).delete()

        # Create new permissions from resolved mapping
        created = []
        for environment, role in resolved_permissions.items():
            perm = UserEnvironmentPermission.objects.create(
                user=user,
                environment=environment,
                role=role,
                source=UserEnvironmentPermission.Source.OKTA,
            )
            created.append(perm)

        # Audit log
        try:
            AuditLog.objects.create(
                user=user,
                action=AuditLog.Action.GROUP_SYNC,
                target=f"user:{user.username}",
                details={
                    "okta_groups": matched_groups or [],
                    "permissions_deleted": deleted_count,
                    "permissions_created": [
                        {"environment": p.environment, "role": p.role} for p in created
                    ],
                },
                ip_address=_get_ip(request),
                user_agent=_get_user_agent(request),
                success=True,
            )
        except Exception as e:
            logger.error("Failed to create audit log for group sync: %s", e)

    logger.info(
        "Okta sync complete for %s: deleted=%d, created=%d",
        user.username,
        deleted_count,
        len(created),
    )


def _reconcile_superuser(user, okta_group_names, request=None, provider=None):
    """Toggle Django is_superuser/is_staff from the user's Okta groups.

    Skips users with no SocialAccount so that bootstrap accounts created via
    `manage.py createsuperuser` are not affected.
    """
    superuser_groups = _superuser_groups_for(provider)
    if not superuser_groups:
        logger.warning(
            "Superuser reconcile for %s skipped: no superuser groups configured "
            "for provider=%s",
            user.username,
            provider,
        )
        return

    if not SocialAccount.objects.filter(user=user).exists():
        logger.info(
            "Superuser reconcile for %s skipped: no SocialAccount on file",
            user.username,
        )
        return

    claimed = list(okta_group_names or [])
    should_be_superuser = any(g in superuser_groups for g in claimed)
    logger.info(
        "Superuser reconcile for %s: claimed_groups=%s superuser_groups=%s match=%s",
        user.username,
        claimed,
        superuser_groups,
        should_be_superuser,
    )
    if (
        user.is_superuser == should_be_superuser
        and user.is_staff == should_be_superuser
    ):
        return

    user.is_superuser = should_be_superuser
    user.is_staff = should_be_superuser
    user.save(update_fields=["is_superuser", "is_staff"])

    logger.info(
        "Reconciled Django superuser flag for %s: is_superuser=%s",
        user.username,
        should_be_superuser,
    )

    try:
        AuditLog.objects.create(
            user=user,
            action=AuditLog.Action.GROUP_SYNC,
            target=f"user:{user.username}",
            details={
                "superuser_set": should_be_superuser,
                "okta_groups": list(okta_group_names or []),
                "okta_superuser_groups": list(superuser_groups),
            },
            ip_address=_get_ip(request),
            user_agent=_get_user_agent(request),
            success=True,
        )
    except Exception as e:
        logger.error("Failed to create audit log for superuser reconcile: %s", e)


def _get_ip(request):
    """Extract client IP from request if available."""
    if request is None:
        return None
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _get_user_agent(request):
    """Extract user agent from request if available."""
    if request is None:
        return ""
    return request.META.get("HTTP_USER_AGENT", "")[:500]


# Retained name for callers predating multi-provider support -- notably the Robot
# keyword in test/resources/PermissionSeed.py. Resolves against the unscoped
# mapping, which is what a single-provider deployment has.
sync_okta_permissions = sync_idp_permissions
