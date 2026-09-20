"""Update deployment status via the deployment service API."""
from django.core.management.base import BaseCommand, CommandError

from deployments.services.api_client import DeploymentAPIClient


CSD_STATUSES = ["CREATED", "STARTED", "COMPLETED", "FAILED", "DESTROYED"]
CSED_STATUSES = ["CREATED", "STARTED", "COMPLETED", "FAILED", "SKIPPED", "DESTROYED"]
RID_STATUSES = [
    "DEPLOY_NEXT",
    "DEPLOYED",
    "DESTROY_NEXT",
    "DESTROYED",
    "FAILED",
    "SKIPPED",
]


class Command(BaseCommand):
    help = "Update deployment status via the deployment service API"

    def add_arguments(self, parser):
        parser.add_argument(
            "entity_type",
            choices=["csd", "csed", "rid"],
            help="Entity type: csd (ChangeSetDeployment), csed (ChangeSetEnvDeployment), rid (RepoInstanceDeployment)",
        )
        parser.add_argument(
            "entity_id",
            help="Entity ID (nid) to update",
        )
        parser.add_argument(
            "status",
            help="New status value",
        )

    def handle(self, *args, **options):
        entity_type = options["entity_type"]
        entity_id = options["entity_id"]
        status = options["status"].upper()

        # Validate status
        if entity_type == "csd":
            valid_statuses = CSD_STATUSES
            endpoint = "set_change_set_deployment_status"
        elif entity_type == "csed":
            valid_statuses = CSED_STATUSES
            endpoint = "set_change_set_env_deployment_status"
        else:  # rid
            valid_statuses = RID_STATUSES
            endpoint = "set_deployment_status"

        if status not in valid_statuses:
            raise CommandError(
                f"Invalid status '{status}' for {entity_type}. "
                f"Valid options: {', '.join(valid_statuses)}"
            )

        # Call API
        client = DeploymentAPIClient()
        response = client._make_request(
            "POST",
            f"/apiop/{endpoint}/{entity_id}/{status}",
        )

        if response.success:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully updated {entity_type} {entity_id} to {status}"
                )
            )
            if response.data:
                self.stdout.write(f"Response: {response.data}")
        else:
            raise CommandError(
                f"Failed to update status: {response.error} (HTTP {response.status_code})"
            )
