"""Custom allauth adapters for identity-provider group sync.

Provider-neutral by design: the GUI registers every IdP -- Okta, Auth0, Entra, or
a customer's own -- through allauth's generic ``openid_connect`` provider, one
APPS entry each. The only per-provider knowledge here is *which claim carries
group membership*, which comes from settings rather than being hardcoded,
because the claim name is not universal (Auth0 commonly namespaces it, Entra may
use ``roles``).
"""
import logging

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.contrib import messages

from .group_sync import sync_idp_permissions

logger = logging.getLogger(__name__)

DEFAULT_GROUPS_CLAIM = "groups"


def groups_claim_for(provider_id):
    """The claim carrying group membership for ``provider_id``."""
    claims = getattr(settings, "IDP_GROUPS_CLAIMS", {}) or {}
    return claims.get(provider_id) or DEFAULT_GROUPS_CLAIM


def extract_groups(extra_data, claim):
    """Pull the group claim out of whichever OIDC payload carries it.

    Providers differ in where the claim lands: some put it on the token response
    directly, others only in the userinfo response or the id_token. All three are
    checked rather than assuming one shape.
    """
    extra_data = extra_data or {}
    userinfo = extra_data.get("userinfo") or {}
    id_token = extra_data.get("id_token") or {}
    for source in (extra_data, userinfo, id_token):
        if not isinstance(source, dict):
            continue
        groups = source.get(claim)
        if groups:
            # A single-valued claim is legitimate; normalise so callers always
            # get a list rather than iterating a string character by character.
            return [groups] if isinstance(groups, str) else list(groups)
    return []


class NeuronSphereSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Social account adapter that syncs IdP groups on login."""

    def on_authentication_error(
        self, request, provider, error=None, exception=None, extra_context=None
    ):
        """Surface the IdP's error_description so the cancelled page can show it.

        allauth maps `error=access_denied` from the provider to its own CANCELLED
        auth error and redirects to the login_cancelled page without forwarding
        the error_description. We pull that description off the request and stash
        it as a Django message so the styled cancelled template can render it.
        """
        error_description = request.GET.get("error_description") or request.GET.get(
            "error"
        )
        if error_description:
            logger.warning(
                "Social login failed via provider=%s error=%s description=%s",
                getattr(provider, "id", provider),
                error,
                error_description,
            )
            messages.error(request, error_description)
        return super().on_authentication_error(
            request,
            provider,
            error=error,
            exception=exception,
            extra_context=extra_context,
        )

    def pre_social_login(self, request, sociallogin):
        """Extract IdP groups from OIDC claims and store for post-login sync.

        Called before the login is finalized. We stash the groups and the
        provider on the request so the user_logged_in signal handler can pick
        them up. For new users, save_user() handles the sync instead.
        """
        super().pre_social_login(request, sociallogin)
        provider_id = getattr(sociallogin.account, "provider", None)
        claim = groups_claim_for(provider_id)
        extra_data = sociallogin.account.extra_data or {}
        groups = extract_groups(extra_data, claim)

        request._idp_groups = groups
        request._idp_provider = provider_id
        logger.info(
            "OIDC claims for %s via provider=%s (groups_claim=%r): "
            "extra_data_keys=%s resolved_groups=%r",
            getattr(sociallogin.user, "username", "<new>"),
            provider_id,
            claim,
            sorted(extra_data.keys()),
            groups,
        )

        # If the user already exists, sync permissions now
        if sociallogin.user and sociallogin.user.pk:
            logger.info(
                "Login for existing user %s via %s with groups: %s",
                sociallogin.user.username,
                provider_id,
                groups,
            )
            sync_idp_permissions(
                sociallogin.user, groups, request=request, provider=provider_id
            )

    def save_user(self, request, sociallogin, form=None):
        """Sync IdP groups after a new social user is created."""
        user = super().save_user(request, sociallogin, form)
        groups = getattr(request, "_idp_groups", [])
        provider_id = getattr(request, "_idp_provider", None)
        if groups:
            logger.info(
                "Login for new user %s via %s with groups: %s",
                user.username,
                provider_id,
                groups,
            )
            sync_idp_permissions(user, groups, request=request, provider=provider_id)
        return user
