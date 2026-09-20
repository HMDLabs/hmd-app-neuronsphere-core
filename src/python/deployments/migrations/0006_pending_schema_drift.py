"""Absorb schema drift that predates the MCP work.

These three operations were already pending against ``0005`` before any MCP
change: the index rename follows Django's auto-generated naming, and the two
``id`` columns move ``AutoField -> BigAutoField`` to match ``DEFAULT_AUTO_FIELD``.
They are split out from the MCP migration so each is reviewable on its own.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("deployments", "0005_changeset_environment_agnostic"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="userenvironmentpermission",
            new_name="deployments_user_id_194315_idx",
            old_name="deployments_useren_user_id_source_idx",
        ),
        migrations.AlterField(
            model_name="deploymentsetpermission",
            name="id",
            field=models.BigAutoField(
                auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
            ),
        ),
        migrations.AlterField(
            model_name="environmentserviceconfig",
            name="id",
            field=models.BigAutoField(
                auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
            ),
        ),
    ]
