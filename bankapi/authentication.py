"""
Custom DRF authentication for bank integrations.

Reads `Authorization: ApiKey <key>`, hashes the key and matches it against an
active BankApiKey, then stamps last_used_at. Deliberately NOT JWT — banks are
external systems, not interactive users.
"""
from django.utils import timezone
from rest_framework import authentication, exceptions

from bankapi.models import BankApiKey, hash_api_key

KEYWORD = "ApiKey"


class BankApiKeyAuthentication(authentication.BaseAuthentication):
    """Authenticate a request via `Authorization: ApiKey <key>`."""

    def authenticate(self, request):
        auth = authentication.get_authorization_header(request).split()
        if not auth or auth[0].decode().lower() != KEYWORD.lower():
            # Not an ApiKey request — let other authenticators handle it.
            return None
        if len(auth) == 1:
            raise exceptions.AuthenticationFailed("Invalid ApiKey header: no credentials.")
        if len(auth) > 2:
            raise exceptions.AuthenticationFailed(
                "Invalid ApiKey header: token may not contain spaces."
            )

        raw_key = auth[1].decode()
        key_hash = hash_api_key(raw_key)
        try:
            api_key = BankApiKey.objects.select_related("bank_admin").get(
                key_hash=key_hash, is_active=True
            )
        except BankApiKey.DoesNotExist:
            raise exceptions.AuthenticationFailed("Invalid or inactive API key.")

        # Stamp usage without touching updated_at semantics elsewhere.
        BankApiKey.objects.filter(pk=api_key.pk).update(last_used_at=timezone.now())

        return (api_key.bank_admin, api_key)

    def authenticate_header(self, request):
        # Drives the WWW-Authenticate header on 401s.
        return KEYWORD
