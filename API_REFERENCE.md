# SalvageMe API Reference

A guide for frontend developers integrating with the SalvageMe backend. Covers every endpoint,
request/response shapes, auth flow, error handling, and common patterns (pagination, geo search,
file uploads).

This document is hand-written for readability. It is generated from, and should stay consistent
with, the machine-readable OpenAPI schema — see [Interactive docs & schema](#interactive-docs--schema)
below if you want to generate a typed client instead of reading this by hand.

---

## Table of contents

- [Base URL & versioning](#base-url--versioning)
- [Authentication](#authentication)
- [Error responses](#error-responses)
- [Pagination](#pagination)
- [Endpoints](#endpoints)
  - [Auth](#auth)
  - [Users](#users)
  - [Categories](#categories)
  - [Listings](#listings)
  - [Book requests](#book-requests)
  - [Exchanges](#exchanges)
  - [Drop-off points](#drop-off-points)
  - [Reports](#reports)
  - [Impact stats](#impact-stats)
  - [Health check](#health-check)
- [Enums reference](#enums-reference)
- [Common patterns](#common-patterns)
- [End-to-end example flow](#end-to-end-example-flow)
- [Interactive docs & schema](#interactive-docs--schema)

---

## Base URL & versioning

```
https://salvageme.pythonanywhere.com/api/v1/
```

Locally: `http://localhost:8000/api/v1/`

All endpoints in this document are relative to that base **except** the health check and the
schema/docs URLs, which live outside `/api/v1/` (see [Health check](#health-check) and
[Interactive docs & schema](#interactive-docs--schema)).

All request/response bodies are JSON unless otherwise noted (file uploads use `multipart/form-data`).

---

## Authentication

SalvageMe uses **JWT access tokens + an httpOnly refresh cookie** — not a single long-lived token
you store yourself.

- **Access token**: returned in the JSON response body on register/login/refresh. Short-lived
  (**15 minutes**). Send it on every authenticated request as:
  ```
  Authorization: Bearer <access_token>
  ```
  Keep it in memory (e.g. a store/context), **not** `localStorage`, to limit XSS exposure.
- **Refresh token**: never appears in any JSON response body. The backend sets it as an **httpOnly
  cookie** (`salvageme_refresh`, scoped to path `/api/v1/auth/`, `SameSite=Lax`, `Secure` outside
  local dev) on register/login, and rotates it on every `/auth/refresh/` call. You cannot read this
  cookie from JavaScript — that's intentional. Its lifetime is **14 days**.

**Every fetch/axios call must include credentials** (`credentials: "include"` in `fetch`, or
`withCredentials: true` in axios) or the refresh cookie will never be sent/received. Your dev
server origin must also be in the backend's `CORS_ALLOWED_ORIGINS` for this to work cross-origin.

### The refresh flow, concretely

1. On app load, call `POST /auth/refresh/` (no body needed — it reads the cookie). If it succeeds,
   you get a fresh access token and the user is still logged in from a previous session. If it
   401s, treat the user as logged out.
2. Keep the access token in memory. When an API call gets a `401`, call `POST /auth/refresh/` once
   to get a new access token, then retry the original call. If the refresh itself 401s, redirect to
   login — the refresh token has expired or was invalidated.
3. On logout, call `POST /auth/logout/`, which blacklists the refresh token server-side and clears
   the cookie. Discard your in-memory access token too.

`register`/`login` are rate-limited (throttle scope `"auth"`) — expect occasional `429 Too Many
Requests` under rapid retry loops (e.g. a buggy auto-retry), especially in production.

---

## Error responses

Every error response (validation, permission, not-found, throttling, upstream-service failure)
shares one shape:

```json
{
  "detail": "Human-readable message, or a validation error dict/list",
  "code": "machine_readable_code",
  "errors": { "field_name": ["Field-specific error message"] }
}
```

- `detail` — always present. Either a string, or (for field-validation errors) an object/array
  matching DRF's standard validation error format.
- `code` — always present. A short machine-readable string, e.g. `"self_request"`,
  `"duplicate_request"`, `"invalid_transition"`, `"service_unavailable"`. Branch on this rather
  than parsing `detail` text.
- `errors` — present only for field-level validation errors, keyed by field name.

Relevant status codes you'll see across the API: `400` (validation), `401` (missing/expired
auth), `403` (authenticated but not allowed to do this), `404` (not found, **or** an object that
exists but is outside your scope — see the note under [Book requests](#book-requests)), `429`
(throttled), `502` (an upstream dependency — currently only FileForge, the file-storage service —
failed; safe to retry).

---

## Pagination

List endpoints (`listings`, `requests`, `exchanges`) use **cursor pagination**, not page numbers:

```json
{
  "next": "http://.../api/v1/listings/?cursor=cD0yMDI2LTA3LTE2...",
  "previous": null,
  "results": [ /* ... */ ]
}
```

- Follow `next`/`previous` as opaque URLs — don't try to construct or parse the cursor yourself.
- Default page size is 20. Override with `?page_size=N` (capped at 100).
- `categories/` and `dropoff-points/` are **not** paginated — they return a plain array, since
  both are small, mostly-static reference lists.

---

## Endpoints

### Auth

All under `/auth/` (i.e. `/api/v1/auth/...`). None require an `Authorization` header (they're how
you get one) except where noted.

#### `POST /auth/register/`

Creates an account and logs you in immediately (same response shape as login).

Request:
```json
{
  "username": "priya_reads",
  "email": "priya@example.com",
  "password": "S3curePassword!",
  "role": "recipient",
  "phone": "+44 7123 456789"
}
```
Only `username` and `password` are required. `email`, `role` (defaults to `"both"` — see
[Enums reference](#enums-reference)), and `phone` are optional. Password is validated
server-side against Django's standard password validators (min length, not too common, not
entirely numeric, not too similar to your username/email).

Response `201`:
```json
{
  "access": "eyJhbGciOi...",
  "user": {
    "id": 42,
    "username": "priya_reads",
    "email": "priya@example.com",
    "role": "recipient",
    "phone": "+44 7123 456789",
    "is_verified": false,
    "avatar_url": null,
    "latitude": null,
    "longitude": null,
    "date_joined": "2026-07-16T10:00:00Z"
  }
}
```
(Refresh token is set as the `salvageme_refresh` cookie — not in this body.)

`400` on validation failure (e.g. weak password, duplicate username) — `errors` will have
per-field messages.

#### `POST /auth/login/`

Request:
```json
{ "username": "priya_reads", "password": "S3curePassword!" }
```

Response `200`: same shape as register's response (`access` + `user`), refresh cookie set the
same way. `401` on wrong credentials.

#### `POST /auth/refresh/`

No body. Reads the `salvageme_refresh` cookie.

Response `200`:
```json
{ "access": "eyJhbGciOi..." }
```
Also rotates and re-sets the refresh cookie. `401` if the cookie is missing, expired, or was
already blacklisted (e.g. by a prior logout).

#### `POST /auth/logout/`

No body needed (reads the cookie same as refresh). Works even without a valid `Authorization`
header — it only needs the refresh cookie. Blacklists the refresh token and clears the cookie.

Response: `204 No Content`.

---

### Users

#### `GET /users/me/` 🔒

Returns the authenticated user's **full** profile (unlike how other users appear to you — see
[Common patterns → Contact/location privacy](#contactlocation-privacy)).

Response `200`: same `user` object shape shown under register above.

#### `PATCH /users/me/` 🔒

Partial update. Any subset of these fields:

```json
{
  "email": "newemail@example.com",
  "role": "both",
  "phone": "+44 7000 000000",
  "latitude": 51.5072,
  "longitude": -0.1276
}
```

⚠️ **`latitude`/`longitude` are a special case.** They don't show up as writable in the raw schema
(they're `SerializerMethodField`s for reads), but the view has custom handling that accepts them
on `PATCH` and converts them into the user's stored location — send them together, as a pair, to
update location. Sending only one of the two has no effect.

Response `200`: the updated `user` object (same shape as `GET`).

---

### Categories

Read-only reference data — no auth required.

#### `GET /categories/`

Not paginated. Returns a plain array:
```json
[
  { "id": 1, "name": "Fiction", "slug": "fiction" },
  { "id": 2, "name": "Textbooks", "slug": "textbooks" }
]
```

#### `GET /categories/{id}/`

Single category, same shape as one array item above.

---

### Listings

The core resource — books/materials donors post for recipients to request.

#### `GET /listings/`

Public (no auth required, but behavior differs slightly if authenticated — see below).

**Query parameters** (all optional, combinable):

| Param | Example | Behavior |
|---|---|---|
| `category` | `?category=textbooks` | Filters by category **slug**, not id. |
| `condition` | `?condition=good` | One of the [Listing condition](#listing-condition) values. |
| `grade_level` | `?grade_level=9th-10th%20grade` | Exact match on the free-text grade level field. |
| `q` | `?q=algebra` | Case-insensitive substring search across title + description. |
| `near` | `?near=51.5072,-0.1276` | `lat,lng`. Requires the listing to have a location set; combine with `radius` (see below). Results are sorted by distance when this is present. |
| `radius` | `?radius=10` | Kilometers. Only applied when `near` is also present. Without `near`, it's ignored. |
| `page_size` | `?page_size=50` | Override the default page size of 20 (max 100). |

Response `200`: [paginated](#pagination) list of listing objects:
```json
{
  "next": "...",
  "previous": null,
  "results": [
    {
      "id": 7,
      "owner": {
        "id": 3,
        "username": "donor_amara",
        "role": "donor",
        "is_verified": true,
        "date_joined": "2026-06-01T09:00:00Z"
      },
      "title": "Introduction to Algebra",
      "description": "A good copy, ready for a new home.",
      "category": { "id": 2, "name": "Textbooks", "slug": "textbooks" },
      "grade_level": "9th-10th grade",
      "condition": "good",
      "status": "available",
      "images": [
        { "id": 5, "url": "https://cdn.example/files/42.jpg", "order": 0 }
      ],
      "distance_km": 3.42,
      "created_at": "2026-07-10T12:00:00Z",
      "updated_at": "2026-07-10T12:00:00Z"
    }
  ]
}
```
`distance_km` is only present (non-`null`) when `near=` was supplied. `owner` never includes
phone/location — see [Contact/location privacy](#contactlocation-privacy).

**Visibility rules** (handled server-side, nothing to implement on your end, just be aware of it):
non-`available` listings (`pending`/`claimed`/`removed`) are hidden from anonymous users and from
authenticated users who don't own them. If you're logged in, you'll see your own listings
regardless of status. Staff see everything.

#### `GET /listings/{id}/`

Same object shape as one item from the list above. `404` if it doesn't exist or you're not allowed
to see it (per the visibility rules above).

#### `POST /listings/` 🔒

Request:
```json
{
  "title": "Introduction to Algebra",
  "description": "Gently used, some highlighting in ch. 3.",
  "category": 2,
  "grade_level": "9th-10th grade",
  "condition": "good",
  "latitude": 51.5072,
  "longitude": -0.1276
}
```
Required: `title`, `description`, `category` (id, not slug), `condition`. Optional:
`grade_level`, `latitude`+`longitude`. `owner` is always the authenticated user — don't send it.
**`status` is not accepted here** — new listings always start as `"available"`; sending a
`status` field in the body is silently ignored.

Response `201`: the created listing, same shape as a list item.

#### `PATCH /listings/{id}/` 🔒

Owner only. Same fields as create, all optional. Also silently ignores any `status` field —
status changes only happen through the request-accept/exchange-completion flow, never a direct
edit. `403` if you're not the owner.

Response `200`: the updated listing.

#### `DELETE /listings/{id}/` 🔒

Owner only. **This is a soft delete** — it sets `status` to `"removed"` rather than deleting the
row, so exchange/request history referencing this listing stays intact. It will simply stop
appearing in public listing search. `204 No Content` on success, `403` if not the owner.

#### `POST /listings/{id}/photos/` 🔒

Owner only. `multipart/form-data` with a single field, `file`:

```
Content-Type: multipart/form-data
file: <binary>
```

Server-side validation (don't rely on frontend validation alone, but matching it client-side
gives a better UX than waiting for a 400): JPEG/PNG/WebP only, max 8MB.

Response `201`:
```json
{ "id": 5, "url": "https://cdn.example/files/42.jpg", "order": 0 }
```

`400` for a rejected file (bad type/too large) — `detail` explains which. `502` if the upstream
file-storage service is unavailable — safe to let the user retry. Photos are appended in upload
order; there's currently no reorder/delete-single-photo endpoint from the API (delete the whole
listing and recreate it, or ask backend to add one if you need it).

---

### Book requests

The "I'd like this listing" → accept/decline lifecycle. A `BookRequest` is scoped: you can only
ever see requests where you're either the requester or the listing's owner.

> ⚠️ **404 vs 403, read this before building error handling around these endpoints.** If the
> current user isn't a party to a given request at all (neither the requester nor the listing
> owner), every endpoint below returns `404` — not `403` — to avoid revealing that the request
> exists. If the user *is* a party but isn't allowed to perform the specific action (e.g. the
> requester trying to `accept` their own request, which only the listing owner can do), you get a
> `403`. Design your error UI to treat both as "you can't do this," but know the distinction if
> you're debugging an unexpected 404.

#### `POST /listings/{listing_id}/request/` 🔒

Request:
```json
{ "message": "I'd love this for my classroom library!" }
```
`message` is optional.

Response `201`:
```json
{
  "id": 15,
  "listing": 7,
  "listing_title": "Introduction to Algebra",
  "requester": { "id": 42, "username": "priya_reads", "role": "recipient", "is_verified": false, "date_joined": "..." },
  "status": "pending",
  "message": "I'd love this for my classroom library!",
  "created_at": "2026-07-16T10:05:00Z"
}
```

`400` cases worth branching on by `code`:
- `self_request` — you own this listing.
- `listing_unavailable` — the listing isn't `available` (already pending/claimed/removed).
- `duplicate_request` — you already have a pending request on this listing.

#### `GET /requests/` 🔒

[Paginated](#pagination). Returns every request where you're either the requester **or** the
listing owner (i.e. both your sent and received requests, combined — filter client-side by
comparing `requester.id` to the current user's id if you need to split them into tabs).

Response items match the shape shown under create, above.

#### `GET /requests/{id}/` 🔒

Single request, same shape. `404` per the scoping note above.

#### `POST /requests/{id}/accept/` 🔒

Listing owner only. Accepting:
- Sets this request's `status` to `"accepted"`.
- Auto-declines every other still-`pending` request on the same listing.
- Sets the listing's `status` to `"pending"` (not yet `"claimed"` — that happens when the
  resulting exchange is completed, see below).
- Creates an `Exchange` linking the listing, the owner (as `donor`), and the requester (as
  `recipient`) — you'll want to redirect the user to that exchange (see next section) so they can
  schedule the handoff. The accept response doesn't include the new exchange's id directly; call
  `GET /exchanges/` and find the one for this `listing` if you need it immediately, or just
  navigate the user to their exchanges list.

Response `200`: the updated request (`status: "accepted"`). `403` if you're not the listing
owner. `400`/`code: "invalid_transition"` if the request isn't `pending` anymore (already
accepted/declined/cancelled).

#### `POST /requests/{id}/decline/` 🔒

Listing owner only. Sets `status` to `"declined"`; the listing stays/reverts to `available`
(available for other requesters).

Response `200`: the updated request. Same `403`/`400` cases as accept.

---

### Exchanges

The handoff-coordination lifecycle, created automatically when a request is accepted. Also
scoped: only visible to the exchange's `donor` and `recipient`, same 404-vs-403 rule as book
requests applies here too.

#### `GET /exchanges/` 🔒

[Paginated](#pagination). Every exchange where you're the donor or the recipient.

Response item shape:
```json
{
  "id": 9,
  "listing": 7,
  "listing_title": "Introduction to Algebra",
  "donor": { "id": 3, "username": "donor_amara", "role": "donor", "is_verified": true, "date_joined": "..." },
  "recipient": { "id": 42, "username": "priya_reads", "role": "recipient", "is_verified": false, "date_joined": "..." },
  "dropoff_point": null,
  "status": "scheduled",
  "scheduled_at": null,
  "completed_at": null,
  "counterpart_contact": {
    "username": "donor_amara",
    "phone": "+44 7123 456789",
    "latitude": 51.5072,
    "longitude": -0.1276
  }
}
```

`counterpart_contact` is the important one — see
[Contact/location privacy](#contactlocation-privacy) below. It's the *other* party's real phone +
coordinates, only present because you're a party to this specific exchange.

#### `GET /exchanges/{id}/` 🔒

Single exchange, same shape.

#### `POST /exchanges/{id}/schedule/` 🔒

Either party. Request:
```json
{ "scheduled_at": "2026-07-20T15:00:00Z", "dropoff_point": 2 }
```
`scheduled_at` (ISO 8601) required, `dropoff_point` (id, optional — omit for an ad-hoc
arrangement between the two parties). Can be called again to reschedule as long as the exchange
is still `scheduled` (i.e. not yet completed/cancelled).

Response `200`: updated exchange. `400`/`invalid_transition` if the exchange is already
completed/cancelled.

#### `POST /exchanges/{id}/complete/` 🔒

Either party. No body. Marks the exchange `"completed"`, stamps `completed_at`, and — this is the
point where it actually happens — sets the **listing's** `status` to `"claimed"`.

Response `200`: updated exchange. `400`/`invalid_transition` if not currently `scheduled`.

#### `POST /exchanges/{id}/cancel/` 🔒

Either party. No body. Marks `"cancelled"` and reverts the listing back to `"available"` so it
can be requested again.

Response `200`: updated exchange. `400`/`invalid_transition` if not currently `scheduled`.

#### `POST /exchanges/{id}/rate/` 🔒

Either party, **only after** the exchange is `completed`. Request:
```json
{ "score": 5, "comment": "Great communication, smooth handoff!" }
```
`score` required (1–5), `comment` optional.

Response `201`:
```json
{ "id": 3, "rated_user": 3, "rated_by": 42, "exchange": 9, "score": 5, "comment": "Great communication, smooth handoff!", "created_at": "..." }
```
`rated_user` is always the *other* party (computed server-side — you don't send it). `400` cases:
`exchange_not_completed` (too early), `duplicate_rating` (you already rated this exchange — one
rating per person per exchange, not editable via this endpoint).

---

### Drop-off points

Public reference data for the scheduling picker.

#### `GET /dropoff-points/`

Not paginated. Plain array:
```json
[
  {
    "id": 2,
    "name": "Riverside Community Center",
    "address": "12 Riverside Walk, London",
    "latitude": 51.5072,
    "longitude": -0.1276
  }
]
```

#### `GET /dropoff-points/{id}/`

Single point, same shape.

---

### Reports

Flagging a listing or user for moderation. Creation only — there's no API endpoint to view your
own past reports or their resolution status (resolution happens in Django Admin, moderator-side).

#### `POST /reports/` 🔒

Request:
```json
{
  "target_type": "listing",
  "target_id": 7,
  "reason": "misrepresented",
  "detail": "Listed as 'good' condition but pages are torn out."
}
```
`target_type` — `"listing"` or `"user"`. `target_id` — the id of that listing/user. `reason` —
see [Report reason](#report-reason). `detail` optional free text.

Response `201`:
```json
{ "id": 11, "target_type": "listing", "target_id": 7, "reason": "misrepresented", "detail": "...", "status": "open", "created_at": "..." }
```

`400`/`code: "duplicate_report"` if you already have an **open** report against this exact
target — resolved/dismissed ones don't block a fresh report if the issue recurs.

---

### Impact stats

Public, cached aggregate numbers — e.g. for a homepage "our impact so far" section.

#### `GET /stats/impact/`

No auth, no params.

Response `200`:
```json
{
  "total_listings": 142,
  "total_exchanges_completed": 58,
  "total_active_donors": 23,
  "total_active_recipients": 31,
  "computed_at": "2026-07-16T02:00:00Z"
}
```
This is a snapshot recomputed once daily (see the backend's `run_daily_jobs` scheduled task), not
live — `computed_at` tells you how fresh it is. Fine to poll occasionally; no need to refetch on
every render.

---

### Health check

#### `GET /api/health/`

⚠️ **Not under `/api/v1/`** — it's at the API root, `/api/health/`, not
`/api/v1/health/`. No auth. Useful for an uptime check or a "is the backend reachable" banner.

Response `200`:
```json
{ "status": "ok", "database": true }
```
`503` with `{"status": "degraded", "database": false}` if the database is unreachable.

---

## Enums reference

#### User role
| Value | Meaning |
|---|---|
| `donor` | Primarily lists items for others. |
| `recipient` | Primarily requests items from others. |
| `both` | Does both — the default if not specified at registration. |

#### Listing condition
| Value | Meaning |
|---|---|
| `new` | Unused / like-new. |
| `good` | Light wear, fully usable. |
| `fair` | Noticeable wear, still usable. |
| `worn` | Heavy wear. |

#### Listing status
| Value | Meaning |
|---|---|
| `available` | Visible in public search, can be requested. |
| `pending` | A request on it has been accepted; an exchange is in progress. |
| `claimed` | The exchange completed — no longer available. |
| `removed` | Soft-deleted by the owner. Hidden from search. |

#### Book request status
| Value | Meaning |
|---|---|
| `pending` | Awaiting the listing owner's decision. |
| `accepted` | Owner accepted — an exchange now exists for it. |
| `declined` | Owner declined, or it was auto-declined when a different request on the same listing was accepted. |
| `cancelled` | Expired automatically after 14 days still pending (see the backend's daily job) — not currently cancellable by the requester via the API. |

#### Exchange status
| Value | Meaning |
|---|---|
| `scheduled` | Default state after creation; can still be rescheduled. |
| `completed` | Handoff happened; listing is now `claimed`; ratings can now be submitted. |
| `cancelled` | Either party backed out; listing reverts to `available`. |
| `no_show` | Reserved for future use — not currently settable via any API endpoint. |

#### Report target type
`listing` \| `user`

#### Report reason
`spam` \| `inappropriate` \| `misrepresented` \| `no_show` \| `other`

#### Report status
`open` \| `resolved` \| `dismissed` — the latter two are only ever set by a moderator in Django
Admin, never via the public API.

---

## Common patterns

### Contact/location privacy

This is enforced server-side, but worth understanding so your UI doesn't try to display data
that's never there:

- **`PublicUserSerializer`** (the shape you get for `owner`, `requester`, `donor`, `recipient`
  anywhere in the API) never includes phone or location — just `id`, `username`, `role`,
  `is_verified`, `date_joined`. Don't build a "contact the owner" button off listing data alone.
- The **only** place raw contact info (phone + lat/lng) ever appears for someone *other than
  yourself* is `counterpart_contact` on an `Exchange` object you're a party to — i.e. only once a
  request has been accepted and the two of you actually need to coordinate a handoff.
- `GET /users/me/` is the only place you see your *own* full contact info.
- Public listing search never returns raw coordinates — only `distance_km` (and only when you
  passed `near=`).

### Geo search

`near=lat,lng` + optional `radius=km` on `GET /listings/`. Sort order automatically switches to
distance-ascending when `near` is present. If a listing has no location set, it's simply excluded
from `near=` results (not returned with `distance_km: null`).

### Status transitions are server-controlled

You'll notice `status` fields (on listings, requests, exchanges) are never directly settable via
`PATCH`/`POST` body — they only change as a side effect of the relevant action endpoint (accept,
decline, complete, cancel, delete). Don't build a generic "edit status" dropdown; use the specific
action buttons/endpoints instead.

### Idempotency / re-calling action endpoints

All the `accept`/`decline`/`complete`/`cancel`/`schedule`(reschedule)/`rate` action endpoints
reject being called twice with a `400`/`code: "invalid_transition"` (except `schedule`, which is
intentionally re-callable to reschedule, and `rate`, which is one-per-person but each party can
still rate independently). Show a friendly "this was already handled" message rather than a raw
error for that code — it usually means two tabs/devices raced, not a real problem.

---

## End-to-end example flow

A minimal "donor lists a book, recipient gets it" walkthrough, showing which endpoint follows
which:

```
1. POST /auth/register/           (role: "donor")           → donor's access token
2. POST /listings/                                            → listing id 7, status: available
3. POST /listings/7/photos/       (multipart)                 → photo attached

4. POST /auth/register/           (role: "recipient")        → recipient's access token
5. GET  /listings/?near=51.5,-0.1&radius=10                   → finds listing 7
6. POST /listings/7/request/                                  → request id 15, status: pending

   (back to donor)
7. GET  /requests/                                             → sees request 15
8. POST /requests/15/accept/                                   → request → accepted,
                                                                   listing 7 → pending,
                                                                   an Exchange is created

   (either party)
9. GET  /exchanges/                                             → finds the new exchange, id 9
10. POST /exchanges/9/schedule/    {"scheduled_at": "..."}      → status stays scheduled,
                                                                    scheduled_at set
11. POST /exchanges/9/complete/                                 → exchange → completed,
                                                                    listing 7 → claimed
12. POST /exchanges/9/rate/        {"score": 5}                 → either party can now rate
```

---

## Interactive docs & schema

The backend also serves a machine-readable OpenAPI 3 schema, kept in sync with the code via
`drf-spectacular` (CI regenerates and validates it on every push):

- **Swagger UI** (try requests in-browser): `/api/docs/`
- **Redoc** (clean read-only reference): `/api/redoc/`
- **Raw schema** (for generating a typed client): `/api/schema/`

If your frontend stack supports it, generating a typed client from `/api/schema/` (e.g.
`openapi-typescript`, `orval`) will save you from hand-typing the request/response shapes above
and will stay accurate as the API evolves — this document is meant to be the readable companion
to that, not a replacement for it.
