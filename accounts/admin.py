"""Django admin for accounts: users, roles, profiles and analyst labels."""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from accounts.models import (
    AnalystLabel,
    AnalystProfile,
    BankAdminProfile,
    User,
)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    # Extend the default UserAdmin with the custom `role` field.
    list_display = ("username", "email", "role", "is_staff", "is_active")
    list_filter = ("role", "is_staff", "is_superuser", "is_active")
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("AFM role", {"fields": ("role",)}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("AFM role", {"fields": ("role",)}),
    )


@admin.register(AnalystProfile)
class AnalystProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "department", "cases_reviewed_count")
    search_fields = ("user__username", "department")
    raw_id_fields = ("user",)
    readonly_fields = ("cases_reviewed_count",)


@admin.register(BankAdminProfile)
class BankAdminProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "bank_name", "api_key_label")
    list_filter = ("bank_name",)
    search_fields = ("user__username", "api_key_label")
    raw_id_fields = ("user",)


@admin.register(AnalystLabel)
class AnalystLabelAdmin(admin.ModelAdmin):
    list_display = ("incident", "decision", "analyst", "decided_at")
    list_filter = ("decision",)
    search_fields = (
        "analyst__username",
        "comment",
        "incident__video__external_id",
    )
    raw_id_fields = ("incident", "analyst")
    date_hierarchy = "decided_at"
