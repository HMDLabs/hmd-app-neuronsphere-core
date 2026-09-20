"""Add MCPApiKey and the MCP_TOOL_CALL audit action.

Bearer tokens for the MCP server where Okta tokens aren't available (local
development, bender, CI). Only the SHA-256 hash of a key is stored.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("deployments", "0006_pending_schema_drift"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="MCPApiKey",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        help_text="What this key is for (e.g. 'local dev', 'bender')",
                        max_length=100,
                    ),
                ),
                (
                    "key_prefix",
                    models.CharField(
                        db_index=True,
                        help_text="Leading characters of the key, for identification only",
                        max_length=16,
                    ),
                ),
                (
                    "key_hash",
                    models.CharField(
                        help_text="SHA-256 hex digest of the full key",
                        max_length=64,
                        unique=True,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                (
                    "expires_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="Optional expiry; blank means the key never expires",
                        null=True,
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mcp_api_keys",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "MCP API key",
                "verbose_name_plural": "MCP API keys",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AlterField(
            model_name="auditlog",
            name="action",
            field=models.CharField(
                choices=[
                    ("view_bom", "View BOM"),
                    ("view_instance", "View Instance"),
                    ("create_changeset", "Create ChangeSet"),
                    ("apply_changeset", "Apply ChangeSet"),
                    ("view_deployment", "View Deployment"),
                    ("view_logs", "View Logs"),
                    ("reject_changeset", "Reject ChangeSet"),
                    ("reopen_changeset", "Reopen ChangeSet"),
                    ("clone_changeset", "Clone ChangeSet"),
                    ("group_sync", "Sync Groups from Okta"),
                    ("mcp_tool_call", "MCP Tool Call"),
                ],
                max_length=50,
            ),
        ),
    ]
