"""Throttling for bank integrations — a dedicated, stricter rate bucket.

Apply BankApiKeyRateThrottle on bankapi views (block C). The rate is defined
under DEFAULT_THROTTLE_RATES["bank"] in settings.
"""
from rest_framework.throttling import SimpleRateThrottle


class BankApiKeyRateThrottle(SimpleRateThrottle):
    """Throttle per authenticated bank API key, in the 'bank' rate bucket."""

    scope = "bank"

    def get_cache_key(self, request, view):
        # request.auth is the BankApiKey instance set by BankApiKeyAuthentication.
        api_key = getattr(request, "auth", None)
        if api_key is None or not getattr(api_key, "pk", None):
            return None  # not a bank-authenticated request — don't throttle here
        return self.cache_format % {"scope": self.scope, "ident": api_key.pk}
