"""ASGI config for AI Media Watch."""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ai_media_watch.settings.dev")

application = get_asgi_application()
