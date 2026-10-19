"""The gateway's IdP-issued upstream tokens (``ns_mcp.gateway.idp``, NERD012 SPEC007).

A service-mode upstream is locked down by accepting only tokens the identity
provider issued to the gateway's own client, scoped to that upstream's environment.
These tests stand in for the IdP with an ``httpx.MockTransport``.
"""
import asyncio
import unittest
from urllib.parse import parse_qs

import httpx

from ns_mcp.gateway.idp import IdpTokenSource
from ns_mcp.gateway.upstream import GatewayCallError

ISSUER = "https://idp.example.com/oauth2/default"
TOKEN_URL = "https://idp.example.com/oauth2/default/v1/token"


class FakeIdp:
    """Answers OIDC discovery and client-credentials requests, recording each."""

    def __init__(self, expires_in=3600, status=200):
        self.expires_in = expires_in
        self.status = status
        self.token_requests = []
        self.discovery_requests = 0
        self.issued = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/.well-known/openid-configuration"):
            self.discovery_requests += 1
            return httpx.Response(
                200, json={"issuer": ISSUER, "token_endpoint": TOKEN_URL}
            )
        if str(request.url) == TOKEN_URL:
            form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
            self.token_requests.append(form)
            if self.status != 200:
                return httpx.Response(self.status, json={"error": "invalid_client"})
            self.issued += 1
            return httpx.Response(
                200,
                json={
                    "access_token": f"tok-{form.get('scope')}-{self.issued}",
                    "token_type": "Bearer",
                    "expires_in": self.expires_in,
                },
            )
        return httpx.Response(404)

    def transport(self):
        return httpx.MockTransport(self.handler)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _source(idp, clock=None, **overrides):
    kwargs = dict(
        issuer=ISSUER,
        client_id="gateway-client",
        client_secret="gateway-secret",
        scope_template="mcp:{environment}",
        transport=idp.transport(),
        clock=clock or Clock(),
    )
    kwargs.update(overrides)
    return IdpTokenSource(**kwargs)


class TestIdpTokenSource(unittest.TestCase):
    def test_requests_a_client_credentials_token_scoped_to_the_environment(self):
        idp = FakeIdp()
        token = asyncio.run(_source(idp).token("prod"))

        self.assertEqual(token, "tok-mcp:prod-1")
        (form,) = idp.token_requests
        self.assertEqual(form["grant_type"], "client_credentials")
        self.assertEqual(form["scope"], "mcp:prod")
        self.assertEqual(form["client_id"], "gateway-client")
        self.assertEqual(form["client_secret"], "gateway-secret")
        self.assertNotIn("audience", form)

    def test_the_token_endpoint_comes_from_oidc_discovery_once(self):
        idp = FakeIdp()
        source = _source(idp)
        asyncio.run(source.token("dev"))
        asyncio.run(source.token("test"))
        self.assertEqual(idp.discovery_requests, 1)

    def test_an_explicit_token_url_skips_discovery(self):
        idp = FakeIdp()
        asyncio.run(_source(idp, issuer="", token_url=TOKEN_URL).token("dev"))
        self.assertEqual(idp.discovery_requests, 0)
        self.assertEqual(len(idp.token_requests), 1)

    def test_audience_is_sent_when_configured(self):
        # Auth0 picks the API by an `audience` parameter; Okta by the issuer.
        idp = FakeIdp()
        asyncio.run(_source(idp, audience="api://neuronsphere-mcp").token("dev"))
        self.assertEqual(idp.token_requests[0]["audience"], "api://neuronsphere-mcp")

    def test_one_cached_token_per_environment(self):
        idp = FakeIdp()
        source = _source(idp)

        async def scenario():
            return [
                await source.token("dev"),
                await source.token("dev"),
                await source.token("prod"),
            ]

        dev1, dev2, prod = asyncio.run(scenario())
        self.assertEqual(dev1, dev2)
        self.assertNotEqual(dev1, prod)
        self.assertEqual(
            [r["scope"] for r in idp.token_requests], ["mcp:dev", "mcp:prod"]
        )

    def test_a_token_is_replaced_before_it_expires(self):
        idp = FakeIdp(expires_in=600)
        clock = Clock()
        source = _source(idp, clock=clock)

        first = asyncio.run(source.token("dev"))
        clock.now += 600 - 61  # inside the 60s refresh margin? not yet
        self.assertEqual(asyncio.run(source.token("dev")), first)
        clock.now += 2  # now within 60s of expiry
        self.assertNotEqual(asyncio.run(source.token("dev")), first)

    def test_a_short_lived_token_is_refreshed_at_half_its_life(self):
        idp = FakeIdp(expires_in=60)
        clock = Clock()
        source = _source(idp, clock=clock)
        first = asyncio.run(source.token("dev"))
        clock.now += 31
        self.assertNotEqual(asyncio.run(source.token("dev")), first)

    def test_an_idp_refusal_is_a_gateway_error_without_the_secret(self):
        idp = FakeIdp(status=401)
        with self.assertRaises(GatewayCallError) as ctx:
            asyncio.run(_source(idp).token("dev"))
        self.assertIn("dev", str(ctx.exception))
        self.assertNotIn("gateway-secret", str(ctx.exception))

    def test_a_response_without_an_access_token_is_an_error(self):
        def handler(request):
            return httpx.Response(200, json={"token_type": "Bearer"})

        source = IdpTokenSource(
            issuer="",
            token_url=TOKEN_URL,
            client_id="c",
            client_secret="s",
            transport=httpx.MockTransport(handler),
        )
        with self.assertRaises(GatewayCallError):
            asyncio.run(source.token("dev"))

    def test_configured_needs_a_client_and_somewhere_to_get_tokens(self):
        idp = FakeIdp()
        self.assertTrue(_source(idp).configured)
        self.assertFalse(_source(idp, client_secret="").configured)
        self.assertFalse(_source(idp, client_id="").configured)
        self.assertFalse(_source(idp, issuer="", token_url="").configured)

    def test_from_settings_reads_the_gateway_client(self):
        from django.test import override_settings

        with override_settings(
            MCP_GATEWAY_IDP_ISSUER=ISSUER,
            MCP_GATEWAY_IDP_TOKEN_URL="",
            MCP_GATEWAY_IDP_CLIENT_ID="gateway-client",
            MCP_GATEWAY_IDP_CLIENT_SECRET="gateway-secret",
            MCP_GATEWAY_IDP_AUDIENCE="",
            MCP_GATEWAY_IDP_SCOPE="mcp:{environment}",
        ):
            self.assertTrue(IdpTokenSource.from_settings().configured)
        with override_settings(MCP_GATEWAY_IDP_CLIENT_ID=""):
            self.assertFalse(IdpTokenSource.from_settings().configured)

    def test_an_unconfigured_source_refuses(self):
        with self.assertRaises(GatewayCallError):
            asyncio.run(_source(FakeIdp(), client_id="").token("dev"))

    def test_discovery_trims_a_trailing_slash_on_the_issuer(self):
        # Auth0 issuers end in "/".
        seen = []

        def handler(request):
            seen.append(str(request.url))
            if "openid-configuration" in str(request.url):
                return httpx.Response(200, json={"token_endpoint": TOKEN_URL})
            return httpx.Response(200, json={"access_token": "t", "expires_in": 60})

        source = IdpTokenSource(
            issuer="https://tenant.auth0.com/",
            client_id="c",
            client_secret="s",
            transport=httpx.MockTransport(handler),
        )
        asyncio.run(source.token("dev"))
        self.assertEqual(
            seen[0], "https://tenant.auth0.com/.well-known/openid-configuration"
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
