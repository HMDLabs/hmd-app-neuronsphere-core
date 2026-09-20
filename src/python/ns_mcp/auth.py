"""Bearer-token verification for the MCP server.

Two credentials are accepted, and ``build_auth_provider`` is the single place either
is wired:

* an Okta bearer, verified against the same authorization server the GUI logs in
  against (``JWTVerifier`` over JWKS) and resolved to a NeuronSphere account. This is
  the cloud credential.
* a platform-issued ``nsmcp_`` key (``MCPApiKey``), for local development, bender, and
  CI, where no Okta token exists.

When both are enabled they are composed with ``MultiAuth``. The Okta side goes in as
``server=`` rather than as another verifier for a concrete reason: ``MultiAuth``
delegates ``get_routes`` only to its server, and those routes are the RFC 9728
protected-resource document an MCP client reads to discover where to get a token. A
verifier contributes no routes, so an Okta side passed as ``verifiers=[...]`` would
authenticate but never advertise itself.
"""
import logging

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from fastmcp.server.auth import (
    AccessToken,
    JWTVerifier,
    MultiAuth,
    RemoteAuthProvider,
    TokenVerifier,
)

from .context import run_in_django
from .principal import (
    AUTH_MODE_API_KEY,
    AUTH_MODE_CLAIM,
    AUTH_MODE_OKTA,
    USER_ID_CLAIM,
)

logger = logging.getLogger(__name__)


class ApiKeyVerifier(TokenVerifier):
    """Validate a platform-issued ``nsmcp_`` key against ``MCPApiKey``.

    The lookup is a database query, so it runs in a worker thread rather than on
    the event loop. Returning ``None`` for every failure mode -- unknown,
    revoked, expired, malformed -- keeps those indistinguishable to the caller.
    """

    async def verify_token(self, token: str) -> AccessToken | None:
        key = await run_in_django(self._authenticate, token)
        if key is None:
            return None
        return AccessToken(
            token=token,
            client_id=key["username"],
            scopes=[],
            subject=key["username"],
            claims={
                AUTH_MODE_CLAIM: AUTH_MODE_API_KEY,
                USER_ID_CLAIM: key["user_id"],
                "key_name": key["name"],
            },
        )

    @staticmethod
    def _authenticate(token: str):
        """Resolve the key to a plain dict. Runs in the worker thread.

        Returns primitives rather than the model instance so nothing carrying a
        database connection escapes the thread.
        """
        from deployments.models import MCPApiKey

        key = MCPApiKey.authenticate(token)
        if key is None:
            return None
        return {
            "user_id": key.user_id,
            "username": key.user.username,
            "name": key.name,
        }


class OktaUserVerifier(JWTVerifier):
    """An Okta bearer, verified by signature and then resolved to a Django user.

    ``JWTVerifier`` does the cryptography and the ``iss``/``aud``/``exp`` checks. This
    subclass adds the half that is specific to this application: turning a verified
    token into the NeuronSphere account whose environment permissions the tools apply.

    A token that verifies but matches no account is *not* a 401. It is returned with
    ``ns_auth_mode`` set and ``ns_user_id`` absent, which ``resolve_principal`` turns
    into an actionable "sign in to the Deployment GUI once" error. Only a token that
    fails verification is indistinguishable from any other bad credential.
    """

    async def verify_token(self, token: str) -> AccessToken | None:
        from deployments.models import MCPApiKey

        # An API key is not a JWT. Under MultiAuth this verifier is tried first on
        # every request, so declining the other credential shape up front keeps the
        # API-key path off the JWT machinery entirely.
        if not token or token.startswith(MCPApiKey.PREFIX):
            return None

        access = await super().verify_token(token)
        if access is None:
            return None

        user = await run_in_django(self._resolve_user, access.claims)

        # ns_auth_mode is set on BOTH branches. resolve_principal defaults a missing
        # mode to "apikey", which would quietly route an Okta caller's downstream
        # request to the service account instead of forwarding their own token.
        claims = dict(access.claims or {})
        claims[AUTH_MODE_CLAIM] = AUTH_MODE_OKTA
        if user is not None:
            claims[USER_ID_CLAIM] = user["id"]

        return AccessToken(
            token=access.token,
            # The NeuronSphere username, matching what ApiKeyVerifier reports, so the
            # audit trail reads the same whichever credential was used. The OAuth
            # client id stays available on the claims as `cid`.
            client_id=(user or {}).get("username") or access.client_id,
            scopes=access.scopes,
            expires_at=access.expires_at,
            resource=access.resource,
            subject=access.subject or claims.get("sub") or "",
            claims=claims,
        )

    @staticmethod
    def _resolve_user(claims: dict):
        """Resolve the token's claims to ``{"id", "username"}``. Runs in the thread.

        Returns primitives rather than the ``User`` so nothing holding a database
        connection escapes the worker thread.
        """
        from deployments.services.auth import resolve_user_for_okta_claims

        user = resolve_user_for_okta_claims(claims)
        if user is None:
            return None
        return {"id": user.pk, "username": user.username}


class _FixedResourceUrl:
    """Advertise the resource at its public URL rather than at the inner mount path.

    The MCP app is served internally at ``/`` and mounted under ``MCP_MOUNT_PATH`` by
    the ASGI router, so FastMCP's default composition appends that inner ``/`` and
    produces ``<origin>/mcp/`` -- a resource URL, and therefore a metadata path, with a
    trailing slash the real endpoint does not have. The public URL is known up front,
    so use it verbatim; that also keeps the 401 challenge (computed from the outer
    provider) and the metadata route (created by the inner one) in agreement.
    """

    def _get_resource_url(self, path: str | None = None):
        return self.resource_base_url or self.base_url


class NsRemoteAuthProvider(_FixedResourceUrl, RemoteAuthProvider):
    """``RemoteAuthProvider`` with a fixed, mount-independent resource URL."""


class NsMultiAuth(_FixedResourceUrl, MultiAuth):
    """``MultiAuth`` with a fixed, mount-independent resource URL."""


def build_okta_verifier() -> OktaUserVerifier | None:
    """The Okta verifier described by settings, or ``None`` when it is disabled."""
    if not getattr(settings, "MCP_OKTA_ENABLED", False):
        return None

    # JWTVerifier takes one key source or the other, never both. The static key is the
    # offline path (tests); JWKS is what a real deployment uses.
    if settings.MCP_OKTA_PUBLIC_KEY:
        key_args = {"public_key": settings.MCP_OKTA_PUBLIC_KEY}
    elif settings.MCP_OKTA_JWKS_URI:
        key_args = {"jwks_uri": settings.MCP_OKTA_JWKS_URI}
    else:
        # base.py already gates MCP_OKTA_ENABLED on having a key source, so reaching
        # here means something overrode it. Say so, rather than letting JWTVerifier
        # raise a bare ValueError from deep inside FastMCP -- and do not quietly fall
        # back to API keys, which would turn a misconfiguration into a weaker server.
        raise ImproperlyConfigured(
            "MCP_OKTA_ENABLED is set but there is no key to verify tokens with. "
            "Set MCP_OKTA_ISSUER (OAUTH_PROVIDER_URL supplies it in a deployed pod), "
            "or MCP_OKTA_JWKS_URI, or MCP_OKTA_PUBLIC_KEY."
        )

    return OktaUserVerifier(
        issuer=settings.MCP_OKTA_ISSUER or None,
        audience=settings.MCP_OKTA_AUDIENCE or None,
        **key_args,
    )


def build_auth_provider():
    """Construct the auth provider for the MCP server, or ``None`` if disabled.

    ``None`` leaves the endpoint unauthenticated and is refused outside DEBUG --
    an unauthenticated MCP server exposes every environment's BOM to anyone who
    can reach the port.
    """
    okta = build_okta_verifier()
    api_key = (
        ApiKeyVerifier() if getattr(settings, "MCP_API_KEYS_ENABLED", False) else None
    )

    server = None
    if okta is not None:
        if not settings.MCP_BASE_URL:
            raise ImproperlyConfigured(
                "MCP_OKTA_ENABLED is set but MCP_BASE_URL is empty. The protected "
                "resource metadata document (RFC 9728) is built from it, so clients "
                "have no way to discover where to get a token without it. Set it to "
                "this server's public origin, e.g. https://gui.example.com."
            )
        server = NsRemoteAuthProvider(
            token_verifier=okta,
            authorization_servers=[settings.MCP_OKTA_ISSUER],
            base_url=settings.MCP_BASE_URL,
            resource_base_url=f"{settings.MCP_BASE_URL}{settings.MCP_MOUNT_PATH}",
            resource_name=settings.MCP_SERVER_NAME,
        )

    if server is not None and api_key is not None:
        return NsMultiAuth(server=server, verifiers=[api_key])
    if server is not None:
        return server
    if api_key is not None:
        return api_key

    if not settings.DEBUG:
        raise RuntimeError(
            "MCP_ENABLED is set but no authentication method is configured. "
            "Enable MCP_OKTA_ENABLED (with an issuer) or MCP_API_KEYS_ENABLED, "
            "or disable MCP_ENABLED."
        )
    logger.warning(
        "MCP server is running WITHOUT authentication (DEBUG only). "
        "Every environment BOM is readable by any caller."
    )
    return None
