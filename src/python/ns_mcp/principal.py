"""The authenticated caller behind an MCP request.

``Principal`` is a plain snapshot taken from the validated access token in async
context -- it holds no Django objects, so it can be built without touching the
ORM. The Django ``User`` is loaded later, inside the threadpool hop.
"""
from dataclasses import dataclass

from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_access_token

#: Set on ``AccessToken.claims`` by each verifier so tools can tell how the
#: caller authenticated without re-inspecting the raw token.
AUTH_MODE_CLAIM = "ns_auth_mode"
USER_ID_CLAIM = "ns_user_id"

AUTH_MODE_API_KEY = "apikey"
AUTH_MODE_OKTA = "okta"


@dataclass(frozen=True)
class Principal:
    """Who is calling, and with what credential."""

    user_id: int
    username: str
    auth_mode: str
    raw_token: str
    subject: str = ""

    @property
    def is_api_key(self) -> bool:
        return self.auth_mode == AUTH_MODE_API_KEY


def resolve_principal() -> Principal:
    """Build a ``Principal`` from the current request's validated access token.

    Safe to call on the event loop: it only reads contextvars. FastMCP rejects
    unauthenticated requests with a 401 before a tool runs, so the missing-token
    branch here is defensive rather than the normal path.
    """
    token = get_access_token()
    if token is None:
        raise ToolError(
            "Unauthenticated. Send an Authorization: Bearer <token> header."
        )

    claims = token.claims or {}
    user_id = claims.get(USER_ID_CLAIM)
    if user_id is None:
        raise ToolError(
            "This credential is not linked to a NeuronSphere account. Sign in to "
            "the Deployment GUI once so your account and environment permissions "
            "are provisioned."
        )

    return Principal(
        user_id=user_id,
        username=token.client_id or "",
        auth_mode=claims.get(AUTH_MODE_CLAIM, AUTH_MODE_API_KEY),
        raw_token=token.token,
        subject=token.subject or "",
    )
