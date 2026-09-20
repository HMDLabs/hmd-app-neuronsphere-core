"""App configuration for deployments."""
from django.apps import AppConfig


class DeploymentsConfig(AppConfig):
    """Configuration for the deployments app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "deployments"
    verbose_name = "NeuronSphere Deployments"

    def ready(self):
        import deployments.signals  # noqa: F401
