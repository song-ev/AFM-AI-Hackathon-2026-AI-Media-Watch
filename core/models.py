"""
Shared abstract base models.

These are abstract (no database table of their own) and exist purely to be
inherited by concrete models in the domain apps. This is the only "model"
code in the scaffold — it carries no business logic, just common columns.
"""
from django.db import models


class TimeStampedModel(models.Model):
    """Abstract base that adds self-updating created/modified timestamps."""

    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        abstract = True
        ordering = ["-created_at"]
