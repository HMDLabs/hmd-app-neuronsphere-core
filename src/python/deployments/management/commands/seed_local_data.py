"""Seed local development data for testing."""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from deployments.models import UserEnvironmentPermission


class Command(BaseCommand):
    help = "Seed local development data (environments, permissions)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--environments",
            nargs="+",
            default=["dev", "test", "prod"],
            help="Environments to create permissions for (default: dev test prod)",
        )
        parser.add_argument(
            "--username",
            default="admin",
            help="Username to grant permissions to (default: admin)",
        )

    def handle(self, *args, **options):
        User = get_user_model()
        environments = options["environments"]
        username = options["username"]

        # Get or create admin user
        try:
            user = User.objects.get(username=username)
            self.stdout.write(f"Found user: {username}")
        except User.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f"User '{username}' not found. Create it first.")
            )
            return

        # Create environment permissions (manual source for local dev)
        for env in environments:
            permission, created = UserEnvironmentPermission.objects.update_or_create(
                user=user,
                environment=env,
                source=UserEnvironmentPermission.Source.MANUAL,
                defaults={"role": UserEnvironmentPermission.Role.ADMIN},
            )
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f"Created {env} permission for {username}")
                )
            else:
                self.stdout.write(f"Updated {env} permission for {username}")

        self.stdout.write(self.style.SUCCESS("\nLocal data seeded successfully!"))
        self.stdout.write("\nUser permissions:")
        for perm in UserEnvironmentPermission.objects.filter(user=user):
            self.stdout.write(f"  - {perm.environment}: {perm.role}")

        self.stdout.write("\nNext steps:")
        self.stdout.write("  1. Seed deployment service data:")
        self.stdout.write("     ./src/local/scripts/seed_data.sh")
        self.stdout.write("  2. Browse environments in the GUI")
        self.stdout.write("  3. Create and apply changesets")
