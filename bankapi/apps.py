from django.apps import AppConfig


class BankapiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "bankapi"
    verbose_name = "Bank API / external REST integration"
