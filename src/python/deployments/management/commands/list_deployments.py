"""List deployments from the deployment service."""
from django.core.management.base import BaseCommand, CommandError

from deployments.services.api_client import DeploymentAPIClient


class Command(BaseCommand):
    help = "List deployments (BOM) from the deployment service"

    def add_arguments(self, parser):
        parser.add_argument(
            "environment",
            help="Environment to list (e.g., dev, test, prod)",
        )
        parser.add_argument(
            "--format",
            choices=["table", "json"],
            default="table",
            help="Output format (default: table)",
        )

    def handle(self, *args, **options):
        environment = options["environment"]
        output_format = options["format"]

        client = DeploymentAPIClient()
        response = client.get_deployment_bom(environment)

        if not response.success:
            raise CommandError(
                f"Failed to get BOM: {response.error} (HTTP {response.status_code})"
            )

        bom_data = response.data or []

        if not bom_data:
            self.stdout.write(f"No deployments found in '{environment}'")
            return

        if output_format == "json":
            import json

            self.stdout.write(json.dumps(bom_data, indent=2))
        else:
            # Table format
            self.stdout.write(f"\nDeployments in '{environment}':")
            self.stdout.write("-" * 80)
            self.stdout.write(
                f"{'Instance Name':<30} {'Repo Class':<25} {'Version':<10} {'Status':<10}"
            )
            self.stdout.write("-" * 80)

            for item in bom_data:
                instance = item.get("repo_instance_name", "N/A")[:29]
                repo_class = item.get("repo_class_name", "N/A")[:24]
                version = item.get("repo_class_version", "N/A")[:9]
                status = item.get("status", "N/A")[:9]
                self.stdout.write(
                    f"{instance:<30} {repo_class:<25} {version:<10} {status:<10}"
                )

            self.stdout.write("-" * 80)
            self.stdout.write(f"Total: {len(bom_data)} deployments")
