# Migration for ChangeSet status workflow and cross-environment promotion

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("deployments", "0002_add_permission_source"),
    ]

    operations = [
        migrations.AddField(
            model_name="changesetdraft",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("in_review", "In Review"),
                    ("accepted", "Accepted"),
                    ("rejected", "Rejected"),
                ],
                default="draft",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="changesetdraft",
            name="rejection_reason",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Reason provided when the ChangeSet was rejected",
            ),
        ),
        migrations.AddField(
            model_name="changesetdraft",
            name="cloned_from",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="clones",
                to="deployments.changesetdraft",
                help_text="Source draft this was cloned or promoted from",
            ),
        ),
        migrations.AddField(
            model_name="changesetdraft",
            name="instance_name_mapping",
            field=models.JSONField(
                blank=True,
                null=True,
                help_text="Mapping of original instance names to remapped names for cross-env promotion",
            ),
        ),
    ]
