"""
Development settings.

Loaded by default (manage.py / wsgi / asgi point here). Optimised for local
development convenience, NOT for security. Never run this in production.
"""
from .base import *  # noqa: F401,F403

# Force DEBUG on locally regardless of the environment file.
DEBUG = True

# Be permissive about hosts during local development.
ALLOWED_HOSTS = ["*"]

# Allow all origins locally so any frontend dev port can call the API.
CORS_ALLOW_ALL_ORIGINS = True

# Run Celery tasks in-process by default so local dev works WITHOUT a running
# Redis broker / worker (submitting a video would otherwise 500 on enqueue).
# Set CELERY_TASK_ALWAYS_EAGER=False in the env to use a real broker+worker.
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=True)
# Don't surface eager task exceptions to the HTTP caller (mirror async behaviour).
CELERY_TASK_EAGER_PROPAGATES = False
