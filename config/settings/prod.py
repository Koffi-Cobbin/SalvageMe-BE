from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import build_databases, env, assert_no_localhost_cors_origins

# NOTE: on PythonAnywhere this module is loaded via the WSGI config file
# PythonAnywhere generates for you — see README "Deploying to PythonAnywhere"
# for the exact `os.environ["DJANGO_SETTINGS_MODULE"]` wiring.

DEBUG = False
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])  # bare hostname only — no scheme, no path — e.g. "salvageme.pythonanywhere.com"

# Production must use PostGIS, regardless of any DB_ENGINE=spatialite left
# over from a shared/copied .env — sqlite is a dev-only convenience.
DATABASES = build_databases(default_engine="postgis")
if DATABASES["default"]["ENGINE"] != "django.contrib.gis.db.backends.postgis":
    raise ImproperlyConfigured("Production must use PostGIS — refusing to start with DB_ENGINE=spatialite.")

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
assert_no_localhost_cors_origins(CORS_ALLOWED_ORIGINS)

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = True

# --- Django SECURE_* hardening -------------------------------------------
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30  # 30 days
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
REFRESH_COOKIE_SECURE = True
X_FRAME_OPTIONS = "DENY"

# PythonAnywhere terminates TLS in front of the app; trust its proxy header
# so SECURE_SSL_REDIRECT doesn't cause a redirect loop.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_RATES": {"auth": "10/min"},
}
