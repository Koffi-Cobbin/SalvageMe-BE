"""
Base settings shared by every environment.

Environment-specific modules (dev.py / staging.py / prod.py) import * from
this module and override only what genuinely differs between environments.
No `if DEBUG:` branching should live outside these settings modules.
"""
from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
# .env is optional — on PythonAnywhere/staging/prod, real env vars are set
# directly in the environment (e.g. via the WSGI config or a bashrc export).
env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(str(env_file))

SECRET_KEY = env("DJANGO_SECRET_KEY", default="insecure-dev-key-change-me")
DEBUG = False
ALLOWED_HOSTS: list[str] = []

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "drf_spectacular",
    "django_filters",
    "corsheaders",
]

LOCAL_APPS = [
    "apps.accounts",
    "apps.listings",
    "apps.requests",
    "apps.exchanges",
    "apps.dropoff",
    "apps.moderation",
    "apps.notifications",
    "apps.analytics",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Database
#
# Two supported engines, chosen via the DB_ENGINE env var:
#   - "postgis"    (default) — PostgreSQL + PostGIS. Required for staging/prod
#                    (see staging.py/prod.py, which hardcode it regardless of
#                    DB_ENGINE) and recommended for dev if you want geo-search
#                    behaviour to match production exactly.
#   - "spatialite" — SQLite + the SpatiaLite extension. A zero-setup local
#                    dev option (no DB server to run) that still supports
#                    GeoDjango's PointField/geo lookups, unlike plain sqlite3
#                    (which has no spatial support at all). dev.py defaults
#                    to this. Requires the `libsqlite3-mod-spatialite` system
#                    package — see README "Local setup".
#
# NOTE: SpatiaLite has no true "geography" column type, so distance
# calculations there are planar (Cartesian) rather than PostGIS's geodesic
# calculation — fine for local dev, but geo-search distances will differ
# slightly from production. See README "Known limitations".
# ---------------------------------------------------------------------------
def build_databases(default_engine: str) -> dict:
    engine = env("DB_ENGINE", default=default_engine)

    if engine == "spatialite":
        return {
            "default": {
                "ENGINE": "django.contrib.gis.db.backends.spatialite",
                "NAME": env("DB_NAME", default=str(BASE_DIR / "db.sqlite3")),
            }
        }

    return {
        "default": {
            "ENGINE": "django.contrib.gis.db.backends.postgis",
            "NAME": env("DB_NAME", default="salvageme"),
            "USER": env("DB_USER", default="postgres"),
            "PASSWORD": env("DB_PASSWORD", default="postgres"),
            "HOST": env("DB_HOST", default="localhost"),
            "PORT": env("DB_PORT", default="5432"),
        }
    }


DATABASES = build_databases(default_engine="postgis")

# Only relevant when DB_ENGINE=spatialite. On Debian/Ubuntu the extension
# ships as `mod_spatialite`, not `libspatialite` (the name GeoDjango's
# ctypes.util.find_library() lookup expects by default), so it has to be
# named explicitly here.
SPATIALITE_LIBRARY_PATH = env("SPATIALITE_LIBRARY_PATH", default="mod_spatialite")


def assert_no_localhost_cors_origins(origins: list[str]) -> None:
    """
    Called by staging.py/prod.py after resolving CORS_ALLOWED_ORIGINS.
    Catches the same class of mistake as the DB_ENGINE/ALLOWED_HOSTS guards
    above: a .env copied from the local-dev template (which points at
    http://localhost:3000) deployed as-is to a real environment, silently
    locking out the real frontend rather than failing loudly.
    """
    from django.core.exceptions import ImproperlyConfigured

    localhost_origins = [o for o in origins if "localhost" in o or "127.0.0.1" in o]
    if localhost_origins:
        raise ImproperlyConfigured(
            f"CORS_ALLOWED_ORIGINS contains localhost origin(s) {localhost_origins} outside local "
            f"dev — this looks like a .env copied from .env.example rather than "
            f".env.production.example. Set CORS_ALLOWED_ORIGINS to your real deployed frontend "
            f"origin(s)."
        )

# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# I18N
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# DRF
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_PAGINATION_CLASS": "common.pagination.CursorSetPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "common.exceptions.custom_exception_handler",
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=14),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

# Refresh token is delivered as an httpOnly cookie by our own auth views
# (apps/accounts/views.py), not by simplejwt's default views.
REFRESH_COOKIE_NAME = "salvageme_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth/"
REFRESH_COOKIE_SECURE = True
REFRESH_COOKIE_SAMESITE = "Lax"

INSTALLED_APPS += ["rest_framework_simplejwt.token_blacklist"]

SPECTACULAR_SETTINGS = {
    "TITLE": "SalvageMe API",
    "DESCRIPTION": (
        "API for SalvageMe, a community book/educational-material exchange "
        "platform connecting donors with recipients (students, families, "
        "schools)."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": r"/api/v[0-9]+",
}

# ---------------------------------------------------------------------------
# CORS — explicit allowlist only, never CORS_ALLOW_ALL_ORIGINS in any
# environment other than local dev.
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_CREDENTIALS = True

# ---------------------------------------------------------------------------
# FileForge (server-to-server file storage boundary — see
# common/fileforge_client.py). Never exposed to the frontend.
# ---------------------------------------------------------------------------
FILEFORGE_BASE_URL = env("FILEFORGE_BASE_URL", default="https://fileforge1.pythonanywhere.com")
FILEFORGE_API_KEY = env("FILEFORGE_API_KEY", default="ffk_1IVK8jHO23O-qCORwplwAhud38j5Ks14QmPpG_uY")
FILEFORGE_TIMEOUT_SECONDS = env.float("FILEFORGE_TIMEOUT_SECONDS", default=10.0)

# ---------------------------------------------------------------------------
# Caching — local-memory/database backend only. No Redis (see
# ASYNC & SCHEDULED WORK: PythonAnywhere free tier has no worker process).
# ---------------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "salvageme-cache",
    }
}

# ---------------------------------------------------------------------------
# Email — synchronous send_mail in the request cycle (see
# apps/notifications). Backend is overridden per-environment.
# ---------------------------------------------------------------------------
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@salvageme.example")

# Business-rule thresholds, centralised here so they're easy to tune without
# hunting through service functions.
PENDING_REQUEST_EXPIRY_DAYS = env.int("PENDING_REQUEST_EXPIRY_DAYS", default=14)
EXCHANGE_REMINDER_WINDOW_HOURS = env.int("EXCHANGE_REMINDER_WINDOW_HOURS", default=24)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "salvageme": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
