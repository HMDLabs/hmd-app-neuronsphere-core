"""Tests for the Okta bearer path: verification, identity mapping, and composition.

Tokens are minted with FastMCP's own ``RSAKeyPair`` and verified against a static
public key, so nothing here touches a JWKS endpoint or any other network.
"""
import asyncio
import unittest

from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings
from fastmcp.server.auth import MultiAuth, RemoteAuthProvider
from fastmcp.server.auth.providers.jwt import RSAKeyPair

from deployments.models import MCPApiKey
from ns_mcp.auth import ApiKeyVerifier, build_auth_provider, build_okta_verifier
from ns_mcp.principal import AUTH_MODE_CLAIM, AUTH_MODE_OKTA, USER_ID_CLAIM

ISSUER = "https://example.okta.com/oauth2/default"
AUDIENCE = "api://neuronsphere"
BASE_URL = "https://gui.example.com"

_KEYS = RSAKeyPair.generate()


def okta_settings(**overrides):
    """Settings enabling the Okta path against the module's static test key."""
    values = {
        "MCP_OKTA_ENABLED": True,
        "MCP_OKTA_ISSUER": ISSUER,
        "MCP_OKTA_AUDIENCE": AUDIENCE,
        "MCP_OKTA_PUBLIC_KEY": _KEYS.public_key,
        "MCP_OKTA_JWKS_URI": "",
        "MCP_BASE_URL": BASE_URL,
        "MCP_API_KEYS_ENABLED": False,
    }
    values.update(overrides)
    return override_settings(**values)


def mint(
    subject="alice@example.com", uid=None, issuer=ISSUER, audience=AUDIENCE, **extra
):
    claims = dict(extra)
    if uid is not None:
        claims["uid"] = uid
    return _KEYS.create_token(
        subject=subject,
        issuer=issuer,
        audience=audience,
        additional_claims=claims or None,
    )


def link_okta_account(user, uid):
    """Give ``user`` the SocialAccount allauth would create on first login."""
    from allauth.socialaccount.models import SocialAccount

    return SocialAccount.objects.create(user=user, provider="okta", uid=uid)


class TestIdentityResolution(unittest.TestCase):
    """The claims -> Django user mapping, independent of any token."""

    def resolve(self, claims):
        from deployments.services.auth import resolve_user_for_okta_claims

        return resolve_user_for_okta_claims(claims)

    def test_uid_matches_the_social_account(self):
        user = User.objects.create_user("alice", email="alice@example.com")
        link_okta_account(user, "00uABC")
        self.assertEqual(
            self.resolve({"uid": "00uABC", "sub": "alice@example.com"}), user
        )

    def test_uid_wins_over_the_email_of_a_different_user(self):
        alice = User.objects.create_user("alice", email="alice@example.com")
        User.objects.create_user("bob", email="bob@example.com")
        link_okta_account(alice, "00uABC")
        # sub names bob, uid names alice; uid is authoritative.
        self.assertEqual(
            self.resolve({"uid": "00uABC", "sub": "bob@example.com"}), alice
        )

    def test_email_fallback_when_no_social_account_matches(self):
        user = User.objects.create_user("carol", email="Carol@Example.com")
        self.assertEqual(
            self.resolve({"uid": "00uUNKNOWN", "sub": "carol@example.com"}), user
        )

    def test_email_fallback_when_the_token_carries_no_uid(self):
        user = User.objects.create_user("dave", email="dave@example.com")
        self.assertEqual(self.resolve({"sub": "dave@example.com"}), user)

    def test_a_subject_that_is_not_an_email_is_not_looked_up(self):
        # An Okta user id in `sub` must never be matched against User.email.
        User.objects.create_user("erin", email="00uABC")
        self.assertIsNone(self.resolve({"sub": "00uABC"}))

    def test_no_match_returns_none(self):
        self.assertIsNone(
            self.resolve({"uid": "00uNOBODY", "sub": "nobody@example.com"})
        )

    def test_empty_claims_are_tolerated(self):
        self.assertIsNone(self.resolve({}))

    def test_uid_is_scoped_to_the_provider_the_issuer_names(self):
        """The same uid under two IdPs resolves to the right user, not either one.

        SocialAccount is unique on (provider, uid), so this row pair is legal, and
        an unscoped lookup would return whichever the database ordered first.
        """
        from allauth.socialaccount.models import SocialAccount

        alice = User.objects.create_user("alice", email="alice@example.com")
        bob = User.objects.create_user("bob", email="bob@example.com")
        SocialAccount.objects.create(user=alice, provider="okta", uid="shared-uid")
        SocialAccount.objects.create(user=bob, provider="acme-auth0", uid="shared-uid")

        providers = [
            {"provider_id": "okta", "server_url": "https://acme.okta.com"},
            {"provider_id": "acme-auth0", "server_url": "https://acme.auth0.com"},
        ]
        with override_settings(IDP_PROVIDERS=providers):
            self.assertEqual(
                self.resolve({"uid": "shared-uid", "iss": "https://acme.okta.com"}),
                alice,
            )
            self.assertEqual(
                self.resolve({"uid": "shared-uid", "iss": "https://acme.auth0.com"}),
                bob,
            )

    def test_issuer_matches_regardless_of_a_trailing_slash(self):
        alice = User.objects.create_user("alice", email="alice@example.com")
        link_okta_account(alice, "00uABC")
        providers = [{"provider_id": "okta", "server_url": "https://acme.okta.com/"}]
        with override_settings(IDP_PROVIDERS=providers):
            self.assertEqual(
                self.resolve({"uid": "00uABC", "iss": "https://acme.okta.com"}), alice
            )

    def test_an_unrecognised_issuer_falls_back_to_the_unscoped_lookup(self):
        """A single-provider deployment never sets IDP_PROVIDERS; it must still work."""
        alice = User.objects.create_user("alice", email="alice@example.com")
        link_okta_account(alice, "00uABC")
        with override_settings(IDP_PROVIDERS=[]):
            self.assertEqual(
                self.resolve({"uid": "00uABC", "iss": "https://elsewhere.test"}), alice
            )


class TestOktaUserVerifier(unittest.TestCase):
    """Verification plus the claims the rest of the pipeline depends on."""

    def verify(self, token):
        return asyncio.run(build_okta_verifier().verify_token(token))

    @okta_settings()
    def test_a_linked_user_is_resolved_and_tagged(self):
        user = User.objects.create_user("alice", email="alice@example.com")
        link_okta_account(user, "00uABC")

        access = self.verify(mint(uid="00uABC"))

        self.assertIsNotNone(access)
        self.assertEqual(access.claims[USER_ID_CLAIM], user.pk)
        self.assertEqual(access.claims[AUTH_MODE_CLAIM], AUTH_MODE_OKTA)
        # The NeuronSphere username, so the audit trail reads the same whichever
        # credential was presented.
        self.assertEqual(access.client_id, "alice")
        self.assertEqual(access.subject, "alice@example.com")

    @okta_settings()
    def test_the_email_fallback_resolves_over_the_transport_claims(self):
        user = User.objects.create_user("carol", email="carol@example.com")
        access = self.verify(mint(subject="carol@example.com"))
        self.assertEqual(access.claims[USER_ID_CLAIM], user.pk)

    @okta_settings()
    def test_an_unprovisioned_user_verifies_but_carries_no_user_id(self):
        # Deliberately not a 401: a valid token from someone who has never signed in
        # is a distinguishable, actionable state.
        access = self.verify(mint(uid="00uNOBODY", subject="nobody@example.com"))
        self.assertIsNotNone(access)
        self.assertNotIn(USER_ID_CLAIM, access.claims)
        self.assertEqual(access.claims[AUTH_MODE_CLAIM], AUTH_MODE_OKTA)

    @okta_settings()
    def test_an_unprovisioned_user_is_refused_by_resolve_principal(self):
        from fastmcp.exceptions import ToolError
        from ns_mcp.principal import resolve_principal

        access = self.verify(mint(uid="00uNOBODY", subject="nobody@example.com"))

        # resolve_principal reads a contextvar; drive it with the token directly.
        import ns_mcp.principal as principal_module

        original = principal_module.get_access_token
        principal_module.get_access_token = lambda: access
        try:
            with self.assertRaises(ToolError) as caught:
                resolve_principal()
        finally:
            principal_module.get_access_token = original
        self.assertIn("not linked to a NeuronSphere account", str(caught.exception))

    @okta_settings()
    def test_the_auth_mode_claim_is_always_set(self):
        # A missing mode claim defaults to "apikey" in resolve_principal, which would
        # silently send the caller's downstream request as the service account.
        for token in (mint(uid="00uNOBODY"), mint(uid="00uABC")):
            access = self.verify(token)
            self.assertEqual(access.claims[AUTH_MODE_CLAIM], AUTH_MODE_OKTA)

    @okta_settings()
    def test_a_wrong_audience_is_rejected(self):
        self.assertIsNone(self.verify(mint(audience="api://neuronsphere-services")))

    @okta_settings()
    def test_a_wrong_issuer_is_rejected(self):
        self.assertIsNone(self.verify(mint(issuer="https://attacker.example.com")))

    @okta_settings()
    def test_a_token_signed_by_another_key_is_rejected(self):
        other = RSAKeyPair.generate()
        token = other.create_token(
            subject="alice@example.com", issuer=ISSUER, audience=AUDIENCE
        )
        self.assertIsNone(self.verify(token))

    @okta_settings()
    def test_an_expired_token_is_rejected(self):
        token = _KEYS.create_token(
            subject="alice@example.com",
            issuer=ISSUER,
            audience=AUDIENCE,
            expires_in_seconds=-60,
        )
        self.assertIsNone(self.verify(token))

    @okta_settings()
    def test_garbage_is_rejected(self):
        for token in ("", "not-a-jwt", "a.b.c"):
            self.assertIsNone(self.verify(token))

    @okta_settings()
    def test_an_api_key_is_declined_without_touching_the_jwt_machinery(self):
        # MultiAuth tries this verifier first on every request, so the other
        # credential shape must be turned away before any verification work.
        verifier = build_okta_verifier()
        called = []

        async def fail(_token):
            called.append(_token)
            raise AssertionError("the JWT path must not run for an API key")

        verifier.load_access_token = fail
        self.assertIsNone(
            asyncio.run(verifier.verify_token(MCPApiKey.PREFIX + "x" * 32))
        )
        self.assertEqual(called, [])


class TestAuthProviderComposition(unittest.TestCase):
    """What ``build_auth_provider`` returns for each credential combination."""

    @okta_settings(MCP_API_KEYS_ENABLED=True)
    def test_both_credentials_compose_with_okta_as_the_server(self):
        provider = build_auth_provider()

        self.assertIsInstance(provider, MultiAuth)
        # Okta must be the server, not another verifier: MultiAuth delegates
        # get_routes only to its server, and those routes are the discovery document.
        self.assertIsInstance(provider.server, RemoteAuthProvider)
        self.assertEqual(len(provider.verifiers), 1)
        self.assertIsInstance(provider.verifiers[0], ApiKeyVerifier)

    @okta_settings()
    def test_okta_alone_is_a_remote_auth_provider(self):
        self.assertIsInstance(build_auth_provider(), RemoteAuthProvider)

    @override_settings(MCP_OKTA_ENABLED=False, MCP_API_KEYS_ENABLED=True)
    def test_api_keys_alone_are_unchanged(self):
        self.assertIsInstance(build_auth_provider(), ApiKeyVerifier)

    @override_settings(MCP_OKTA_ENABLED=False, MCP_API_KEYS_ENABLED=False, DEBUG=False)
    def test_no_credential_outside_debug_refuses_to_start(self):
        # This is the cloud configuration before Okta existed: mcpEnabled on,
        # mcpApiKeysEnabled off, DEBUG false. It must fail loudly, not serve.
        with self.assertRaises(RuntimeError) as caught:
            build_auth_provider()
        self.assertIn("MCP_OKTA_ENABLED", str(caught.exception))

    @override_settings(MCP_OKTA_ENABLED=False, MCP_API_KEYS_ENABLED=False, DEBUG=True)
    def test_no_credential_under_debug_is_unauthenticated(self):
        self.assertIsNone(build_auth_provider())

    @okta_settings(MCP_BASE_URL="")
    def test_okta_without_a_base_url_fails_with_a_clear_message(self):
        with self.assertRaises(ImproperlyConfigured) as caught:
            build_auth_provider()
        self.assertIn("MCP_BASE_URL", str(caught.exception))

    @override_settings(
        MCP_OKTA_ENABLED=True,
        MCP_OKTA_ISSUER="",
        MCP_OKTA_PUBLIC_KEY="",
        MCP_API_KEYS_ENABLED=True,
    )
    def test_the_flag_without_a_key_source_fails_loudly(self):
        # base.py already gates MCP_OKTA_ENABLED on having a key source. If something
        # overrides that, the server must refuse rather than quietly serving with only
        # the weaker credential enabled.
        with self.assertRaises(ImproperlyConfigured) as caught:
            build_auth_provider()
        self.assertIn("no key to verify tokens with", str(caught.exception))


class TestProtectedResourceMetadata(unittest.TestCase):
    """The RFC 9728 document, and the challenge that points at it."""

    def routes_for(self, provider):
        from django.conf import settings

        return provider.get_well_known_routes(mcp_path=settings.MCP_MOUNT_PATH)

    @okta_settings()
    def test_the_metadata_path_has_no_trailing_slash(self):
        # The MCP app is served internally at "/" and mounted at /mcp, so FastMCP's
        # default composition would advertise ".../oauth-protected-resource/mcp/".
        paths = [r.path for r in self.routes_for(build_auth_provider())]
        self.assertIn("/.well-known/oauth-protected-resource/mcp", paths)

    @okta_settings(MCP_API_KEYS_ENABLED=True)
    def test_the_composed_provider_advertises_the_same_resource(self):
        provider = build_auth_provider()
        paths = [r.path for r in self.routes_for(provider)]
        self.assertIn("/.well-known/oauth-protected-resource/mcp", paths)
        # The 401 challenge is built from the OUTER provider's resource URL. If it
        # disagreed with the route above, discovery would 404.
        from mcp.server.auth.routes import build_resource_metadata_url

        challenge = build_resource_metadata_url(provider._get_resource_url("/"))
        self.assertEqual(
            str(challenge),
            f"{BASE_URL}/.well-known/oauth-protected-resource/mcp",
        )

    @override_settings(MCP_OKTA_ENABLED=False, MCP_API_KEYS_ENABLED=True)
    def test_an_api_key_only_deployment_advertises_nothing(self):
        self.assertEqual(self.routes_for(build_auth_provider()), [])


class TestDownstreamTokenMode(unittest.TestCase):
    """Which identity the hmd-ms-deployment request carries."""

    def build(self, principal):
        from ns_mcp.tooling import _build_client

        return _build_client(principal)

    def okta_principal(self):
        from ns_mcp.principal import Principal

        return Principal(
            user_id=1,
            username="alice",
            auth_mode=AUTH_MODE_OKTA,
            raw_token="user-token",
        )

    def api_key_principal(self):
        from ns_mcp.principal import AUTH_MODE_API_KEY, Principal

        return Principal(
            user_id=1,
            username="alice",
            auth_mode=AUTH_MODE_API_KEY,
            raw_token="nsmcp_x",
        )

    @override_settings(MCP_DOWNSTREAM_TOKEN_MODE="passthrough")
    def test_passthrough_forwards_the_callers_own_token(self):
        self.assertEqual(self.build(self.okta_principal()).auth_token, "user-token")

    @override_settings(MCP_DOWNSTREAM_TOKEN_MODE="service")
    def test_service_mode_never_forwards_the_callers_token(self):
        self.assertNotEqual(self.build(self.okta_principal()).auth_token, "user-token")

    @override_settings(MCP_DOWNSTREAM_TOKEN_MODE="passthrough")
    def test_an_api_key_never_forwards_its_key(self):
        # There is no user token behind an API key; it must not be sent downstream.
        self.assertNotEqual(self.build(self.api_key_principal()).auth_token, "nsmcp_x")


class TestCheckMcpTokenCommand(unittest.TestCase):
    """The operator-facing diagnostic. Its job is to answer, not to crash."""

    def run_command(self, token):
        import io as _io

        from django.core.management import call_command

        out = _io.StringIO()
        call_command("check_mcp_token", token=token, stdout=out)
        return out.getvalue()

    @okta_settings()
    def test_it_reports_the_resolved_user_and_the_downstream_caveat(self):
        user = User.objects.create_user("alice", email="alice@example.com")
        link_okta_account(user, "00uABC")

        output = self.run_command(mint(uid="00uABC", cid="0oaWEBAPP"))

        # `cid` is the claim the whole downstream question turns on, so it has to be
        # in the output whether or not anything else is.
        self.assertIn("cid", output)
        self.assertIn("0oaWEBAPP", output)
        self.assertIn("VERIFIED", output)
        self.assertIn("alice", output)

    @okta_settings()
    def test_a_bearer_prefix_is_tolerated(self):
        output = self.run_command("Bearer " + mint(uid="00uNOBODY"))
        self.assertIn("VERIFIED", output)
        self.assertIn("no NeuronSphere account", output)

    @okta_settings()
    def test_a_rejected_token_says_so_rather_than_raising(self):
        output = self.run_command(mint(audience="api://wrong"))
        self.assertIn("REJECTED", output)

    @okta_settings()
    def test_something_that_is_not_a_jwt_is_a_clean_error(self):
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            self.run_command("not-a-jwt")
