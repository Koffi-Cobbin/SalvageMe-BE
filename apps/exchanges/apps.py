from django.apps import AppConfig


class ExchangesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.exchanges"
    label = "exchanges"

    def ready(self):
        import apps.exchanges.signals  # noqa: F401
