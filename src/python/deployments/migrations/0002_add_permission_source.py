# Generated manually for Okta group-to-role mapping feature

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("deployments", "0001_initial"),
    ]

    operations = [
        # Add source field with default 'manual' for existing records
        migrations.AddField(
            model_name="userenvironmentpermission",
            name="source",
            field=models.CharField(
                choices=[("manual", "Manual"), ("okta", "Okta")],
                default="manual",
                help_text="How this permission was assigned (manual or synced from Okta)",
                max_length=20,
            ),
        ),
        # Update unique constraint from (user, environment) to (user, environment, source)
        migrations.AlterUniqueTogether(
            name="userenvironmentpermission",
            unique_together={("user", "environment", "source")},
        ),
        # Add index on (user, source) for efficient Okta sync queries
        migrations.AddIndex(
            model_name="userenvironmentpermission",
            index=models.Index(
                fields=["user", "source"],
                name="deployments_useren_user_id_source_idx",
            ),
        ),
    ]
