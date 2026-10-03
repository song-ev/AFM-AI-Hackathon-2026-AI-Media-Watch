"""Request-timing decorator for the latency-sensitive bank endpoints."""
import functools
import logging
import time

logger = logging.getLogger("bankapi")


def log_response_time(view_method):
    """Log handler wall-time and expose it via the X-Response-Time-ms header.

    The bank risk-check has a tight SLA (< 200ms in production); this surfaces
    the per-request time so regressions are visible in logs.
    """

    @functools.wraps(view_method)
    def wrapper(self, request, *args, **kwargs):
        start = time.perf_counter()
        response = view_method(self, request, *args, **kwargs)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        logger.info("%s handled in %.1f ms", request.path, elapsed_ms)
        response["X-Response-Time-ms"] = f"{elapsed_ms:.1f}"
        return response

    return wrapper
