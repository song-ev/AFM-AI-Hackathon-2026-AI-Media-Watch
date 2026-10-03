from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
    verbose_name = "Accounts / users & roles"

    def ready(self):
        # Connect post_save signals (cases_reviewed_count bookkeeping).
        from accounts import signals  # noqa: F401
