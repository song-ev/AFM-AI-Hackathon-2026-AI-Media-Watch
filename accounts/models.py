"""
Accounts: custom user model, roles and per-role profiles.

Roles and what they grant:

- analyst    — full internal access: queue, incident cards, reasoning graphs,
               connections, the leadership trends dashboard, the code-word
               dictionary review (Stage 4), decisions and user management
               (the latter via the Django superuser flag).
- bank_admin — access ONLY to bankapi (REST risk-score lookups for an
               account); cannot see internal incident cards or AFM analytics.
"""
from django.contrib.auth.models import AbstractUser
from django.db import models

from core.models import TimeStampedModel


class User(AbstractUser):
    """Custom user with an AFM role.

    Set as AUTH_USER_MODEL; AbstractUser already provides username, password,
    email, names and the staff/superuser flags.
    """

    class Role(models.TextChoices):
        ANALYST = "analyst", "Analyst"
        BANK_ADMIN = "bank_admin", "Bank admin"
        AFM_LEAD = "afm_lead", "AFM lead"
        SYSTEM_ADMIN = "system_admin", "System admin"

    role = models.CharField(
        max_length=16,
        choices=Role.choices,
        default=Role.ANALYST,
        db_index=True,
    )

    def __str__(self) -> str:
        return f"{self.username} ({self.role})"


class AnalystProfile(TimeStampedModel):
    """Extra profile data for analyst users."""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="analyst_profile",
    )
    department = models.CharField(max_length=255, null=True, blank=True)
    # Kept in sync by a post_save signal on AnalystLabel.
    cases_reviewed_count = models.IntegerField(default=0)

    def __str__(self) -> str:
        return f"AnalystProfile<{self.user.username}>"


class BankAdminProfile(TimeStampedModel):
    """Extra profile data for bank_admin users."""

    class Bank(models.TextChoices):
        KASPI = "kaspi", "Kaspi"
        HALYK = "halyk", "Halyk"
        OTHER = "other", "Other"

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="bank_admin_profile",
    )
    bank_name = models.CharField(max_length=16, choices=Bank.choices)
    # Display label only — never store the actual API key here.
    api_key_label = models.CharField(max_length=255, blank=True)

    def __str__(self) -> str:
        return f"BankAdminProfile<{self.user.username}> ({self.bank_name})"


class AnalystLabel(TimeStampedModel):
    """An analyst's manual decision on an incident."""

    class Decision(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmed"
        FALSE_POSITIVE = "false_positive", "False positive"
        BORDERLINE = "borderline", "Borderline"

    incident = models.ForeignKey(
        "incidents.Incident",
        on_delete=models.CASCADE,
        related_name="analyst_labels",
    )
    decision = models.CharField(
        max_length=16,
        choices=Decision.choices,
        db_index=True,
    )
    comment = models.TextField(null=True, blank=True)
    analyst = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="analyst_labels",
    )
    decided_at = models.DateTimeField()

    class Meta:
        ordering = ["-decided_at"]
        indexes = [
            models.Index(fields=["incident", "decision"]),
        ]

    def __str__(self) -> str:
        return f"{self.decision} on incident {self.incident_id} by {self.analyst_id}"
