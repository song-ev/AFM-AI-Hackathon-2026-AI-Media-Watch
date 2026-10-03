"""
Project-wide error types and DRF exception handling.

`ModuleDependencyError` is the backbone of the production "fail-loud" policy:
an analysis step that needs an external model, library or API key it cannot
reach raises this instead of fabricating a result. Callers (the Celery tasks)
catch it, record the failure on the relevant record, and contribute *nothing*
to the risk score — a missing model must never look like a clean verdict.
"""
import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_default_handler

logger = logging.getLogger("aimw")


class ModuleDependencyError(RuntimeError):
    """A required external dependency (model / library / API key) is unavailable.

    Args:
        module: short identifier of the analysis module (e.g. "frame_analysis").
        detail: human-readable explanation of what is missing and how to fix it.
    """

    def __init__(self, module: str, detail: str):
        self.module = module
        self.detail = detail
        super().__init__(f"[{module}] {detail}")


def custom_exception_handler(exc, context):
    """DRF's default error response, normalised into a consistent envelope.

    Unhandled server errors are logged with full context and returned as a
    generic 500 (no internal detail leaks to the client in production).
    """
    response = drf_default_handler(exc, context)

    if response is not None:
        response.data = {
            "error": True,
            "status_code": response.status_code,
            "detail": response.data,
        }
        return response

    # Not a DRF-handled exception → genuine server error. Log it and return a
    # safe, generic payload rather than leaking a traceback.
    view = context.get("view") if context else None
    logger.exception("Unhandled exception in %s", getattr(view, "__class__", view))
    return Response(
        {
            "error": True,
            "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
            "detail": "Internal server error.",
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
