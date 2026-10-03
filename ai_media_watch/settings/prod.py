"""
Production settings.

Activate by setting DJANGO_SETTINGS_MODULE=ai_media_watch.settings.prod.
All sensitive values MUST come from the environment — nothing is hard-coded.
"""
from .base import *  # noqa: F401,F403

# DEBUG must be off in production. Sourced from the environment via base.py;
# pinned here defensively.
DEBUG = False

# Fail loudly if the secret key was left at its insecure default.
if SECRET_KEY == "insecure-dev-key-change-me":  # noqa: F405
    raise RuntimeError(
        "DJANGO_SECRET_KEY is not set. Refusing to start with the insecure "
        "default key in production."
    )

# ALLOWED_HOSTS and CORS_ALLOWED_ORIGINS are read from the environment in base.py.

# ---------------------------------------------------------------------------
# Security hardening
# ---------------------------------------------------------------------------
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30  # 30 days
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# In production the Browsable API is unnecessary; serve JSON only.
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [  # noqa: F405
    "rest_framework.renderers.JSONRenderer",
]
