from django.apps import AppConfig


class RequestsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.requests"
    label = "requests_app"  # "requests" is avoided as the app_label purely
    # to keep manage.py shell/`django-admin` output unambiguous from the
    # `requests` HTTP library that's also a dependency in this project;
    # Python import resolution is unaffected either way (absolute imports).

    def ready(self):
        import apps.requests.signals  # noqa: F401
