"""
Management command: create one demo user per role.

FOR DEMO ONLY — all users share a randomly generated password that is printed
to the console. Never run this against a real/production environment.
"""
import secrets

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import AnalystProfile, BankAdminProfile, User

# (username, role, email, is_superuser) — one per role.
DEMO_USERS = [
    ("analyst_demo", User.Role.ANALYST, "analyst_demo@example.kz", False),
    ("lead_demo", User.Role.AFM_LEAD, "lead_demo@example.kz", False),
    ("bank_demo", User.Role.BANK_ADMIN, "bank_demo@example.kz", False),
    ("admin_demo", User.Role.SYSTEM_ADMIN, "admin_demo@example.kz", True),
]


class Command(BaseCommand):
    help = "Create demo users (idempotent). DEV ONLY — refuses to run with DEBUG=False."

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "Refusing to create demo users with DEBUG=False (production). "
                "Create real accounts via the admin or a provisioning workflow."
            )
        created, updated = [], []
        password = secrets.token_urlsafe(18)

        for username, role, email, is_superuser in DEMO_USERS:
            user, was_created = User.objects.get_or_create(
                username=username,
                defaults={"email": email, "role": role},
            )
            user.email = email
            user.role = role
            user.is_active = True
            if is_superuser:
                user.is_staff = True
                user.is_superuser = True
            user.set_password(password)
            user.save()

            self._ensure_profile(user, role)
            (created if was_created else updated).append(username)

        self.stdout.write(self.style.SUCCESS(
            f"Created: {', '.join(created) or '—'}"
        ))
        self.stdout.write(
            f"Updated (already existed): {', '.join(updated) or '—'}"
        )
        self.stdout.write("")
        self.stdout.write(self.style.WARNING(
            "================ ТОЛЬКО ДЛЯ ДЕМО / DEMO ONLY ================"
        ))
        self.stdout.write(self.style.WARNING(
            f"  Demo password for ALL demo users: {password}"
        ))
        self.stdout.write(self.style.WARNING(
            "  Do NOT use these credentials outside of local demos."
        ))
        self.stdout.write(self.style.WARNING(
            "============================================================"
        ))

    @staticmethod
    def _ensure_profile(user, role):
        """Attach the role-appropriate profile."""
        internal = (User.Role.ANALYST, User.Role.AFM_LEAD, User.Role.SYSTEM_ADMIN)
        if role in internal:
            AnalystProfile.objects.get_or_create(
                user=user,
                defaults={"department": "Demo department"},
            )
        elif role == User.Role.BANK_ADMIN:
            BankAdminProfile.objects.get_or_create(
                user=user,
                defaults={
                    "bank_name": BankAdminProfile.Bank.KASPI,
                    "api_key_label": "demo-key",
                },
            )
