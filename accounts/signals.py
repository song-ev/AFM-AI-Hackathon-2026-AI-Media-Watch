"""Signals that keep derived profile data in sync."""
from django.db.models.signals import post_save
from django.dispatch import receiver

from accounts.models import AnalystLabel, AnalystProfile


@receiver(post_save, sender=AnalystLabel)
def bump_cases_reviewed_count(sender, instance, created, **kwargs):
    """Recompute the analyst's reviewed-cases counter when a label is saved.

    Recomputed (not blindly incremented) so the value stays correct even if a
    label is re-saved or back-filled.
    """
    if not created:
        return
    profile, _ = AnalystProfile.objects.get_or_create(user=instance.analyst)
    profile.cases_reviewed_count = AnalystLabel.objects.filter(
        analyst=instance.analyst
    ).count()
    profile.save(update_fields=["cases_reviewed_count", "updated_at"])
