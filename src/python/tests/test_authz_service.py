"""Unit tests for the transport-independent authorization service.

These run against the real permission models rather than stubs: the whole point
of ``services.authz`` is that the GUI decorators and the MCP tools reach the
same decision, and a stub would only prove the stub agrees with itself.
"""
import unittest

from django.contrib.auth.models import User

from deployments.models import DeploymentSetPermission, UserEnvironmentPermission
from deployments.services.authz import (
    DeploymentSetAccessDenied,
    EnvironmentAccessDenied,
    assert_deployment_set_access,
    assert_environment_access,
    user_has_deployment_set_access,
    user_has_environment_access,
)


class TestEnvironmentAccess(unittest.TestCase):
    def setUp(self):
        self.viewer = User.objects.create_user("authz_viewer")
        self.deployer = User.objects.create_user("authz_deployer")
        self.root = User.objects.create_user("authz_root", is_superuser=True)
        UserEnvironmentPermission.objects.create(
            user=self.viewer, environment="dev", role="viewer"
        )
        UserEnvironmentPermission.objects.create(
            user=self.deployer, environment="dev", role="deployer"
        )

    def test_superuser_has_access_to_any_environment(self):
        self.assertTrue(user_has_environment_access(self.root, "anything-at-all"))
        self.assertTrue(user_has_environment_access(self.root, "prod", "deploy"))

    def test_viewer_can_view_but_not_deploy(self):
        self.assertTrue(user_has_environment_access(self.viewer, "dev", "viewer"))
        self.assertFalse(user_has_environment_access(self.viewer, "dev", "deploy"))

    def test_deployer_can_do_both(self):
        self.assertTrue(user_has_environment_access(self.deployer, "dev", "viewer"))
        self.assertTrue(user_has_environment_access(self.deployer, "dev", "deploy"))

    def test_no_grant_means_no_access(self):
        self.assertFalse(user_has_environment_access(self.viewer, "prod"))

    def test_assert_raises_carrying_environment_and_role(self):
        with self.assertRaises(EnvironmentAccessDenied) as ctx:
            assert_environment_access(self.viewer, "prod", "deploy")
        self.assertEqual(ctx.exception.environment, "prod")
        self.assertEqual(ctx.exception.role_required, "deploy")
        self.assertIn("prod", str(ctx.exception))

    def test_assert_passes_silently_when_permitted(self):
        self.assertIsNone(assert_environment_access(self.viewer, "dev"))

    def test_missing_environment_is_denied_rather_than_unscoped(self):
        # A tool called without an environment must not fall through to an
        # unscoped permission check.
        for missing in (None, ""):
            with self.subTest(value=missing):
                with self.assertRaises(EnvironmentAccessDenied):
                    assert_environment_access(self.viewer, missing)

    def test_grant_on_one_environment_does_not_leak_to_another(self):
        UserEnvironmentPermission.objects.create(
            user=self.viewer, environment="staging", role="admin"
        )
        self.assertTrue(user_has_environment_access(self.viewer, "staging"))
        self.assertFalse(user_has_environment_access(self.viewer, "prod"))


class TestDeploymentSetAccess(unittest.TestCase):
    def setUp(self):
        self.user = User.objects.create_user("authz_ds")
        self.root = User.objects.create_user("authz_ds_root", is_superuser=True)
        DeploymentSetPermission.objects.create(
            user=self.user, deployment_set="set-a", can_deploy=False
        )
        DeploymentSetPermission.objects.create(
            user=self.user, deployment_set="set-b", can_deploy=True
        )

    def test_superuser_has_access(self):
        self.assertTrue(user_has_deployment_set_access(self.root, "set-a"))
        self.assertTrue(user_has_deployment_set_access(self.root, "set-a", deploy=True))

    def test_view_only_grant_cannot_deploy(self):
        self.assertTrue(user_has_deployment_set_access(self.user, "set-a"))
        self.assertFalse(
            user_has_deployment_set_access(self.user, "set-a", deploy=True)
        )

    def test_deploy_grant_allows_both(self):
        self.assertTrue(user_has_deployment_set_access(self.user, "set-b"))
        self.assertTrue(user_has_deployment_set_access(self.user, "set-b", deploy=True))

    def test_assert_raises_carrying_the_set_name(self):
        with self.assertRaises(DeploymentSetAccessDenied) as ctx:
            assert_deployment_set_access(self.user, "set-a", deploy=True)
        self.assertEqual(ctx.exception.deployment_set, "set-a")
        self.assertEqual(ctx.exception.role_required, "deploy")


if __name__ == "__main__":
    unittest.main()
