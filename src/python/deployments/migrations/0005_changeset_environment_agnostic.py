# Drop environment/promotion fields from ChangeSetDraft and introduce
# ChangeSetApplication to record each apply to a DeploymentSet.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("deployments", "0004_deployment_set_permission_and_service_config"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="changesetdraft",
            name="cloned_from",
        ),
        migrations.RemoveField(
            model_name="changesetdraft",
            name="instance_name_mapping",
        ),
        migrations.RemoveField(
            model_name="changesetdraft",
            name="target_deployment_set",
        ),
        migrations.RemoveField(
            model_name="changesetdraft",
            name="target_environment",
        ),
        migrations.CreateModel(
            name="ChangeSetApplication",
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
                ("deployment_set", models.CharField(max_length=100)),
                ("csd_id", models.CharField(blank=True, default="", max_length=100)),
                ("applied_at", models.DateTimeField(auto_now_add=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("submitted", "Submitted"),
                            ("failed", "Failed"),
                        ],
                        default="submitted",
                        max_length=20,
                    ),
                ),
                ("error", models.TextField(blank=True, default="")),
                (
                    "draft",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="applications",
                        to="deployments.changesetdraft",
                    ),
                ),
                (
                    "applied_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="changeset_applications",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-applied_at"],
            },
        ),
    ]
