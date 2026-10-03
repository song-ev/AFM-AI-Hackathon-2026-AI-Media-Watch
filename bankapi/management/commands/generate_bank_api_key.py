"""
Management command: generate a bank API key for a bank_admin user.

The raw key is printed ONCE and only its hash is stored — exactly like a normal
API provider. It cannot be retrieved again; if lost, issue a new one.
"""
import secrets

from django.core.management.base import BaseCommand, CommandError

from accounts.models import User
from bankapi.models import BankApiKey, hash_api_key

# Length (in bytes) of randomness behind the key.
KEY_BYTES = 32
PREFIX_LEN = 8


class Command(BaseCommand):
    help = "Generate a new API key for a bank_admin user (raw key shown once)."

    def add_arguments(self, parser):
        parser.add_argument("username", help="Username of the bank_admin user.")
        parser.add_argument(
            "--revoke-existing",
            action="store_true",
            help="Deactivate the user's existing active keys before issuing.",
        )

    def handle(self, *args, **options):
        username = options["username"]
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f"User '{username}' does not exist.")

        if user.role != User.Role.BANK_ADMIN:
            raise CommandError(
                f"User '{username}' has role '{user.role}', not 'bank_admin'. "
                "API keys may only be issued to bank_admin users."
            )

        if options["revoke_existing"]:
            count = BankApiKey.objects.filter(
                bank_admin=user, is_active=True
            ).update(is_active=False)
            self.stdout.write(self.style.WARNING(f"Revoked {count} existing key(s)."))

        raw_key = secrets.token_urlsafe(KEY_BYTES)
        BankApiKey.objects.create(
            bank_admin=user,
            key_hash=hash_api_key(raw_key),
            prefix=raw_key[:PREFIX_LEN],
        )

        self.stdout.write(self.style.SUCCESS(f"API key issued for '{username}'."))
        self.stdout.write("")
        self.stdout.write(self.style.WARNING(
            "============ SHOWN ONCE — STORE IT NOW ============"
        ))
        self.stdout.write(f"  API key: {raw_key}")
        self.stdout.write(self.style.WARNING(
            "  Use it as:  Authorization: ApiKey <key>"
        ))
        self.stdout.write(self.style.WARNING(
            "  It cannot be retrieved again — only reissued."
        ))
        self.stdout.write(self.style.WARNING(
            "==================================================="
        ))
