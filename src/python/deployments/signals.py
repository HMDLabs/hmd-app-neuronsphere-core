"""Signal handlers for the deployments app."""
import logging

from allauth.socialaccount.models import SocialAccount
from django.dispatch import receiver

from allauth.account.signals import user_logged_in

from .group_sync import sync_idp_permissions  # noqa: F401

logger = logging.getLogger(__name__)


@receiver(user_logged_in)
def sync_idp_groups_on_login(sender, request, user, **kwargs):
    """Sync IdP groups when a social account user logs in.

    This handles re-login of existing users where pre_social_login may have
    already run. We check for _idp_groups on the request (set by the adapter)
    to avoid duplicate syncs when the adapter already handled it.
    """
    # Only process if we have groups stashed by the adapter
    idp_groups = getattr(request, "_idp_groups", None)
    if idp_groups is None:
        # Not a social login, or the adapter didn't set groups -- check whether the
        # user has *any* social account (re-login via session restore won't trigger
        # the adapter). Deliberately unfiltered by provider: the GUI registers one
        # allauth app per configured IdP, so the provider id varies per deployment.
        if SocialAccount.objects.filter(user=user).exists():
            logger.debug(
                "Social login for %s but no groups claim available, skipping sync",
                user.username,
            )
        return

    # Mark as consumed to prevent duplicate processing
    request._idp_groups = None
