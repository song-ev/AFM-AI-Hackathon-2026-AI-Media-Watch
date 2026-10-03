# Production deployment

This document describes what is required to run AI Media Watch in production and
the **fail-loud** policy that replaced the demo stubs.

## Fail-loud policy (no fabricated data)

Every analysis step depends on an external model, library or API key. In
production a missing dependency must **never** silently produce a fake result
(that could let fraud pass as "clean"). Instead:

- **Stage 1 (screening):** a module that cannot run raises
  `core.exceptions.ModuleDependencyError`; its `ScreeningSignal` is persisted
  with `error` set and contributes nothing to the verdict. If *every* domain
  module errors, the `ScreeningResult` status is `error` (not `clean`).
- **Stage 2 (deep analysis):** each step (transcription, semantic LLM, fake
  screenshot, identity, summary) is wrapped; failures are recorded in
  `DeepAnalysisResult.step_errors` and the step is skipped. The risk score is
  computed only from steps that genuinely ran.

So a model/key you did not configure shows up as a recorded error, not as a
green light.

## Required external assets & services

| Capability | Requirement | If missing |
| --- | --- | --- |
| Frame OCR | `tesseract-ocr` binary (`TESSERACT_CMD`) | frame module errored |
| Logo detection | YOLO weights **fine-tuned on casino/gambling logos** at `YOLO_MODEL_PATH` + `YOLO_LOGO_CLASSES` | no logo flags (OCR still runs) |
| Audio transcription | `openai-whisper` + ffmpeg | audio / transcription errored |
| Voice identity | `resemblyzer` | identity errored |
| Face identity | `face_recognition` (dlib) | identity errored |
| Semantic analysis & summaries | `LLM_API_KEY` + endpoint/model, or `ANTHROPIC_API_KEY` + `ANTHROPIC_BASE_URL` + `ANTHROPIC_MODEL` | those steps errored |
| Database | PostgreSQL (`DATABASE_URL`) | app will not start |
| Task queue | Redis + Celery worker **and beat** | async pipeline / weekly learning won't run |

> The base `yolov8n.pt` is a generic COCO model. Logo detection only flags
> classes listed in `YOLO_LOGO_CLASSES`; until you ship a fine-tuned model with
> its class names, YOLO contributes nothing — by design, not by accident.

## Configuration

All config is environment-driven (`django-environ`). See `.env.example`.
Production settings (`ai_media_watch.settings.prod`) enforce: `DEBUG=False`, a
non-default `DJANGO_SECRET_KEY` (refuses to start otherwise), HSTS/SSL redirect,
secure cookies, `nosniff`, `X-Frame-Options: DENY`, JSON-only renderer.

```bash
cp .env.example .env            # then edit; set real secrets
export DJANGO_SETTINGS_MODULE=ai_media_watch.settings.prod
```

## Deploy (Docker)

This is a backend deployment template, not a verified production release. It does not include the frontend or TLS proxy. Model weights and cookies must be mounted separately, read-only. Copy `.env.example` to `.env` and replace all development credentials. The `.env` file is supplied at runtime and excluded from image builds.

```bash
# Provide secrets in the environment first (DJANGO_SECRET_KEY, POSTGRES_PASSWORD,
# DJANGO_ALLOWED_HOSTS, DJANGO_CORS_ALLOWED_ORIGINS, ANTHROPIC_API_KEY, ...).
docker compose -f docker-compose.prod.yml up -d --build
```

This runs `migrate` + `collectstatic` + gunicorn, plus a Celery `worker` and
`beat`. Put a TLS-terminating reverse proxy (nginx/Caddy/ALB) in front and serve
`staticfiles/` + `media/`.

## Roles & first user

Roles: `analyst` вЉ‚ `afm_lead` вЉ‚ `system_admin` (internal), and `bank_admin`
(external, bankapi only). Create the first admin with
`python manage.py createsuperuser` (role defaults to analyst; set
`system_admin` in the admin). `create_demo_users` / `seed_learning_demo` refuse
to run when `DEBUG=False`.

## Stage 4 self-learning

The weekly Celery-beat job trains a real risk classifier on analyst decisions
(`learning.training.train_risk_model`) and deploys it only if precision does not
regress. Train on demand: `python manage.py train_risk_model --show-importances`.
Inspect via `GET /api/learning/model/active/`.

## Pre-flight checklist

- [ ] `DJANGO_SECRET_KEY` set (long random), `DJANGO_DEBUG=False`
- [ ] `DJANGO_ALLOWED_HOSTS` / CORS set to real domains
- [ ] PostgreSQL + Redis reachable; Celery worker **and** beat running
- [ ] `tesseract`, ffmpeg present; Whisper model available
- [ ] Fine-tuned `YOLO_MODEL_PATH` + `YOLO_LOGO_CLASSES` (or accept no logo flags)
- [ ] `LLM_API_KEY` (with endpoint/model) or `ANTHROPIC_API_KEY` + `ANTHROPIC_BASE_URL` + `ANTHROPIC_MODEL` set (or accept errored semantic/summary steps)
- [ ] `python manage.py migrate` and `collectstatic` run
- [ ] `python manage.py check --deploy` passes
