"""Request middleware for keeping the app session in step with Okta.

``OktaTokenExpiryMiddleware`` closes the gap between the Django session (rolling,
8h) and the Okta access token (never refreshed once stored). Without it an
expired token keeps riding a still-valid session: ``@login_required`` passes, the
stale token is forwarded to downstream services, they answer 401/403, and views
surface that as an "Unauthorized" banner while the page renders anyway.

Instead, when the stored Okta access token has expired we destroy the stale
session and send the user back through Okta login (a silent SSO round-trip while
their Okta session is still alive, a full prompt once it isn't) so Okta stays the
source of truth and revoked/deprovisioned users can't keep operating.
"""
import logging
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import logout
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django_htmx.http import HttpResponseClientRedirect

from deployments.services.auth import get_okta_social_account, get_okta_social_token

logger = logging.getLogger(__name__)

# Treat a token as expired this many seconds before its real expiry, so a request
# doesn't set off downstream calls with a token about to die mid-flight.
TOKEN_EXPIRY_BUFFER_SECONDS = 30

# Path prefixes that must never be gated: the login/callback/logout flow lives
# under allauth's mount (gating it would loop on the redirect target itself), and
# health probes / static assets have no user token to check.
_EXEMPT_PREFIXES = ("/accounts/", "/admin/login/", "/health/")


class OktaTokenExpiryMiddleware:
    """Redirect Okta users to re-authenticate once their access token expires."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._token_expired(request):
            return self._reauth_response(request)
        return self.get_response(request)

    def _is_exempt(self, request):
        prefixes = _EXEMPT_PREFIXES
        static_url = getattr(settings, "STATIC_URL", None)
        if static_url:
            prefixes = prefixes + (static_url,)
        return request.path.startswith(prefixes)

    def _token_expired(self, request):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return False
        if self._is_exempt(request):
            return False

        token = get_okta_social_token(user)
        if token is None:
            # No token row. Force re-auth only for genuine Okta users; a local
            # username/password account (no Okta SocialAccount) must pass through.
            return get_okta_social_account(user) is not None

        if token.expires_at is None:
            # Expiry unknown — can't safely gate, so fail open and leave the
            # request alone (the pre-existing behavior for this edge case).
            return False

        deadline = timezone.now() + timedelta(seconds=TOKEN_EXPIRY_BUFFER_SECONDS)
        return token.expires_at <= deadline

    def _reauth_response(self, request):
        login_url = reverse("account_login")
        # get_full_path() is always a server-derived relative path, so it is
        # inherently same-origin; the check still rejects protocol-relative
        # ("//evil.com") smuggling before we echo it back as ?next=.
        next_url = request.get_full_path()
        if url_has_allowed_host_and_scheme(
            next_url, allowed_hosts=None, require_https=request.is_secure()
        ):
            login_url = f"{login_url}?{urlencode({'next': next_url})}"

        # Destroy the stale session so no authority survives the redirect.
        logout(request)
        logger.info("Okta access token expired; redirecting to re-authenticate")

        # An HTMX partial request must not swap the login page into the target
        # element — HX-Redirect makes htmx do a full-page navigation instead.
        if getattr(request, "htmx", False):
            return HttpResponseClientRedirect(login_url)
        return HttpResponseRedirect(login_url)
