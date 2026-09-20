"""Mint an MCP API key for a user.

The plaintext key is printed once and is unrecoverable afterwards -- only its
SHA-256 hash is stored.
"""
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from deployments.models import MCPApiKey


class Command(BaseCommand):
    help = "Create an MCP API key for a user (prints the key once)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--user", required=True, help="Username to issue the key to"
        )
        parser.add_argument(
            "--name", default="mcp", help="Label for the key (e.g. 'local dev')"
        )
        parser.add_argument(
            "--expires-days",
            type=int,
            default=None,
            help="Expire the key after this many days (default: never)",
        )
        parser.add_argument(
            "--key",
            default=None,
            help=(
                "Use this plaintext key instead of generating one. For a "
                "deploy-time bootstrap where both sides must know the "
                "credential (the local createLocalMcpKey hook); only the hash "
                "is stored either way."
            ),
        )
        parser.add_argument(
            "--if-not-exists",
            action="store_true",
            help=(
                "Do nothing if an active key with this name already exists for "
                "the user. For idempotent local/CI bootstrap."
            ),
        )

    def handle(self, *args, **options):
        try:
            user = User.objects.get(username=options["user"])
        except User.DoesNotExist:
            raise CommandError(f"No such user: {options['user']}")

        name = options["name"]
        if (
            options["if_not_exists"]
            and MCPApiKey.objects.filter(user=user, name=name, is_active=True).exists()
        ):
            self.stdout.write(
                self.style.WARNING(
                    f"An active key named '{name}' already exists for "
                    f"{user.username}; leaving it alone."
                )
            )
            return

        expires_at = None
        if options["expires_days"]:
            expires_at = timezone.now() + timezone.timedelta(
                days=options["expires_days"]
            )

        try:
            _, raw_key = MCPApiKey.generate(
                user, name, expires_at=expires_at, raw_key=options["key"]
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from None

        if options["key"]:
            # Nothing to reveal -- the operator supplied it -- and echoing a
            # known credential into deploy logs is worth avoiding.
            self.stdout.write(
                self.style.SUCCESS(
                    f"Created MCP API key '{name}' for {user.username} from the "
                    f"supplied plaintext."
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(f"Created MCP API key '{name}' for {user.username}.")
        )
        self.stdout.write("")
        self.stdout.write(raw_key)
        self.stdout.write("")
        self.stdout.write(
            self.style.WARNING("This is the only time the key is shown. Store it now.")
        )
