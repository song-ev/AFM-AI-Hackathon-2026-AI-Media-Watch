"""
Base settings for the AI Media Watch project.

Settings common to every environment live here. Environment-specific
overrides live in dev.py and prod.py, both of which import everything from
this module with `from .base import *`.

Configuration values are read from environment variables via django-environ,
so no secrets are hard-coded in source control. See .env.example.
"""
from pathlib import Path

import environ

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# BASE_DIR points at the repository root (the folder containing manage.py).
# settings/base.py -> settings -> ai_media_watch -> <repo root>
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Environment variables
# ---------------------------------------------------------------------------
env = environ.Env(
    DJANGO_DEBUG=(bool, True),
    DJANGO_ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    DJANGO_CORS_ALLOWED_ORIGINS=(list, ["http://localhost:3000"]),
)

# Read a .env file at the repo root if present (no error if it is absent —
# in production the variables are typically injected by the orchestrator).
environ.Env.read_env(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# Core security settings
# ---------------------------------------------------------------------------
SECRET_KEY = env("DJANGO_SECRET_KEY", default="insecure-dev-key-change-me")

# DEBUG defaults to False here; dev.py forces it True. Never trust the default
# blindly in production — set DJANGO_DEBUG explicitly.
DEBUG = env("DJANGO_DEBUG")

ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",  # refresh-token blacklist on logout
    "django_filters",
    "corsheaders",
]

# Each local app is a future zone of responsibility in the v3.0 pipeline.
LOCAL_APPS = [
    "core",          # shared utilities and base models
    "accounts",      # users, roles, authentication
    "ingestion",     # Stage 1 — video collection / data sources
    "screening",     # Stage 1 — first-pass screening microservices
    "deepanalysis",  # Stage 2 — deep analysis
    "incidents",     # Stage 3 — incident cards, summaries, evidence chain
    "learning",      # Stage 4 — self-learning, code-word dictionary
    "bankapi",       # external REST API for banks
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",  # must precede CommonMiddleware
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "ai_media_watch.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "ai_media_watch.wsgi.application"
ASGI_APPLICATION = "ai_media_watch.asgi.application"

# ---------------------------------------------------------------------------
# Database (PostgreSQL via DATABASE_URL)
# ---------------------------------------------------------------------------

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://aimw:aimw@localhost:5432/ai_media_watch",
    ),
}

# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Almaty"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static & media files
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Custom user model with a role (analyst / bank_admin).
AUTH_USER_MODEL = "accounts.User"

# ---------------------------------------------------------------------------
# Cache (local in-memory is enough for the hackathon). Used to cache the
# leadership dashboard aggregations for a few minutes.
# ---------------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "ai-media-watch",
    }
}

# Dashboard ROI assumption: average time an analyst spends manually reviewing
# one video. DEMO ASSUMPTION — not measured. Used to estimate time saved by
# Stage-1 auto-filtering.
ANALYST_AVG_REVIEW_SECONDS_PER_VIDEO = 180  # 3 minutes

# ---------------------------------------------------------------------------
# Celery (async task queue) — broker/result backend default to local Redis.
# In an environment without Redis, set CELERY_TASK_ALWAYS_EAGER=True to run
# tasks synchronously in-process (handy for demos; see README).
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/0")
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TIMEZONE = TIME_ZONE

# Route the long-running live-stream monitor to its own queue so it never
# starves video downloads / screening. Run a dedicated worker for it:
#   celery -A ai_media_watch worker -Q live --pool=solo -n live@%h
# and the default worker(s) for everything else (default "celery" queue):
#   celery -A ai_media_watch worker --pool=solo -n w1@%h
CELERY_TASK_ROUTES = {
    "ingestion.monitor_live_session": {"queue": "live"},
}

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    # Custom exception handler stub — fill in project-wide error shaping later.
    "EXCEPTION_HANDLER": "core.exceptions.custom_exception_handler",
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    # Internal frontend (analysts / AFM): JWT + session (for the browsable API).
    # Banks authenticate per-view with BankApiKeyAuthentication (see bankapi),
    # NOT with JWT — a deliberate architectural choice (doc §3.6).
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    # No restrictive global permission yet — domain endpoints (block C) set their
    # own. Auth endpoints are explicitly AllowAny.
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.AnonRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "user": "1000/hour",
        "anon": "100/hour",
        # Stricter, dedicated bucket for bank integrations (SLA < 200ms — must
        # be protected from overload). Applied via BankApiKeyRateThrottle.
        "bank": "60/min",
    },
}

# ---------------------------------------------------------------------------
# SimpleJWT
# ---------------------------------------------------------------------------
from datetime import timedelta  # noqa: E402

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# ---------------------------------------------------------------------------
# CORS (for the Next.js frontend)
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env("DJANGO_CORS_ALLOWED_ORIGINS")

# ---------------------------------------------------------------------------
# Stage 1 Screening Configurations
# ---------------------------------------------------------------------------
# Threshold for scenedetect ContentDetector
SCENEDETECT_THRESHOLD = env.float("SCENEDETECT_THRESHOLD", default=27.0)

# Whisper model for fast Stage 1 audio transcription (trade-off: speed vs quality)
# 'tiny' is fastest, 'base' is slightly better but slower.
WHISPER_STAGE1_MODEL = env.str("WHISPER_STAGE1_MODEL", default="tiny")

# Optional yt-dlp cookies file (Netscape format). Required to parse/download
# TikTok & Instagram reliably (and age/region-gated YouTube). Export from a
# logged-in browser session. Empty => only public, cookie-free sources work.
YTDLP_COOKIES_FILE = env.str("YTDLP_COOKIES_FILE", default="")

# Optional outbound proxy for yt-dlp (parsing/live at scale, IP-rotation pools).
# e.g. "http://user:pass@host:port" or "socks5://host:port". Empty => direct.
YTDLP_PROXY = env.str("YTDLP_PROXY", default="")

# Browser TLS impersonation target for yt-dlp (requires curl_cffi). TikTok /
# Instagram return HTTP 403 without it. "chrome" is a safe default; empty
# disables impersonation.
YTDLP_IMPERSONATE = env.str("YTDLP_IMPERSONATE", default="chrome")

# JavaScript runtimes yt-dlp may use to decipher YouTube signatures. yt-dlp only
# auto-enables "deno"; without an available runtime modern YouTube videos fail
# with "Video unavailable" / missing formats. We also enable "node" (commonly
# installed). Comma-separated; empty disables (not recommended for YouTube).
YTDLP_JS_RUNTIMES = env.list("YTDLP_JS_RUNTIMES", default=["deno", "node"])

# Tesseract executable path. Change this if tesseract is not in PATH.
# Example for Windows: r'C:\Program Files\Tesseract-OCR\tesseract.exe'
TESSERACT_CMD = env.str("TESSERACT_CMD", default="tesseract")
# Optional custom tessdata directory (extra language packs, e.g. rus/kaz). When
# the system tessdata folder isn't writable, point here via --tessdata-dir.
TESSDATA_DIR = env.str("TESSDATA_DIR", default="")
# Minimum per-word OCR confidence (0-100) to trust a recognised token.
OCR_MIN_WORD_CONFIDENCE = env.float("OCR_MIN_WORD_CONFIDENCE", default=40.0)

# YOLO model for logo detection. In production point this at a model FINE-TUNED
# on gambling/casino logos (1xBet, Lucky Jet, ...) and list its positive class
# names in YOLO_LOGO_CLASSES — only those classes flag the frame. With no
# classes configured, YOLO contributes nothing (OCR keywords still apply); it
# never flags on arbitrary COCO objects.
YOLO_MODEL_PATH = env.str("YOLO_MODEL_PATH", default="yolov8n.pt")
YOLO_IOU_THRESHOLD = env.float("YOLO_IOU_THRESHOLD", default=0.5)
YOLO_CONFIDENCE_THRESHOLD = env.float("YOLO_CONFIDENCE_THRESHOLD", default=0.5)
YOLO_LOGO_CLASSES = env.list("YOLO_LOGO_CLASSES", default=[])

# ---------------------------------------------------------------------------
# Stage 2 & 4 Configurations
# ---------------------------------------------------------------------------
# LLM for semantic analysis and incident summaries. Empty key => the LLM steps
# fail loudly (recorded as a step error) instead of fabricating a neutral result.
ANTHROPIC_API_KEY = env.str("ANTHROPIC_API_KEY", default="")
ANTHROPIC_BASE_URL = env.str("ANTHROPIC_BASE_URL", default="")
ANTHROPIC_MODEL = env.str("ANTHROPIC_MODEL", default="")

# Unified LLM client (core.llm). Primary path is an OpenAI-compatible endpoint
# (OpenRouter / Qwen / vLLM / local). When LLM_API_KEY is set it is preferred;
# otherwise the client falls back to the Anthropic SDK if ANTHROPIC_API_KEY is
# set. With neither configured, every LLM step fails loud (ModuleDependencyError).
LLM_BASE_URL = env.str("LLM_BASE_URL", default="")
LLM_API_KEY = env.str("LLM_API_KEY", default="")
LLM_MODEL = env.str("LLM_MODEL", default="")
LLM_TIMEOUT = env.float("LLM_TIMEOUT", default=120.0)
LLM_FORCE_JSON = env.bool("LLM_FORCE_JSON", default=False)
WHISPER_STAGE2_MODEL = env.str("WHISPER_STAGE2_MODEL", default="base")
RISK_SCORE_VERDICT_THRESHOLD = env.float("RISK_SCORE_VERDICT_THRESHOLD", default=60.0)

# Identity matching thresholds (cosine similarity). Tune per deployment.
IDENTITY_VOICE_THRESHOLD = env.float("IDENTITY_VOICE_THRESHOLD", default=0.75)
IDENTITY_FACE_THRESHOLD = env.float("IDENTITY_FACE_THRESHOLD", default=0.6)

from celery.schedules import crontab
CELERY_BEAT_SCHEDULE = {
    'weekly_finetuning_cycle': {
        'task': 'learning.tasks.weekly_finetuning_cycle',
        'schedule': crontab(day_of_week='sun', hour=2, minute=0),
    },
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL = env.str("DJANGO_LOG_LEVEL", default="INFO")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "%(asctime)s %(levelname)s %(name)s %(process)d %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "aimw": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "ingestion": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
    },
}
