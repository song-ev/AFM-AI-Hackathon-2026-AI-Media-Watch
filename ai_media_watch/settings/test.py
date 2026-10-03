"""Isolated automated tests; no database server, broker, or API keys needed."""
from .base import *  # noqa: F401,F403

DEBUG = False
SECRET_KEY = "test-only-key-never-use-in-a-deployment"
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
LLM_API_KEY = ""
ANTHROPIC_API_KEY = ""
