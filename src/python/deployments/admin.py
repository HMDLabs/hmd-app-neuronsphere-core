"""Django admin configuration for deployments app."""
from django.contrib import admin
from .models import (
    AuditLog,
    ChangeSetDraft,
    DeploymentSetPermission,
    EnvironmentServiceConfig,
    MCPApiKey,
    UserEnvironmentPermission,
    UserPreference,
)


@admin.register(UserEnvironmentPermission)
class UserEnvironmentPermissionAdmin(admin.ModelAdmin):
    """Admin for UserEnvironmentPermission."""

    list_display = ["user", "environment", "role", "source", "created_at"]
    list_filter = ["environment", "role", "source"]
    search_fields = ["user__username", "user__email", "environment"]
    ordering = ["user", "environment"]

    def get_readonly_fields(self, request, obj=None):
        """Make Okta-sourced permissions read-only (managed by sync)."""
        if obj and obj.source == UserEnvironmentPermission.Source.OKTA:
            return ["user", "environment", "role", "source", "created_at", "updated_at"]
        return []


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Admin for AuditLog."""

    list_display = ["timestamp", "user", "action", "target", "success", "duration_ms"]
    list_filter = ["action", "success", "timestamp"]
    search_fields = ["user__username", "target", "correlation_id"]
    ordering = ["-timestamp"]
    readonly_fields = [
        "user",
        "action",
        "target",
        "details",
        "timestamp",
        "ip_address",
        "user_agent",
        "correlation_id",
        "success",
        "error_message",
        "duration_ms",
    ]

    def has_add_permission(self, request):
        """Disable adding audit logs manually."""
        return False

    def has_change_permission(self, request, obj=None):
        """Disable editing audit logs."""
        return False


@admin.register(ChangeSetDraft)
class ChangeSetDraftAdmin(admin.ModelAdmin):
    """Admin for ChangeSetDraft."""

    list_display = ["name", "user", "status", "change_count", "updated_at"]
    list_filter = ["status"]
    search_fields = ["name", "user__username"]
    ordering = ["-updated_at"]


@admin.register(DeploymentSetPermission)
class DeploymentSetPermissionAdmin(admin.ModelAdmin):
    """Admin for DeploymentSetPermission."""

    list_display = ["user", "deployment_set", "can_deploy", "created_at"]
    list_filter = ["deployment_set", "can_deploy"]
    search_fields = ["user__username", "user__email", "deployment_set"]
    ordering = ["user", "deployment_set"]


@admin.register(EnvironmentServiceConfig)
class EnvironmentServiceConfigAdmin(admin.ModelAdmin):
    """Admin for EnvironmentServiceConfig."""

    list_display = ["environment", "service_type", "instance_name"]
    list_filter = ["environment", "service_type"]
    search_fields = ["environment", "service_type", "instance_name"]
    ordering = ["environment", "service_type"]


@admin.register(UserPreference)
class UserPreferenceAdmin(admin.ModelAdmin):
    """Admin for UserPreference."""

    list_display = ["user", "default_environment", "default_view", "items_per_page"]
    search_fields = ["user__username", "user__email"]


@admin.register(MCPApiKey)
class MCPApiKeyAdmin(admin.ModelAdmin):
    """Admin for MCP API keys.

    Keys are created with the ``create_mcp_api_key`` management command, which is
    the only place the plaintext is ever shown. Adding one here is disabled
    because this form cannot display the generated secret; revoke by clearing
    ``is_active``.
    """

    list_display = [
        "name",
        "user",
        "key_prefix",
        "is_active",
        "created_at",
        "last_used_at",
        "expires_at",
    ]
    list_filter = ["is_active", "created_at"]
    search_fields = ["name", "user__username", "user__email", "key_prefix"]
    readonly_fields = ["key_prefix", "key_hash", "created_at", "last_used_at"]
    ordering = ["-created_at"]

    def has_add_permission(self, request):
        return False
