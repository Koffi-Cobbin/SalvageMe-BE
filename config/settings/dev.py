from .base import *  # noqa: F401,F403
from .base import build_databases, env

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]

# SQLite (via SpatiaLite) by default for a zero-setup local dev experience —
# set DB_ENGINE=postgis in .env to point dev at a real Postgres+PostGIS
# instance instead (e.g. to debug something that behaves differently there).
DATABASES = build_databases(default_engine="spatialite")

CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS", default=["http://localhost:3000", "http://127.0.0.1:3000", "https://salvageme.pythonanywhere.com"]
)

REFRESH_COOKIE_SECURE = False  # allow http on localhost

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Looser throttle scopes in dev so manual testing/Postman collections don't
# trip rate limits while iterating.
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": {"auth": "100/min"}}  # noqa: F405
