"""Django admin for bankapi. Keys are read-only — never editable by hand."""
from django.contrib import admin

from bankapi.models import BankApiKey


@admin.register(BankApiKey)
class BankApiKeyAdmin(admin.ModelAdmin):
    list_display = ("prefix", "bank_admin", "is_active", "last_used_at", "created_at")
    list_filter = ("is_active",)
    search_fields = ("prefix", "bank_admin__username")
    raw_id_fields = ("bank_admin",)
    # The hash and usage data are managed by the auth layer / command, not by hand.
    readonly_fields = ("key_hash", "prefix", "last_used_at", "created_at", "updated_at")

    def has_add_permission(self, request):
        # Keys are issued via the generate_bank_api_key command (raw key shown once).
        return False
