"""Authentication services for API calls."""
import logging
import os
from typing import Optional

import httpx
from django.core.cache import cache

logger = logging.getLogger(__name__)


class AuthTokenManager:
    """Manages authentication tokens for API calls."""

    CACHE_KEY = "deployment_api_token"
    TOKEN_BUFFER_SECONDS = 300  # Refresh 5 minutes before expiry

    def __init__(self):
        """Initialize the token manager."""
        self.okta_issuer = os.environ.get("OAUTH_PROVIDER_URL")
        self.client_id = os.environ.get("SERVICE_CLIENT_ID")
        self.client_secret = os.environ.get("SERVICE_CLIENT_SECRET")

    def get_token(self) -> Optional[str]:
        """Get valid auth token, refreshing if needed.

        Returns:
            Bearer token string or None if not configured/available
        """
        # Check cache first
        cached = cache.get(self.CACHE_KEY)
        if cached:
            return cached

        # Obtain new token
        token = self._fetch_new_token()
        if token:
            # Cache token with appropriate TTL (1 hour minus buffer)
            cache.set(self.CACHE_KEY, token, timeout=3600 - self.TOKEN_BUFFER_SECONDS)

        return token

    def _fetch_new_token(self) -> Optional[str]:
        """Fetch new token from Okta.

        Returns:
            Access token string or None
        """
        if not all([self.okta_issuer, self.client_id, self.client_secret]):
            logger.debug("OAuth credentials not configured, skipping token fetch")
            return None

        try:
            response = httpx.post(
                f"{self.okta_issuer}/v1/token",
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "scope": "service",
                    "grant_type": "client_credentials",
                },
                timeout=10,
            )

            if response.status_code == 200:
                token = response.json().get("access_token")
                logger.info("Successfully obtained new API token")
                return token
            else:
                logger.error(f"Failed to obtain token: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Error fetching auth token: {e}")
            return None

    def clear_token(self) -> None:
        """Clear cached token (force refresh on next request)."""
        cache.delete(self.CACHE_KEY)
        logger.debug("Cleared cached API token")


# Singleton instance
token_manager = AuthTokenManager()


def api_client_class():
    """The service client class -- settings.DEPLOYMENT_API_CLIENT_CLASS, resolved once.

    An extra app names a subclass here to add the routes its own service serves.
    """
    from importlib import import_module

    from django.conf import settings

    from .api_client import DeploymentAPIClient

    dotted = getattr(settings, "DEPLOYMENT_API_CLIENT_CLASS", "")
    if not dotted:
        return DeploymentAPIClient
    module_name, _, class_name = dotted.rpartition(".")
    return getattr(import_module(module_name), class_name)


def get_api_client():
    """Factory function to get configured API client.

    Returns:
        The configured client class (see api_client_class) with the service
        auth token if available
    """
    token = token_manager.get_token()
    return api_client_class()(auth_token=token)


def get_okta_social_token(user):
    """Return the user's stored IdP ``SocialToken`` row, or ``None``.

    Shared by ``get_api_client_for_request`` and the token-expiry middleware so
    both agree on which token represents the user's SSO session. The row's
    ``token`` is the access token forwarded downstream and ``expires_at`` is its
    expiry (populated by allauth from the provider's ``expires_in``).

    Not filtered by provider: the GUI registers one allauth app per configured
    IdP, so the provider id varies per deployment (``okta``, ``acme-auth0``, a
    customer's own). A user has at most one social account here, and filtering on
    a hardcoded ``okta`` would silently forward no token for everyone else --
    falling back to the service account and losing per-user authorization
    downstream.
    """
    from allauth.socialaccount.models import SocialToken
    from django.db.models import F

    # Ordered, not just .first(): a user who has linked two IdPs has two rows, and
    # an unordered .first() would forward whichever the database happened to return
    # -- possibly an expired token while a live one sits beside it. Latest expiry
    # wins; rows with no expiry sort last, and the newest row breaks a tie.
    return (
        SocialToken.objects.filter(account__user=user)
        .select_related("account")
        .order_by(F("expires_at").desc(nulls_last=True), "-id")
        .first()
    )


def get_okta_social_account(user):
    """Return the user's SSO ``SocialAccount``, or ``None``.

    Distinguishes a genuine SSO user — whose expired or missing token should
    force re-authentication — from a local username/password account (dev only,
    when ``SOCIALACCOUNT_ONLY`` is off), which must pass through untouched.
    Provider-agnostic for the same reason as ``get_okta_social_token``.
    """
    from allauth.socialaccount.models import SocialAccount

    return SocialAccount.objects.filter(user=user).order_by("-id").first()


def provider_id_for_issuer(issuer):
    """The configured ``provider_id`` whose issuer is ``issuer``, or ``None``.

    ``SocialAccount`` is unique on *(provider, uid)*, not on ``uid`` alone, so a
    lookup by uid needs the provider to be unambiguous. The token's ``iss`` is the
    only thing that identifies which IdP minted it, and it has already been
    verified by the time any caller gets here.

    Compared with the trailing slash normalised away, since an issuer is routinely
    configured with one and asserted without it (or the reverse).
    """
    issuer = (issuer or "").rstrip("/")
    if not issuer:
        return None
    from django.conf import settings

    for provider in getattr(settings, "IDP_PROVIDERS", []) or []:
        if (provider.get("server_url") or "").rstrip("/") == issuer:
            return provider.get("provider_id")
    return None


def resolve_user_for_okta_claims(claims: dict):
    """Map a verified Okta access token's claims to a Django ``User``, or ``None``.

    The load-bearing join is ``uid``, not ``sub``. allauth stores the *ID token's*
    ``sub`` -- the Okta user id, ``00u...`` -- in ``SocialAccount.uid``, while an
    *access* token's ``sub`` is the user's email. Matching on ``sub`` first would
    therefore miss every user.

    ``sub`` is still worth a second look: an authorization server that does not emit
    ``uid`` on access tokens would otherwise strand every caller. Issuer and audience
    are already verified by the time this runs, so the email fallback cannot admit an
    identity from another tenant.

    Returns ``None`` when the token is valid but belongs to nobody here; the caller
    turns that into an actionable "sign in to the GUI once" message rather than a 401.
    """
    from allauth.socialaccount.models import SocialAccount
    from django.contrib.auth.models import User

    uid = (claims or {}).get("uid")
    if uid:
        # Scoped by the provider the verified issuer names, not by a hardcoded
        # "okta" -- which would strand users on a differently-named IdP -- and not
        # unscoped either: SocialAccount is unique on (provider, uid), so two IdPs
        # may legitimately carry the same uid, and an unscoped lookup could resolve
        # a token from one provider onto the other's user.
        #
        # An issuer that matches no configured provider falls back to the unscoped
        # lookup: single-provider deployments that never set IDP_PROVIDERS (and the
        # tests that drive this function directly) have nothing to match against,
        # and there is only one provider's accounts to find in that case anyway.
        provider_id = provider_id_for_issuer((claims or {}).get("iss"))
        accounts = SocialAccount.objects.filter(uid=uid)
        if provider_id:
            accounts = accounts.filter(provider=provider_id)
        account = accounts.select_related("user").first()
        if account is not None:
            return account.user

    subject = (claims or {}).get("sub") or ""
    if "@" in subject:
        user = User.objects.filter(email__iexact=subject).first()
        if user is not None:
            logger.info(
                "Okta token resolved to %s by email; no SocialAccount matched uid=%r. "
                "The authorization server may not be emitting a uid claim.",
                user.username,
                uid,
            )
            return user

    logger.info("Okta token matched no NeuronSphere account (uid=%r)", uid)
    return None


def get_api_client_for_request(request):
    """Return an API client bound to the current user's Okta access token.

    Falls back to the service-account token when no authenticated user or
    SocialToken is available.
    """
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        social_token = get_okta_social_token(user)
        if social_token and social_token.token:
            return api_client_class()(auth_token=social_token.token)
        logger.warning(
            "No Okta SocialToken for user %s; falling back to service token",
            user.username,
        )

    return get_api_client()
