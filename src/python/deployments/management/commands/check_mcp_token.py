"""Inspect a real Okta access token against this deployment's MCP configuration.

The question this answers cannot be answered from the code: does forwarding a caller's
own bearer to hmd-ms-deployment actually work here? That service verifies a *human*
caller against ``issuer=ns_issuer, audience=api://neuronsphere``, but only when the
token's ``cid`` is a trusted human client (``hmd_lib_auth.lambda_helper``); anything
else is treated as a service token and checked against a different audience entirely.

So run this against a token from the environment you are about to enable, and read the
`cid` line. If the client is not trusted downstream, the fix is to register it there
(hmd-lib-auth NERD001), not to switch MCP_DOWNSTREAM_TOKEN_MODE.
"""
import asyncio
import base64
import binascii
import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


def _decode_unverified(token: str) -> dict:
    """The token's claims WITHOUT verifying anything. Diagnostics only."""
    parts = token.split(".")
    if len(parts) != 3:
        raise CommandError(
            "That does not look like a JWT (expected three dot-separated segments)."
        )
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload))
    except (binascii.Error, ValueError) as exc:
        raise CommandError(f"Could not decode the token payload: {exc}") from None


class Command(BaseCommand):
    help = "Inspect an Okta access token and report how the MCP server would treat it."

    def add_arguments(self, parser):
        parser.add_argument(
            "--token",
            required=True,
            help="The raw access token (no 'Bearer ' prefix).",
        )

    def handle(self, *args, **options):
        from ns_mcp.auth import build_okta_verifier

        token = options["token"].strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()

        claims = _decode_unverified(token)

        self.stdout.write("Token claims (unverified):")
        for name in ("iss", "aud", "cid", "uid", "sub", "scp", "exp"):
            if name in claims:
                self.stdout.write(f"  {name:>4} = {claims[name]!r}")

        self.stdout.write("")
        self.stdout.write("This deployment expects:")
        self.stdout.write(f"  issuer   = {settings.MCP_OKTA_ISSUER!r}")
        self.stdout.write(f"  audience = {settings.MCP_OKTA_AUDIENCE!r}")
        self.stdout.write(f"  jwks_uri = {settings.MCP_OKTA_JWKS_URI!r}")

        verifier = build_okta_verifier()
        if verifier is None:
            raise CommandError(
                "MCP_OKTA_ENABLED is off (or no issuer is configured), so there is "
                "nothing to verify against. Set MCP_OKTA_ENABLED and MCP_OKTA_ISSUER."
            )

        self.stdout.write("")
        access = asyncio.run(verifier.verify_token(token))
        if access is None:
            self.stdout.write(
                self.style.ERROR(
                    "REJECTED. Signature, issuer, audience, or expiry did not match. "
                    "Compare the two blocks above."
                )
            )
            return

        from ns_mcp.principal import USER_ID_CLAIM

        user_id = (access.claims or {}).get(USER_ID_CLAIM)
        if user_id is None:
            self.stdout.write(
                self.style.WARNING(
                    "VERIFIED, but it maps to no NeuronSphere account. The holder must "
                    "sign in to the Deployment GUI once so a SocialAccount and their "
                    "environment permissions exist."
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"VERIFIED as {access.client_id!r} (user id {user_id}). "
                "MCP tools will apply that user's environment permissions."
            )
        )
        self.stdout.write(
            "Downstream: this token is forwarded to hmd-ms-deployment verbatim under "
            f"MCP_DOWNSTREAM_TOKEN_MODE={settings.MCP_DOWNSTREAM_TOKEN_MODE!r}. "
            "That is only accepted there if the `cid` above is a trusted human client."
        )
