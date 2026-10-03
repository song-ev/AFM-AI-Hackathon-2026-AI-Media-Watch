"""
Bank API key model.

Banks are external integrations (doc §3.6): they authenticate with an API key,
not a JWT login. We store only the SHA-256 hash of the key — the raw key is
shown once at generation time and can never be retrieved again, only reissued.
"""
import hashlib

from django.db import models

from core.models import TimeStampedModel


def hash_api_key(raw_key: str) -> str:
    """Return the hex SHA-256 of a raw API key (used for storage & lookup)."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


class BankApiKey(TimeStampedModel):
    """A hashed API key belonging to a bank_admin user."""

    bank_admin = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="bank_api_keys",
        help_text="Owner; must be a user with role=bank_admin.",
    )
    # SHA-256 hex digest of the key; the raw key is never stored.
    key_hash = models.CharField(max_length=64, unique=True, db_index=True)
    # Non-secret leading fragment, for identifying a key in the UI/admin.
    prefix = models.CharField(max_length=12, blank=True)
    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        state = "active" if self.is_active else "revoked"
        return f"BankApiKey {self.prefix}… ({self.bank_admin_id}, {state})"
