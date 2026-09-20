"""Unit tests for MCPApiKey and the verifier that authenticates against it."""
import asyncio
import unittest

from django.contrib.auth.models import User
from django.utils import timezone

from deployments.models import MCPApiKey
from ns_mcp.auth import ApiKeyVerifier
from ns_mcp.principal import AUTH_MODE_CLAIM, USER_ID_CLAIM


class TestMCPApiKeyModel(unittest.TestCase):
    def setUp(self):
        self.user = User.objects.create_user("keyholder")

    def test_generate_returns_a_prefixed_key_and_stores_only_its_hash(self):
        key, raw = MCPApiKey.generate(self.user, "local dev")
        self.assertTrue(raw.startswith(MCPApiKey.PREFIX))
        self.assertEqual(key.key_hash, MCPApiKey.hash_key(raw))
        self.assertNotIn(raw, (key.key_hash, key.key_prefix))
        self.assertEqual(key.key_prefix, raw[: MCPApiKey.KEY_PREFIX_LENGTH])

    def test_each_key_is_distinct(self):
        _, first = MCPApiKey.generate(self.user, "a")
        _, second = MCPApiKey.generate(self.user, "b")
        self.assertNotEqual(first, second)

    def test_authenticate_resolves_the_owner(self):
        _, raw = MCPApiKey.generate(self.user, "local dev")
        self.assertEqual(MCPApiKey.authenticate(raw).user, self.user)

    def test_authenticate_stamps_last_used(self):
        key, raw = MCPApiKey.generate(self.user, "local dev")
        self.assertIsNone(key.last_used_at)
        MCPApiKey.authenticate(raw)
        key.refresh_from_db()
        self.assertIsNotNone(key.last_used_at)

    def test_unknown_key_returns_none(self):
        self.assertIsNone(MCPApiKey.authenticate(MCPApiKey.PREFIX + "nope"))

    def test_key_without_the_prefix_is_rejected_without_a_query(self):
        self.assertIsNone(MCPApiKey.authenticate("some-other-token"))

    def test_empty_and_none_are_rejected(self):
        self.assertIsNone(MCPApiKey.authenticate(""))
        self.assertIsNone(MCPApiKey.authenticate(None))

    def test_revoked_key_is_rejected(self):
        key, raw = MCPApiKey.generate(self.user, "local dev")
        key.is_active = False
        key.save()
        self.assertIsNone(MCPApiKey.authenticate(raw))

    def test_expired_key_is_rejected(self):
        _, raw = MCPApiKey.generate(
            self.user,
            "short lived",
            expires_at=timezone.now() - timezone.timedelta(seconds=1),
        )
        self.assertIsNone(MCPApiKey.authenticate(raw))

    def test_unexpired_key_is_accepted(self):
        _, raw = MCPApiKey.generate(
            self.user,
            "long lived",
            expires_at=timezone.now() + timezone.timedelta(days=1),
        )
        self.assertIsNotNone(MCPApiKey.authenticate(raw))


class TestSuppliedKey(unittest.TestCase):
    """The deploy-time bootstrap path: a key both sides already know.

    Used by the chart's createLocalMcpKey hook so bender can authenticate
    without parsing a key out of a pod's stdout. Only the hash is stored, so a
    supplied key is no less protected at rest than a generated one.
    """

    def setUp(self):
        self.user = User.objects.create_user("bootstrapper")

    def test_a_supplied_key_is_used_verbatim_and_still_only_hashed(self):
        raw = MCPApiKey.PREFIX + "a_known_local_bootstrap_key"
        key, returned = MCPApiKey.generate(self.user, "bender", raw_key=raw)
        self.assertEqual(returned, raw)
        self.assertEqual(key.key_hash, MCPApiKey.hash_key(raw))
        self.assertEqual(MCPApiKey.authenticate(raw).user, self.user)

    def test_a_key_without_the_prefix_is_refused(self):
        with self.assertRaises(ValueError) as ctx:
            MCPApiKey.generate(
                self.user, "bender", raw_key="not_prefixed_but_long_enough_key"
            )
        self.assertIn(MCPApiKey.PREFIX, str(ctx.exception))

    def test_a_short_key_is_refused(self):
        with self.assertRaises(ValueError):
            MCPApiKey.generate(self.user, "bender", raw_key=MCPApiKey.PREFIX + "short")

    def test_the_command_installs_a_supplied_key_without_printing_it(self):
        from io import StringIO

        from django.core.management import call_command

        raw = MCPApiKey.PREFIX + "a_known_local_bootstrap_key"
        out = StringIO()
        call_command(
            "create_mcp_api_key",
            user=self.user.username,
            name="bender",
            key=raw,
            stdout=out,
        )
        self.assertNotIn(raw, out.getvalue())
        self.assertEqual(MCPApiKey.authenticate(raw).user, self.user)

    def test_the_command_is_idempotent_with_if_not_exists(self):
        from io import StringIO

        from django.core.management import call_command

        raw = MCPApiKey.PREFIX + "a_known_local_bootstrap_key"
        for _ in range(2):
            call_command(
                "create_mcp_api_key",
                user=self.user.username,
                name="bender",
                key=raw,
                if_not_exists=True,
                stdout=StringIO(),
            )
        self.assertEqual(MCPApiKey.objects.filter(user=self.user).count(), 1)

    def test_a_malformed_key_fails_the_command_rather_than_the_deploy(self):
        from io import StringIO

        from django.core.management import call_command
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            call_command(
                "create_mcp_api_key",
                user=self.user.username,
                key="bogus",
                stdout=StringIO(),
            )


class TestApiKeyVerifier(unittest.TestCase):
    def setUp(self):
        self.user = User.objects.create_user("verified")
        self.verifier = ApiKeyVerifier()

    def _verify(self, token):
        return asyncio.run(self.verifier.verify_token(token))

    def test_valid_key_yields_a_token_carrying_the_user_id(self):
        _, raw = MCPApiKey.generate(self.user, "local dev")
        token = self._verify(raw)
        self.assertIsNotNone(token)
        self.assertEqual(token.claims[USER_ID_CLAIM], self.user.pk)
        self.assertEqual(token.claims[AUTH_MODE_CLAIM], "apikey")
        self.assertEqual(token.client_id, "verified")

    def test_every_failure_mode_is_indistinguishable(self):
        key, revoked = MCPApiKey.generate(self.user, "revoked")
        key.is_active = False
        key.save()
        for label, token in (
            ("unknown", MCPApiKey.PREFIX + "unknown"),
            ("revoked", revoked),
            ("wrong prefix", "bearer-ish-thing"),
            ("empty", ""),
        ):
            with self.subTest(case=label):
                self.assertIsNone(self._verify(token))


if __name__ == "__main__":
    unittest.main()
