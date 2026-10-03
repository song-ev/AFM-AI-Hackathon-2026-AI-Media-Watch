"""Celery application for AI Media Watch."""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ai_media_watch.settings.dev")

app = Celery("ai_media_watch")
# All CELERY_* settings in Django settings are picked up via this namespace.
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
