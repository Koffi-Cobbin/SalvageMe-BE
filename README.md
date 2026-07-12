# SalvageMe Backend

A Django + Django REST Framework API for **SalvageMe**, a community book/educational-material
exchange platform connecting donors with recipients (students, families, schools).

Built to run on a **free-tier PythonAnywhere account** in production: no Celery, no Redis, no
persistent background worker — see [Async & scheduled work](#async--scheduled-work) below.

---

## Tech stack

| Concern            | Choice                                                  |
|---------------------|------------------------------------------------------------|
| Framework           | Django 5.0 + Django REST Framework                       |
| Auth                | `djangorestframework-simplejwt` — access token + httpOnly refresh cookie |
| Database            | PostgreSQL + PostGIS                                      |
| File storage        | [FileForge](https://github.com/Koffi-Cobbin/FileForge) (server-to-server client only) |
| API schema          | `drf-spectacular` (OpenAPI 3)                              |
| Filtering           | `django-filter`                                            |
| Testing             | `pytest-django` + `factory_boy`                             |
| Lint/format         | `ruff`                                                      |
| Dependency mgmt     | `pip-tools` (`requirements.in` → `requirements.txt`)        |
| Local containerization | Docker + docker-compose (`web`, `db` — no `redis`)       |

---

## Project layout

```
config/settings/{base,dev,staging,prod}.py   # env-specific settings; no `if DEBUG` in app code
apps/
  accounts/       # custom User, JWT auth, ratings
  listings/       # Category, Listing, ListingPhoto, FileForge-backed photo uploads
  requests/       # BookRequest lifecycle (create/accept/decline/expire)
  exchanges/      # Exchange lifecycle (schedule/complete/cancel/rate)
  dropoff/        # DropOffPoint
  moderation/     # Report, AuditLog
  notifications/  # synchronous email sends (no queue)
  analytics/      # cached ImpactStatsSnapshot + /api/v1/stats/impact/
common/           # permissions.py, pagination.py, exceptions.py, mixins.py, fileforge_client.py
tests/factories.py  # factory_boy factories for every model, shared across apps
```

Each domain app follows `models.py`, `serializers.py`, `views.py`, `permissions.py` (where
needed), `urls.py`, `admin.py`, `signals.py`, `tests/`.

---

## Local setup

### Option A — Docker (recommended, no local GDAL/Postgres install needed)

```bash
cp .env.example .env          # fill in FILEFORGE_API_KEY etc. — safe defaults otherwise
docker-compose up
```

This builds the `web` image (which includes GDAL/GEOS/PostGIS client libs), starts Postgres+PostGIS
as `db`, runs migrations automatically, and serves the API at `http://localhost:8000`.

### Option B — Bare metal

Requires: Python 3.12, PostgreSQL 16 with the PostGIS extension available, and GDAL/GEOS system
libraries (GeoDjango needs these — `apt-get install gdal-bin libgdal-dev libproj-dev` on Debian/Ubuntu).

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt

cp .env.example .env          # edit DB_*, FILEFORGE_* as needed

# create the database + enable PostGIS (adjust for your local postgres setup)
createdb salvageme
psql -d salvageme -c "CREATE EXTENSION IF NOT EXISTS postgis;"

python manage.py migrate
python manage.py createsuperuser
python manage.py seed_demo_data
python manage.py runserver
```

Verify it's up: `curl http://localhost:8000/api/health/` → `{"status": "ok", "database": true}`.

---

## Environment variables

See [`.env.example`](.env.example) for the full list with inline comments. Highlights:

- `DJANGO_SECRET_KEY` — required in staging/prod; dev.py has an insecure fallback for convenience.
- `DB_NAME` / `DB_USER` / `DB_PASSWORD` / `DB_HOST` / `DB_PORT` — Postgres connection.
- `CORS_ALLOWED_ORIGINS` — comma-separated explicit allowlist. Never `*` outside dev.
- `FILEFORGE_BASE_URL` / `FILEFORGE_API_KEY` — see below.
- `PENDING_REQUEST_EXPIRY_DAYS`, `EXCHANGE_REMINDER_WINDOW_HOURS` — business-rule tuning.

No secrets are committed anywhere in this repo — `.env` is git-ignored, only `.env.example` (with
placeholder values) is tracked.

---

## FileForge integration (file storage)

SalvageMe never touches raw file bytes on disk and never talks to a cloud storage provider (S3,
Cloudinary, Google Drive) directly. All `ListingPhoto`/avatar uploads go through
[FileForge](https://github.com/Koffi-Cobbin/FileForge), a separate DRF service that brokers to a
pluggable storage backend. The **only** code in this repo allowed to call FileForge's HTTP API is
`common/fileforge_client.py::FileForgeClient` — views/serializers call `add_listing_photo()` /
`delete_listing_photo()` in `apps/listings/services.py`, which use the client wrapper.

### Standing up FileForge for local dev

1. Clone and run FileForge per its own README (it's a separate Django project):
   `git clone https://github.com/Koffi-Cobbin/FileForge && cd FileForge` and follow its setup.
2. Register an "App" in FileForge and generate an API key (`ffk_...`).
3. Configure at least one storage provider credential in FileForge itself (Cloudinary is the
   quickest to start with for local dev).
4. Point this backend at it via `.env`:
   ```
   FILEFORGE_BASE_URL=http://localhost:9000
   FILEFORGE_API_KEY=ffk_your_key_here
   ```

If you don't need to test the upload flow locally, you can leave the placeholder values in
`.env.example` — every other endpoint works fine without a real FileForge instance running; only
`POST /api/v1/listings/{id}/photos/` needs it.

---

## Running migrations & seed data

```bash
python manage.py migrate
python manage.py seed_demo_data          # add demo users/categories/listings
python manage.py seed_demo_data --flush  # wipe demo users/listings first, then reseed
```

`seed_demo_data` creates 5 demo users (a mix of donor/recipient/both roles, all with password
`DemoPass123!`), 5 categories, 8 listings across various conditions/grade levels, a pending
request, an in-progress exchange, and one drop-off point — enough for a frontend dev to exercise
every screen without hand-crafting data via the admin.

---

## Running tests

```bash
pytest                 # full suite
pytest apps/listings/  # single app
pytest -k "test_accept" -v
```

Tests run against a real PostgreSQL+PostGIS database (created/torn down automatically by
`pytest-django`; `--reuse-db` is enabled in `pytest.ini` so repeat runs are fast — pass
`--create-db` to force a fresh one after a migration change).

```bash
ruff check .                              # lint
python manage.py makemigrations --check   # confirm no missing migrations
```

---

## OpenAPI schema

```bash
python manage.py spectacular --file schema.yaml                  # generate to a file
python manage.py spectacular --file schema.yaml --fail-on-warn   # CI-strength check
```

Interactive docs are also served at `/api/docs/` (Swagger UI) and `/api/redoc/` (Redoc) when the
app is running; the raw schema is at `/api/schema/`. The frontend team generates its TypeScript
client from this schema — CI regenerates and validates it on every push (see `.github/workflows/ci.yml`).

---

## Async & scheduled work

PythonAnywhere's free tier has **no persistent worker process** — no Celery worker/beat, no
Django-Q cluster, no Redis. This backend is designed around that constraint rather than working
around it later:

- **Notifications are sent synchronously**, inline in the request that triggers them (e.g. an
  email fires during the `accept` request, not via a queue). See `apps/notifications/services.py` —
  every send is wrapped so an email-provider hiccup never breaks the underlying API call.
- **Periodic work** (expiring stale pending requests, recomputing cached impact stats, sending
  exchange reminders, reconciling FileForge-backed photos) is consolidated into a single management
  command, `python manage.py run_daily_jobs`, meant to be wired up as **one** PythonAnywhere
  Scheduled Task (free accounts get a limited number of daily task slots).
- Because the scheduled task only runs once a day, reminders aren't "exactly 24h before" — the job
  catches anything whose `scheduled_at` falls within the next `EXCHANGE_REMINDER_WINDOW_HOURS`
  window. This is a deliberate, documented limitation, not a bug.
- Caching uses Django's local-memory backend (`CACHES` in `base.py`) — no Redis.

### PythonAnywhere Scheduled Task setup

In the PythonAnywhere dashboard → **Tasks** tab, add one daily task:

```
workon /home/yourusername/salvageme_backend/venv && cd /home/yourusername/salvageme_backend && python manage.py run_daily_jobs
```

(Adjust the venv/project paths to match your actual PythonAnywhere account layout.)

---

## Deploying to PythonAnywhere (production)

PythonAnywhere's free tier runs your app under its **own WSGI configuration**, not `gunicorn`
directly, and has no push-to-deploy CI/CD — deployment is a manual `git pull` + reload. There is
no Docker on PythonAnywhere; the `Dockerfile`/`docker-compose.yml` in this repo are for local dev
only.

1. **One-time setup** (PythonAnywhere Bash console):
   ```bash
   git clone <your-repo-url> salvageme_backend
   cd salvageme_backend
   python3.12 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt   # production deps only, not requirements-dev.txt
   ```
2. Create a Postgres database (see [Deviations](#deviations--assumptions) below for a note on
   Postgres availability on PythonAnywhere's literal free tier).
3. Set environment variables. PythonAnywhere doesn't read `.env` automatically for WSGI apps —
   either `export` them at the top of the WSGI configuration file (Web tab → WSGI configuration
   file) before the Django import, or rely on `.env` in the project root, which
   `config/settings/base.py` already loads via `django-environ` if present.
4. In the **Web** tab's WSGI configuration file:
   ```python
   import os, sys

   path = "/home/yourusername/salvageme_backend"
   if path not in sys.path:
       sys.path.insert(0, path)

   os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.prod"

   from config.wsgi import application
   ```
5. Set the **Source code** / **Working directory** to the project root, and the **Virtualenv** path
   to `/home/yourusername/salvageme_backend/venv`.
6. Run migrations and collect static files from the Bash console:
   ```bash
   python manage.py migrate
   python manage.py collectstatic --noinput
   python manage.py createsuperuser
   ```
7. Hit **Reload** on the Web tab.
8. **Every subsequent deploy**:
   ```bash
   cd salvageme_backend && git pull
   source venv/bin/activate && pip install -r requirements.txt
   python manage.py migrate
   python manage.py collectstatic --noinput
   ```
   then click **Reload** on the Web tab again. There's no automated CI/CD push-to-deploy on the
   free tier — this manual sequence is the actual production deploy process.
9. Confirm `https://yourusername.pythonanywhere.com/api/health/` responds `{"status": "ok", ...}`.

---

## Security notes

- CORS is an explicit allowlist (`CORS_ALLOWED_ORIGINS`) in every environment — never
  `CORS_ALLOW_ALL_ORIGINS`.
- `register`/`login` are throttled (`ScopedRateThrottle`, scope `"auth"`) to blunt
  credential-stuffing/spam signups.
- A user's raw location/phone is **never** in a public API response. Public listing search only
  ever returns `distance_km` (approximate), and `PublicUserSerializer` omits phone/location
  entirely. Precise contact info is only surfaced to the other matched party on an `Exchange`, via
  `counterpart_contact`, once a request has been accepted.
- Listing photo uploads are validated server-side (content-type allowlist, size cap) in
  `apps/listings/services.py` before ever reaching FileForge — never trust frontend validation
  alone.
- `FILEFORGE_API_KEY` lives only in environment variables and inside
  `common/fileforge_client.py`'s request headers — it's never returned in any API response.
- `prod.py` turns on `SECURE_SSL_REDIRECT`, HSTS, secure cookies, and `X_FRAME_OPTIONS = "DENY"`.

---

## Deviations & assumptions

This section documents where the implementation diverges from the original prompt, and why —
flagged rather than silently dropped, per the prompt's own instructions.

1. **Postgres on PythonAnywhere's free tier.** PythonAnywhere's actual free tier only ships MySQL
   out of the box; Postgres (required here for PostGIS) has historically required a paid plan or a
   manually-provisioned external Postgres (e.g. ElephantSQL/Supabase's free tiers) reachable from
   PythonAnywhere. The prompt's deployment-target section specifies "free-tier PythonAnywhere" *and*
   "PostgreSQL with PostGIS" as hard requirements, which are in tension on the literal free tier.
   This implementation assumes an externally-hosted Postgres+PostGIS instance is used in production
   (reachable from PythonAnywhere via `DB_HOST`), which is the closest faithful resolution —
   flagging this explicitly rather than silently swapping to MySQL/sqlite and losing PostGIS geo
   search.
2. **Listing soft-delete.** `DELETE /api/v1/listings/{id}/` sets `status=removed` rather than
   hard-deleting the row, to preserve exchange/request history for audit purposes. The `Listing`
   model already had a `removed` status value in the required data model, which is the basis for
   this choice.
3. **404 vs 403 on scoped list endpoints.** `BookRequestViewSet`/`ExchangeViewSet` scope their
   `get_queryset()` to the requesting user's own requests/exchanges. A user who isn't a party to a
   given request/exchange gets a 404 (object doesn't exist *for them*) rather than a 403, to avoid
   leaking the existence of other users' requests/exchanges. A user who *is* a party but lacks
   permission for the specific action (e.g. the requester trying to `accept` their own request)
   correctly gets a 403. Both cases are covered by tests.
4. **`Report` dedup rule.** The prompt didn't specify exact dedup semantics for reports, so this
   implementation enforces "one **open** report per reporter per target" via a partial unique
   constraint — a resolved/dismissed report doesn't block a fresh report if the issue recurs later.
5. **FileForge reconciliation job.** Because `add_listing_photo()` only ever creates a
   `ListingPhoto` row after a successful synchronous FileForge upload, there's no long-lived
   "pending" state to sweep under normal operation. The daily reconciliation job instead checks for
   drift (a `ListingPhoto` whose backing FileForge file has since disappeared) rather than
   resolving stuck in-flight uploads, since the current design doesn't produce stuck uploads.
6. **`apps.requests` app label.** The `requests` app is given an explicit `app_label = "requests_app"`
   in its `AppConfig`, purely so `django-admin`/shell output isn't ambiguous against the `requests`
   HTTP library dependency; Python's absolute-import resolution means there's no actual import
   collision either way.

## Known limitations / follow-ups (not silently dropped)

Prioritized, most important first:

1. **Docker Compose is unverified in the sandbox this was built in** — Docker itself wasn't
   available in the build environment (no daemon, restricted network egress to Docker Hub), so
   while `Dockerfile`/`docker-compose.yml` are written to spec (GDAL/PostGIS base image,
   `web`+`db` only, `.env`-driven), they haven't been run end-to-end. **Everything else in this
   README *was* verified for real** — migrations, the full test suite, and a live smoke test all
   ran against an actual PostgreSQL 16 + PostGIS 3.4 instance and a real running dev server in the
   build sandbox (not mocked). Please run `docker-compose up` as a first step after cloning and
   file an issue if anything doesn't come up cleanly.
2. **CI workflow is written but not run against GitHub's actual runners** — same constraint as
   above (no outbound access to github.com Actions infra from the build sandbox). Confirm on the
   first real push.
3. **FileForge is mocked in every test** (`unittest.mock.patch` on `get_fileforge_client`) since no
   live FileForge instance was available to point at. The client wrapper
   (`common/fileforge_client.py`) itself is straightforward enough that this should translate
   cleanly, but a manual end-to-end photo upload against a real FileForge instance is worth doing
   before shipping.
4. **Avatar upload endpoint isn't wired up.** The `User` model has `avatar_file_id`/`avatar_url`
   fields and `FileForgeClient` supports the same upload/delete flow used for listing photos, but
   there's no `POST /api/v1/users/me/avatar/` endpoint yet — only listing photos are wired through
   to FileForge today. Small addition, same pattern as `apps/listings/services.py::add_listing_photo`.
5. **No rate limiting beyond `register`/`login`.** Other write-heavy endpoints (creating
   listings/requests/reports) have no throttle scope. Low priority for a low-volume nonprofit
   platform per the prompt's own framing, but worth adding if abuse becomes a problem.
6. **Django Admin is the only admin surface**, as the prompt explicitly allows for MVP — no
   dedicated moderation API endpoints beyond `POST /api/v1/reports/` (creation) exist; resolving
   reports is admin-only for now.
