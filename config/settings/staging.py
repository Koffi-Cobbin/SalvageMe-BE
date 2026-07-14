from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import build_databases, env, assert_no_localhost_cors_origins

DEBUG = False
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

# Staging must exercise the same PostGIS geo behaviour as production,
# regardless of any DB_ENGINE=spatialite left over from a shared .env.
DATABASES = build_databases(default_engine="postgis")
if DATABASES["default"]["ENGINE"] != "django.contrib.gis.db.backends.postgis":
    raise ImproperlyConfigured("Staging must use PostGIS — refusing to start with DB_ENGINE=spatialite.")

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
assert_no_localhost_cors_origins(CORS_ALLOWED_ORIGINS)

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = True

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
REFRESH_COOKIE_SECURE = True

REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_RATES": {"auth": "10/min"},
}
