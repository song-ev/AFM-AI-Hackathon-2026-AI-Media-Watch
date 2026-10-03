"""
Unified LLM client for the whole project.

Users configure their own credentials, endpoint, and model through ``LLM_*``
or ``ANTHROPIC_*`` settings. No provider endpoint is supplied by this project.
This module unifies both behind one ``call_llm`` / ``call_llm_json`` API so every AI step
(semantic analysis, incident summaries, geo inference, audio reasoning, …) uses
the same, configurable backend.

Fail-loud policy (see core.exceptions.ModuleDependencyError): if no backend is
configured/reachable the call raises ``ModuleDependencyError`` so the caller
records a step error rather than fabricating a neutral result.

Backend selection (in order):
1. ``LLM_API_KEY`` set  -> OpenAI-compatible endpoint at ``LLM_BASE_URL``.
2. ``ANTHROPIC_API_KEY`` set -> Anthropic SDK (``ANTHROPIC_MODEL``).
3. neither -> ModuleDependencyError.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from django.conf import settings

from core.exceptions import ModuleDependencyError

logger = logging.getLogger("aimw")

# Cached OpenAI client per worker process (cheap to reuse, keeps the HTTP pool).
_OPENAI_CLIENT = None


def _module_name(module: Optional[str]) -> str:
    return module or "llm"


def llm_is_configured() -> bool:
    """True if any LLM backend is configured (used for UI/health hints)."""
    prefix = "LLM" if active_backend() == "openai" else "ANTHROPIC"
    return all(getattr(settings, f"{prefix}_{field}", "").strip()
               for field in ("API_KEY", "BASE_URL", "MODEL"))


def _require_config(prefix: str) -> dict:
    config = {field: getattr(settings, f"{prefix}_{field}", "").strip()
              for field in ("API_KEY", "BASE_URL", "MODEL")}
    missing = [f"{prefix}_{field}" for field, value in config.items() if not value]
    if missing:
        raise ModuleDependencyError("llm", "Configure your own " + ", ".join(missing) + ".")
    return config


def active_backend() -> str:
    """Return which backend a call would use: 'openai', 'anthropic' or 'none'."""
    if getattr(settings, "LLM_API_KEY", ""):
        return "openai"
    if getattr(settings, "ANTHROPIC_API_KEY", ""):
        return "anthropic"
    return "none"


def _get_openai_client():
    global _OPENAI_CLIENT
    config = _require_config("LLM")
    if _OPENAI_CLIENT is not None:
        return _OPENAI_CLIENT
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - dep listed in requirements
        raise ModuleDependencyError(
            "llm", "openai SDK is not installed; cannot reach the LLM endpoint."
        ) from exc
    _OPENAI_CLIENT = OpenAI(
        base_url=config["BASE_URL"],
        api_key=config["API_KEY"],
        timeout=getattr(settings, "LLM_TIMEOUT", 120.0),
    )
    return _OPENAI_CLIENT


def _call_openai(
    *, system: str, user: str, max_tokens: int, temperature: float, json_mode: bool
) -> str:
    client = _get_openai_client()
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})

    kwargs = {
        "model": settings.LLM_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if json_mode and getattr(settings, "LLM_FORCE_JSON", False):
        # Only some endpoints honour this; guarded by a flag so a model that
        # rejects response_format does not hard-fail every call.
        kwargs["response_format"] = {"type": "json_object"}

    resp = client.chat.completions.create(**kwargs)
    return (resp.choices[0].message.content or "").strip()


def _call_anthropic(
    *, system: str, user: str, max_tokens: int, temperature: float
) -> str:
    config = _require_config("ANTHROPIC")
    try:
        from anthropic import Anthropic
    except ImportError as exc:
        raise ModuleDependencyError("llm", "anthropic SDK is not installed.") from exc
    client = Anthropic(api_key=config["API_KEY"], base_url=config["BASE_URL"])
    kwargs = {
        "model": config["MODEL"],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": user}],
    }
    if system:
        kwargs["system"] = system
    resp = client.messages.create(**kwargs)
    return resp.content[0].text.strip()


def call_llm(
    user: str,
    *,
    system: str = "",
    max_tokens: int = 600,
    temperature: float = 0.2,
    json_mode: bool = False,
    module: Optional[str] = None,
) -> str:
    """Call the configured LLM and return raw text.

    Raises ModuleDependencyError (fail-loud) when no backend is configured or the
    request errors, so callers record a step error rather than fabricating data.
    """
    backend = active_backend()
    mod = _module_name(module)
    if backend == "none":
        raise ModuleDependencyError(
            mod,
            "No LLM configured: set LLM_API_KEY (OpenAI-compatible) or "
            "ANTHROPIC_API_KEY.",
        )
    try:
        if backend == "openai":
            return _call_openai(
                system=system,
                user=user,
                max_tokens=max_tokens,
                temperature=temperature,
                json_mode=json_mode,
            )
        return _call_anthropic(
            system=system, user=user, max_tokens=max_tokens, temperature=temperature
        )
    except ModuleDependencyError:
        raise
    except Exception as exc:  # noqa: BLE001 - network/model errors -> fail loud
        # Provider exceptions may contain request URLs or credential fragments.
        logger.warning("LLM call failed (%s/%s): %s", backend, mod, type(exc).__name__)
        raise ModuleDependencyError(
            mod, f"LLM request failed ({type(exc).__name__}). Check your provider configuration."
        ) from None


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> str:
    """Best-effort pull of a JSON object out of a chat response."""
    fence = _JSON_FENCE_RE.search(text)
    if fence:
        return fence.group(1).strip()
    obj = _JSON_OBJECT_RE.search(text)
    if obj:
        return obj.group(0)
    return text.strip()


def call_llm_json(
    user: str,
    *,
    system: str = "",
    max_tokens: int = 700,
    temperature: float = 0.1,
    module: Optional[str] = None,
    default: Optional[dict] = None,
) -> dict:
    """Call the LLM and parse a JSON object out of the reply.

    On a parse failure: returns ``default`` if provided, otherwise raises
    ModuleDependencyError (so the step is recorded as errored, never fabricated).
    """
    mod = _module_name(module)
    raw = call_llm(
        user,
        system=system,
        max_tokens=max_tokens,
        temperature=temperature,
        json_mode=True,
        module=mod,
    )
    try:
        return json.loads(_extract_json(raw))
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("LLM JSON parse failed (%s): %s | raw=%.200s", mod, exc, raw)
        if default is not None:
            return dict(default)
        raise ModuleDependencyError(
            mod, f"LLM returned non-JSON output: {raw[:200]}"
        ) from exc
