# Migration for DeploymentSetPermission and EnvironmentServiceConfig models

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("deployments", "0003_changeset_status_and_promotion"),
    ]

    operations = [
        migrations.CreateModel(
            name="DeploymentSetPermission",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "deployment_set",
                    models.CharField(
                        db_index=True,
                        help_text="Deployment set name (e.g., 'dev-main', 'prod-primary')",
                        max_length=100,
                    ),
                ),
                (
                    "can_deploy",
                    models.BooleanField(
                        default=False,
                        help_text="Whether the user can deploy to this deployment set",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="deployment_set_permissions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["user", "deployment_set"],
                "unique_together": {("user", "deployment_set")},
            },
        ),
        migrations.CreateModel(
            name="EnvironmentServiceConfig",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "environment",
                    models.CharField(
                        help_text="Environment type (e.g., 'dev', 'test', 'prod')",
                        max_length=50,
                    ),
                ),
                (
                    "service_type",
                    models.CharField(
                        help_text="Service type (e.g., 'telemetry', 'transform', 'librarian')",
                        max_length=50,
                    ),
                ),
                (
                    "instance_name",
                    models.CharField(
                        help_text="Overridden instance name in the BOM",
                        max_length=100,
                    ),
                ),
            ],
            options={
                "ordering": ["environment", "service_type"],
                "unique_together": {("environment", "service_type")},
            },
        ),
    ]
