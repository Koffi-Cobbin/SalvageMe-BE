from .base import *  # noqa: F401,F403
from .base import env

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]

CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS", default=["http://localhost:3000", "http://127.0.0.1:3000"]
)

REFRESH_COOKIE_SECURE = False  # allow http on localhost

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Looser throttle scopes in dev so manual testing/Postman collections don't
# trip rate limits while iterating.
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": {"auth": "100/min"}}  # noqa: F405
