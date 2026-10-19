"""The gateway's own identity, as tokens from the platform's IdP (NERD012 SPEC007).

A service-mode upstream is locked down by accepting only access tokens the identity
provider issued to the gateway's client, carrying the upstream's environment as a
scope. Every NeuronSphere environment shares one IdP tenant, so a user's own token
verifies everywhere; it is the client ID and the environment scope that set the
gateway's tokens apart.

Tokens come from the standard OAuth client-credentials grant, so any OIDC provider
works (Okta, Auth0, or a customer's own). The token endpoint is read from the
issuer's OIDC metadata unless configured outright, and ``audience`` is sent only when
set, since Auth0 needs it and Okta selects the API by its authorization server.

One token is cached per environment and replaced shortly before it expires. Each
gunicorn worker keeps its own cache, which costs at most a few token requests per
worker per hour.
"""
import logging
import time
from typing import Callable, Dict, Optional, Tuple

import httpx

from .upstream import GatewayCallError

logger = logging.getLogger(__name__)

#: Replace a token this long before it expires (or at half its life, if shorter).
REFRESH_MARGIN_SECONDS = 60
#: Assumed lifetime when the IdP does not say.
DEFAULT_EXPIRES_IN = 3600


class IdpTokenSource:
    """Client-credentials tokens for the gateway, one per environment."""

    def __init__(
        self,
        *,
        issuer: str = "",
        token_url: str = "",
        client_id: str = "",
        client_secret: str = "",
        audience: str = "",
        scope_template: str = "mcp:{environment}",
        timeout: float = 10.0,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._issuer = (issuer or "").rstrip("/")
        self._token_url = token_url or ""
        self._client_id = client_id or ""
        self._client_secret = client_secret or ""
        self._audience = audience or ""
        self._scope_template = scope_template
        self._timeout = timeout
        self._transport = transport
        self._clock = clock
        self._tokens: Dict[str, Tuple[str, float]] = {}

    @classmethod
    def from_settings(cls) -> "IdpTokenSource":
        from django.conf import settings

        return cls(
            issuer=settings.MCP_GATEWAY_IDP_ISSUER,
            token_url=settings.MCP_GATEWAY_IDP_TOKEN_URL,
            client_id=settings.MCP_GATEWAY_IDP_CLIENT_ID,
            client_secret=settings.MCP_GATEWAY_IDP_CLIENT_SECRET,
            audience=settings.MCP_GATEWAY_IDP_AUDIENCE,
            scope_template=settings.MCP_GATEWAY_IDP_SCOPE,
            timeout=settings.MCP_GATEWAY_CALL_TIMEOUT,
        )

    @property
    def configured(self) -> bool:
        return bool(
            self._client_id
            and self._client_secret
            and (self._token_url or self._issuer)
        )

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self._timeout, transport=self._transport)

    async def _resolve_token_url(self, client: httpx.AsyncClient) -> str:
        if self._token_url:
            return self._token_url
        url = f"{self._issuer}/.well-known/openid-configuration"
        try:
            response = await client.get(url)
            response.raise_for_status()
            token_url = response.json().get("token_endpoint") or ""
        except (httpx.HTTPError, ValueError) as exc:
            logger.error("MCP gateway: OIDC discovery failed at %s: %s", url, exc)
            token_url = ""
        if not token_url:
            raise GatewayCallError(
                "The gateway could not find the identity provider's token endpoint."
            )
        self._token_url = token_url
        return token_url

    async def token(self, environment: str) -> str:
        """A valid access token for calling ``environment``'s upstreams."""
        if not self.configured:
            raise GatewayCallError(
                "The gateway has no identity provider client configured for calling "
                "upstream servers; ask a platform administrator to set one up."
            )
        cached = self._tokens.get(environment)
        if cached and self._clock() < cached[1]:
            return cached[0]

        scope = self._scope_template.format(environment=environment)
        data = {
            "grant_type": "client_credentials",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "scope": scope,
        }
        if self._audience:
            data["audience"] = self._audience

        async with self._client() as client:
            token_url = await self._resolve_token_url(client)
            try:
                response = await client.post(token_url, data=data)
            except httpx.HTTPError as exc:
                logger.error("MCP gateway: token request failed: %s", exc)
                response = None
        payload = {}
        if response is not None and response.status_code == 200:
            try:
                payload = response.json()
            except ValueError:
                payload = {}
        elif response is not None:
            # The body is the IdP's error code and description; it holds no secret.
            logger.error(
                "MCP gateway: IdP refused a token for scope %s: %s %s",
                scope,
                response.status_code,
                response.text[:300],
            )

        access_token = payload.get("access_token")
        if not access_token:
            raise GatewayCallError(
                f"The gateway could not get a token for environment '{environment}' "
                "from the identity provider."
            )
        try:
            expires_in = float(payload.get("expires_in") or DEFAULT_EXPIRES_IN)
        except (TypeError, ValueError):
            expires_in = DEFAULT_EXPIRES_IN
        margin = min(REFRESH_MARGIN_SECONDS, expires_in / 2)
        self._tokens[environment] = (access_token, self._clock() + expires_in - margin)
        return access_token


_default: Optional[IdpTokenSource] = None


def default_token_source() -> IdpTokenSource:
    """The process-wide token source, built from settings on first use."""
    global _default
    if _default is None:
        _default = IdpTokenSource.from_settings()
    return _default
