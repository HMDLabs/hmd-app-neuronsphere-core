"""Robot Framework library to manage user permissions for testing."""

import json
import subprocess


APP_CONTAINER = "neuronsphere-gui"


class PermissionSeed:
    """Manage Django users and environment permissions for testing."""

    def create_test_user(self, username, password, email=None, is_superuser=False):
        """Create a Django user via manage.py shell."""
        email = email or f"{username}@test.local"
        if is_superuser:
            cmd = (
                f"from django.contrib.auth.models import User; "
                f"User.objects.filter(username='{username}').delete(); "
                f"User.objects.create_superuser('{username}', '{email}', '{password}')"
            )
        else:
            cmd = (
                f"from django.contrib.auth.models import User; "
                f"User.objects.filter(username='{username}').delete(); "
                f"u = User.objects.create_user('{username}', '{email}', '{password}'); "
                f"u.is_active = True; u.save()"
            )
        self._run_manage_shell(cmd)

    def grant_environment_permission(self, username, environment, role, source="manual"):
        """Create a UserEnvironmentPermission for a user."""
        cmd = (
            f"from django.contrib.auth.models import User; "
            f"from deployments.models import UserEnvironmentPermission; "
            f"user = User.objects.get(username='{username}'); "
            f"UserEnvironmentPermission.objects.update_or_create("
            f"user=user, environment='{environment}', source='{source}', "
            f"defaults={{'role': '{role}'}})"
        )
        self._run_manage_shell(cmd)

    def revoke_environment_permission(self, username, environment, source=None):
        """Remove a UserEnvironmentPermission for a user."""
        if source:
            filter_clause = (
                f"user=user, environment='{environment}', source='{source}'"
            )
        else:
            filter_clause = f"user=user, environment='{environment}'"
        cmd = (
            f"from django.contrib.auth.models import User; "
            f"from deployments.models import UserEnvironmentPermission; "
            f"user = User.objects.get(username='{username}'); "
            f"UserEnvironmentPermission.objects.filter({filter_clause}).delete()"
        )
        self._run_manage_shell(cmd)

    def clear_user_permissions(self, username, source=None):
        """Clear all permissions for a user, optionally filtered by source."""
        if source:
            filter_clause = f"user=user, source='{source}'"
        else:
            filter_clause = "user=user"
        cmd = (
            f"from django.contrib.auth.models import User; "
            f"from deployments.models import UserEnvironmentPermission; "
            f"user = User.objects.get(username='{username}'); "
            f"UserEnvironmentPermission.objects.filter({filter_clause}).delete()"
        )
        self._run_manage_shell(cmd)

    def get_permission_count(self, username, source=None):
        """Return the number of permissions for a user."""
        if source:
            filter_clause = f"user=user, source='{source}'"
        else:
            filter_clause = "user=user"
        cmd = (
            f"from django.contrib.auth.models import User; "
            f"from deployments.models import UserEnvironmentPermission; "
            f"user = User.objects.get(username='{username}'); "
            f"print(UserEnvironmentPermission.objects.filter({filter_clause}).count())"
        )
        result = self._run_manage_shell(cmd)
        return int(result.strip().split("\\n")[-1])

    def grant_deployment_set_permission(self, username, deployment_set, can_deploy=False):
        """Create a DeploymentSetPermission for a user."""
        can_deploy_str = "True" if can_deploy else "False"
        cmd = (
            f"from django.contrib.auth.models import User; "
            f"from deployments.models import DeploymentSetPermission; "
            f"user = User.objects.get(username='{username}'); "
            f"DeploymentSetPermission.objects.update_or_create("
            f"user=user, deployment_set='{deployment_set}', "
            f"defaults={{'can_deploy': {can_deploy_str}}})"
        )
        self._run_manage_shell(cmd)

    def revoke_deployment_set_permission(self, username, deployment_set):
        """Remove a DeploymentSetPermission for a user."""
        cmd = (
            f"from django.contrib.auth.models import User; "
            f"from deployments.models import DeploymentSetPermission; "
            f"user = User.objects.get(username='{username}'); "
            f"DeploymentSetPermission.objects.filter("
            f"user=user, deployment_set='{deployment_set}').delete()"
        )
        self._run_manage_shell(cmd)

    def clear_deployment_set_permissions(self, username):
        """Clear all deployment set permissions for a user."""
        cmd = (
            f"from django.contrib.auth.models import User; "
            f"from deployments.models import DeploymentSetPermission; "
            f"user = User.objects.get(username='{username}'); "
            f"DeploymentSetPermission.objects.filter(user=user).delete()"
        )
        self._run_manage_shell(cmd)

    def get_deployment_set_permission_count(self, username):
        """Return the number of deployment set permissions for a user."""
        cmd = (
            f"from django.contrib.auth.models import User; "
            f"from deployments.models import DeploymentSetPermission; "
            f"user = User.objects.get(username='{username}'); "
            f"print(DeploymentSetPermission.objects.filter(user=user).count())"
        )
        result = self._run_manage_shell(cmd)
        return int(result.strip().split("\\n")[-1])

    def run_okta_group_sync(self, username, okta_groups_json):
        """Invoke sync_okta_permissions for a user with given group names."""
        cmd = (
            f"import json; "
            f"from django.contrib.auth.models import User; "
            f"from deployments.group_sync import sync_okta_permissions; "
            f"user = User.objects.get(username='{username}'); "
            f"groups = json.loads('{okta_groups_json}'); "
            f"sync_okta_permissions(user, groups)"
        )
        self._run_manage_shell(cmd)

    def delete_test_user(self, username):
        """Delete a Django user."""
        cmd = (
            f"from django.contrib.auth.models import User; "
            f"User.objects.filter(username='{username}').delete()"
        )
        self._run_manage_shell(cmd)

    def _run_manage_shell(self, python_code):
        """Execute Python code in the Django manage.py shell."""
        result = subprocess.run(
            [
                "docker", "exec", APP_CONTAINER,
                "python", "manage.py", "shell", "-c", python_code,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"manage.py shell failed: {result.stderr}\nstdout: {result.stdout}"
            )
        return result.stdout
