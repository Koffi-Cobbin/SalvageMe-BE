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
  - [Notifications](#notifications)
  - [Partner applications](#partner-applications)
  - [Leaderboard](#leaderboard)
  - [Impact stats](#impact-stats)
  - [Health check](#health-check)
- [Admin API](#admin-api)
  - [Roles & capabilities](#roles--capabilities)
  - [Admin: Users](#admin-users)
  - [Admin: Listings](#admin-listings)
  - [Admin: Categories](#admin-categories)
  - [Admin: Reports](#admin-reports)
  - [Admin: Audit log](#admin-audit-log)
  - [Admin: Exchanges](#admin-exchanges)
  - [Admin: Requests](#admin-requests)
  - [Admin: Ratings](#admin-ratings)
  - [Admin: Drop-off points](#admin-drop-off-points)
  - [Admin: Dashboard & stats](#admin-dashboard--stats)
  - [Admin: Leaderboard](#admin-leaderboard)
  - [Admin: Partner applications](#admin-partner-applications)
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

#### `POST /auth/set-password/`

Public — the token itself is the auth, no `Authorization` header needed. Used for two cases: an
account created with no password (e.g. via the [partner application flow](#partner-applications))
setting one for the first time, and (in the future) a general "forgot password" flow reusing this
same endpoint.

Request:
```json
{ "uid": "MTIz", "token": "abc123-some-signed-token", "new_password": "NewSecurePassword!" }
```
`uid` and `token` come from the link in the invite/reset email — the frontend doesn't construct
these itself, just reads them out of the URL the email links to and passes them through unchanged.

Response: `204 No Content` on success. Also sets the account's `is_verified` to `true`. `400`/
`code: "invalid_token"` if the link is malformed, expired, or already used.

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
  "include_in_leaderboard": true,
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

Flagging a listing or user for moderation. Creation only from this public API — there's no
endpoint here to view your own past reports or their resolution status directly, but **you do get
a [notification](#notifications) once staff resolve or dismiss it**. Resolution itself happens via
the [Admin API](#admin-reports) or Django Admin, moderator-side.

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

### Notifications

In-app notifications — every event that used to only send an email (a request being accepted, an
exchange reminder, a report being resolved, and so on) now also creates a row here, so you can
build a notification bell/inbox instead of relying on email alone. Always scoped to the
authenticated user — you never see another user's notifications.

#### `GET /notifications/` 🔒

[Paginated](#pagination). Query params: `?is_read=false` (or `true`), `?category=exchange_reminder`
(see [Notification category](#notification-category) for the full list).

Response `200`:
```json
{
  "next": null, "previous": null,
  "results": [
    {
      "id": 12,
      "category": "request_accepted",
      "title": "Your request for 'Intro to Algebra' was accepted",
      "body": "Great news — your request was accepted. Coordinate the handoff via exchange #9.",
      "target_type": "exchange",
      "target_id": 9,
      "is_read": false,
      "read_at": null,
      "created_at": "2026-07-19T10:05:00Z"
    }
  ]
}
```
`target_type`/`target_id` let you build one generic "click a notification, navigate to its target"
handler — `target_type` values you'll see: `"request"`, `"exchange"`, `"report"`, `"user"`,
`"partner_application"`.

#### `GET /notifications/{id}/` 🔒

Single notification, same shape. `404` if it isn't yours.

#### `GET /notifications/unread-count/` 🔒

For a bell-icon badge:
```json
{ "count": 4 }
```
No push/websocket delivery — poll this (e.g. on route change, or a short interval) rather than
expecting it to update in real time.

#### `POST /notifications/{id}/read/` 🔒

No body. Marks it read.

Response `200`: the updated notification (`is_read: true`, `read_at` set).

#### `POST /notifications/mark-all-read/` 🔒

No body. Marks every one of your unread notifications as read in one call — the "clear the badge"
action.

Response `200`:
```json
{ "marked_read": 4 }
```

#### `DELETE /notifications/{id}/` 🔒

Dismiss/remove one of your own notifications. `204 No Content`. `404` if it isn't yours.

---

### Partner applications

Public form for someone to apply to become a Partner and/or offer their location as a drop-off
point. Staff review these via the [Admin API](#admin-partner-applications).

#### `POST /partner-applications/` 🔓 (public — auth optional)

Request:
```json
{
  "applicant_name": "Amara Okafor",
  "applicant_email": "amara@riversidecc.example",
  "applicant_phone": "+44 7123 456789",
  "organization_name": "Riverside Community Center",
  "message": "We'd like to help distribute books to local families.",
  "proposed_dropoff_name": "Riverside Community Center",
  "proposed_dropoff_address": "12 Riverside Walk, London",
  "proposed_latitude": 51.5072,
  "proposed_longitude": -0.1276
}
```
Everything is optional **if you're authenticated** — your own account's name/email/phone are used
automatically and anything you send for those three fields is ignored (the server never trusts a
logged-in request to claim a different identity than the account making it). **If you're not
authenticated, `applicant_name` and `applicant_email` are required.** Omit the `proposed_*` fields
entirely if you're only applying for a role, not offering a physical location.

**What happens next, so you can set expectations in your UI:**
- If you're logged in, your application is immediately ready for review — nothing further needed
  from you.
- If you're not logged in: a new account is created for you right away with the email you
  provided (or your existing account is used, if that email already has one) — **this account is
  fully usable immediately, regardless of whether the application is later approved or rejected**.
  You'll get an email with a link to verify your address and set a password. Your application only
  becomes visible to reviewers once you complete that step.

Response `201`:
```json
{
  "id": 4,
  "applicant_name": "Amara Okafor",
  "applicant_email": "amara@riversidecc.example",
  "applicant_phone": "+44 7123 456789",
  "organization_name": "Riverside Community Center",
  "message": "We'd like to help distribute books to local families.",
  "proposed_dropoff_name": "Riverside Community Center",
  "proposed_dropoff_address": "12 Riverside Walk, London",
  "email_verified_at": null,
  "status": "pending",
  "rejection_reason": "",
  "created_at": "2026-07-19T10:00:00Z"
}
```

`400`/`code: "duplicate_application"` if this email already has a **pending** application —
a rejected one doesn't block reapplying.

---

### Leaderboard

Public recognition for top donors, ranked by completed donations. Computed live on every request
(not cached) — always reflects current data.

#### `GET /leaderboard/` 🔓 (public)

Query params: `?period=all_time` (default) or `?period=this_month`. `?limit=20` (default, capped
at 100 — this is a "top N" endpoint, not a full paginated list).

Response `200`:
```json
{
  "period": "all_time",
  "results": [
    {
      "rank": 1,
      "username": "donor_amara",
      "avatar_url": "https://cdn.example/avatars/3.jpg",
      "completed_donation_count": 47,
      "average_rating": 4.9,
      "hero_tier": "Legend"
    }
  ]
}
```
`average_rating` reflects ratings received **specifically as a donor** (not mixed with any ratings
received as a recipient on other exchanges) — `null` if they haven't been rated yet.
`hero_tier` — see [Hero tier](#hero-tier) — `null` if below the first threshold (shouldn't
normally appear in a top-N list, but possible with a small `?limit=`). `400`/`code: "invalid_period"`
for anything other than the two supported values. Never exposes phone/email/location — same
`PublicUserSerializer`-style boundary as everywhere else in this API (see
[Contact/location privacy](#contactlocation-privacy)) — just `username`/`avatar_url` plus derived
counts.

#### `GET /leaderboard/me/` 🔒

Your own rank, even when you're outside the top N of `GET /leaderboard/`.

Response `200`:
```json
{ "rank": 47, "username": "donor_felix", "completed_donation_count": 3, "average_rating": 5.0, "hero_tier": "Contributor" }
```
`rank: null` if you have zero completed donations yet (not "last place" — show a "make your first
donation to join the leaderboard" prompt instead of a number in that case).

**Opting out:** anyone can exclude themselves from the public leaderboard via
`PATCH /users/me/` with `{"include_in_leaderboard": false}` (default `true` — see
[`GET /users/me/`](#get-usersme)). Staff can also do this on someone else's behalf via
[`PATCH /admin/users/{id}/`](#patch-adminusersid-usersedit), gated by the existing `users.edit`
capability — no separate leaderboard-specific admin capability exists for this.

#### `GET /leaderboard/featured/` 🔓 (public)

An editorial "Donor of the Month"-style spotlight — a human pick by staff, distinct from the
algorithmic ranking above. Returns every **currently-active** entry (there can be more than one at
once — e.g. nothing stops staff running two simultaneous spotlights).

Response `200`:
```json
[
  {
    "id": 3,
    "username": "donor_amara",
    "avatar_url": "https://cdn.example/avatars/3.jpg",
    "blurb": "Amara has donated over 50 books to local schools this year!",
    "featured_from": "2026-07-01T00:00:00Z",
    "featured_until": "2026-07-31T23:59:59Z"
  }
]
```
`featured_until: null` means indefinite — no end date set. Empty array `[]` if nobody is currently
featured. Managed via the [Admin API](#admin-leaderboard) below.

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

## Admin API

A separate surface, all under `/api/v1/admin/`, for building a custom admin/moderation panel.
**Access isn't a simple "is staff" boolean** — it's built on named, admin-creatable **roles**, each
holding a set of fine-grained **capabilities**. A role can be created, renamed, or have its
capabilities changed at any time by whoever holds the `roles.manage` capability, with no code
deploy required. Every endpoint below lists the exact capability it requires.

### Roles & capabilities

#### `GET /admin/me/` 🔒 (any authenticated user — no capability required)

Call this once after login to decide whether to show admin navigation **at all**. A normal user
gets `can_access_admin: false` and an empty capability list — hide the entire admin section of
your UI on that response rather than letting individual admin calls 403 one at a time.

Response `200`:
```json
{
  "admin_role": { "id": 3, "name": "Content Moderator" },
  "capabilities": ["listings.remove_restore", "reports.resolve", "reports.view", "listings.view"],
  "can_access_admin": true
}
```
For a normal user: `{ "admin_role": null, "capabilities": [], "can_access_admin": false }`. Use
the `capabilities` array to show/hide individual admin sections/buttons too — e.g. hide the
"Categories" nav item if `categories.manage` isn't in the list.

#### `GET /admin/capabilities/` 🔒`roles.manage`

The full fixed vocabulary of capabilities — for building the checkbox list in a role-editor UI.

Response `200`:
```json
[
  { "code": "users.view", "description": "View user profiles and account status" },
  { "code": "users.suspend", "description": "Suspend / reactivate user accounts" }
]
```
See [Capabilities](#capabilities) for the complete list.

#### `GET /admin/roles/` 🔒`roles.manage`

Not paginated (there are typically only a handful of roles). Plain array:
```json
[
  { "id": 1, "name": "Admin", "description": "Full access to every admin capability. Built-in and protected.", "capabilities": ["users.view", "..."], "is_protected": true, "created_at": "...", "updated_at": "..." },
  { "id": 3, "name": "Content Moderator", "description": "Handles listing/report moderation.", "capabilities": ["listings.remove_restore", "reports.resolve"], "is_protected": false, "created_at": "...", "updated_at": "..." }
]
```
`is_protected: true` marks the single built-in role seeded when the system was set up — see notes
on `PATCH`/`DELETE` below for what that restricts.

#### `GET /admin/roles/{id}/` 🔒`roles.manage`

Single role, same shape.

#### `POST /admin/roles/` 🔒`roles.manage`

Request:
```json
{ "name": "Content Moderator", "description": "Handles listing/report moderation.", "capabilities": ["listings.remove_restore", "reports.resolve", "reports.view", "listings.view"] }
```
`name` required. `capabilities` — array of capability codes; unknown codes are rejected. `400`/
`code: "unknown_capability"` for a bad code, `400`/`code: "duplicate_name"` for a repeated name.

Response `201`: the created role.

#### `PATCH /admin/roles/{id}/` 🔒`roles.manage`

Any subset of `name`, `description`, `capabilities`. **The protected built-in role's
`capabilities` cannot be changed** (`400`/`code: "role_protected"`) — its `name`/`description`
can still be edited for cosmetic reasons. This guarantees at least one role always has every
capability, so the system can never be edited into a state where nobody can manage roles.

Response `200`: the updated role.

#### `DELETE /admin/roles/{id}/` 🔒`roles.manage`

`400`/`code: "role_protected"` for the built-in role. `400`/`code: "role_in_use"` if any user
currently holds this role — reassign or clear their role first via
[`assign-role`](#post-adminusersidassign-role-rolesmanage). `204 No Content` on success.

#### `POST /admin/users/{id}/assign-role/` 🔒`roles.manage`

Documented under [Admin: Users](#admin-users) below, listed here too since it's the other half of
role management.

---

### Admin: Users

#### `GET /admin/users/` 🔒`users.view`

[Paginated](#pagination). Filter: `?role=donor`, `?is_verified=true`, `?is_active=false`.

Response item shape:
```json
{
  "id": 42, "username": "priya_reads", "email": "priya@example.com", "phone": "+44 7123 456789",
  "role": "recipient", "is_verified": false, "is_active": true,
  "admin_role": { "id": 3, "name": "Content Moderator" },
  "date_joined": "2026-06-01T09:00:00Z"
}
```
`admin_role` is `null` for a normal user — this is the **full** profile (unlike `PublicUserSerializer`
elsewhere in this API), since this is a staff-only view.

#### `GET /admin/users/{id}/` 🔒`users.view`

Single user, same shape.

#### `PATCH /admin/users/{id}/` 🔒`users.edit`

Any subset of `role`, `phone`, `is_verified`, `include_in_leaderboard` (see
[Leaderboard](#leaderboard)). **Does not include `admin_role`** — that's
exclusively via `assign-role` below, gated by the separate `roles.manage` capability, so a role
with `users.edit` but not `roles.manage` can't grant admin access through the back door via a
generic field edit.

Response `200`: the updated user.

#### `POST /admin/users/{id}/suspend/` 🔒`users.suspend`

No body. Sets the account inactive (they'll be unable to log in). `400`/`code: "already_suspended"`
if already inactive.

Response `200`: the updated user.

#### `POST /admin/users/{id}/reactivate/` 🔒`users.suspend`

No body. `400`/`code: "already_active"` if already active. Same capability as `suspend` — they're
the inverse of one power, not two separate ones.

#### `POST /admin/users/{id}/assign-role/` 🔒`roles.manage`

Request:
```json
{ "admin_role_id": 3 }
```
`admin_role_id: null` revokes admin access entirely, back to a normal user. `404` if the role id
doesn't exist.

Response `200`: the updated user (with the new `admin_role`).

⚠️ **Safeguard:** rejected with `400`/`code: "last_role_manager"` if this specific change would
leave **zero users** able to manage roles at all — you can't lock everyone (including yourself)
out of the role system this way.

---

### Admin: Listings

#### `GET /admin/listings/` 🔒`listings.view`

[Paginated](#pagination). Filter: `?category=`, `?condition=`, `?status=`. **Unlike the public
`/listings/` endpoint, returns every status including `removed`** — staff need to see removed
listings to review/undo a removal.

Response items match the [public listing shape](#listings).

#### `GET /admin/listings/{id}/` 🔒`listings.view`

Single listing, any status.

#### `POST /admin/listings/{id}/remove/` 🔒`listings.remove_restore`

No body. Sets `status: "removed"`.

#### `POST /admin/listings/{id}/restore/` 🔒`listings.remove_restore`

No body. Sets `status: "available"`. `400`/`code: "invalid_transition"` if the listing is
currently `pending`/`claimed` — only `removed → available` is a meaningful restore.

#### `DELETE /admin/listings/{id}/photos/{photo_id}/` 🔒`listings.delete_photo`

Removes a single photo without touching the rest of the listing. `204 No Content`. `404`/
`code: "not_found"` if that photo doesn't belong to this listing. `502` if the upstream
file-storage service fails — safe to retry.

---

### Admin: Categories

Full CRUD — unlike the [public `/categories/`](#categories) endpoint, which is read-only.

#### `GET /admin/categories/`, `POST /admin/categories/`, `PATCH /admin/categories/{id}/`, `DELETE /admin/categories/{id}/` 🔒`categories.manage`

Not paginated. Same shape as the public endpoint (`id`, `name`, `slug`) — `slug` auto-generated
from `name` if omitted on create. `DELETE` returns `400`/`code: "category_in_use"` (not a raw 500)
if any listing still references it — remove/recategorize those listings first.

---

### Admin: Reports

#### `GET /admin/reports/` 🔒`reports.view`

[Paginated](#pagination). Filter: `?status=`, `?reason=`, `?target_type=`. Every report, not
scoped to who filed it.

Response items match the [public report shape](#reports), plus `status`.

#### `GET /admin/reports/{id}/` 🔒`reports.view`

Single report, same shape.

#### `POST /admin/reports/{id}/resolve/` 🔒`reports.resolve`

No body. Sets `status: "resolved"` and **notifies the reporter** (see [Notifications](#notifications)).

#### `POST /admin/reports/{id}/dismiss/` 🔒`reports.resolve`

No body. Sets `status: "dismissed"`, same reporter notification. Resolve and dismiss share one
capability — both are "you've handled this report," not two separate powers.

---

### Admin: Audit log

Read-only trail of every admin action — role/capability changes, suspensions, removals, report
resolutions, force-overrides, and so on.

#### `GET /admin/audit-log/` 🔒`auditlog.view`

[Paginated](#pagination). Filter: `?action=`, `?target_type=`. Ordered newest-first.

Response item shape:
```json
{
  "id": 88, "actor": 3, "actor_username": "staffuser", "action": "listing_removed",
  "target_type": "listing", "target_id": 7, "metadata": {}, "created_at": "2026-07-19T10:00:00Z"
}
```

#### `GET /admin/audit-log/{id}/` 🔒`auditlog.view`

Single entry, including the full `metadata` payload (shape varies by `action` — e.g. a
`user_role_assigned` entry's metadata has `old_role_id`/`new_role_id`).

---

### Admin: Exchanges

#### `GET /admin/exchanges/` 🔒`exchanges.view`

[Paginated](#pagination). Filter: `?status=`. **Every** exchange, unlike the public
[`/exchanges/`](#exchanges) endpoint (which is scoped to the current user).

#### `GET /admin/exchanges/{id}/` 🔒`exchanges.view`

Single exchange, same shape as the public endpoint (including `counterpart_contact`, computed the
same way — see [Contact/location privacy](#contactlocation-privacy)).

#### `POST /admin/exchanges/{id}/force-cancel/` 🔒`exchanges.force_override`

For a stuck/abandoned exchange neither party is acting on — bypasses the normal donor/recipient-only
restriction. Request:
```json
{ "reason": "Both parties unresponsive for 3 weeks; listing needs to be freed up." }
```
`reason` is **required** — every force-override is recorded in the [audit log](#admin-audit-log)
with it. `400`/`code: "invalid_transition"` if the exchange isn't currently `scheduled`.

#### `POST /admin/exchanges/{id}/force-complete/` 🔒`exchanges.force_override`

Same shape and `reason` requirement as `force-cancel`, for a handoff confirmed to have happened
outside the app but never marked complete by either party.

---

### Admin: Requests

Read-only support visibility — there's no admin power to accept/decline on someone's behalf, since
that's inherently the listing owner's call.

#### `GET /admin/requests/` 🔒`requests.view`

[Paginated](#pagination). Filter: `?status=`. Every request, not scoped to the current user.

#### `GET /admin/requests/{id}/` 🔒`requests.view`

Single request.

---

### Admin: Ratings

Read-only, for trust & safety review.

#### `GET /admin/ratings/` 🔒`ratings.view`

[Paginated](#pagination). Filter: `?score=`.

#### `GET /admin/ratings/{id}/` 🔒`ratings.view`

Single rating.

---

### Admin: Drop-off points

Full CRUD — unlike the [public `/dropoff-points/`](#drop-off-points) endpoint (read-only). **This
is genuinely scoped**: a user with `dropoff.manage` only sees/edits drop-off points they're
assigned to as a manager; `dropoff.manage_all` sees/edits every point.

#### `GET /admin/dropoff-points/` 🔒`dropoff.view`, `dropoff.manage`, or `dropoff.manage_all`

Not paginated. Response items:
```json
{
  "id": 2, "name": "Riverside Community Center", "address": "12 Riverside Walk, London",
  "latitude": 51.5072, "longitude": -0.1276, "coordinator": 5,
  "managers": [{ "id": 42, "username": "amara" }]
}
```
Scoped to your assigned points unless you hold `dropoff.manage_all`.

#### `GET /admin/dropoff-points/{id}/` 🔒 same as above

Single point. `404` (not `403`) if it's outside your scope and you don't hold `dropoff.manage_all`.

#### `POST /admin/dropoff-points/` 🔒`dropoff.manage_all` **only**

```json
{ "name": "New Point", "address": "1 Main St", "latitude": 51.5, "longitude": -0.1, "coordinator": 5 }
```
Deliberately not available to plain `dropoff.manage` — a brand-new point has no managers yet, so
there's nothing to scope creation to.

#### `PATCH /admin/dropoff-points/{id}/` 🔒`dropoff.manage` (your own points) or `dropoff.manage_all` (any)

Same fields as create, any subset. `404` if outside your scope.

#### `DELETE /admin/dropoff-points/{id}/` 🔒 same as `PATCH`

`204 No Content`. Always safe — exchanges referencing this point just lose their `dropoff_point`
reference rather than being blocked.

#### `POST /admin/dropoff-points/{id}/assign-managers/` 🔒`dropoff.manage_all` **only**

Request:
```json
{ "user_ids": [42, 57] }
```
**Replaces** the full manager list for this point (not additive — resend the complete set each
time). Deliberately gated to `dropoff.manage_all`, not plain `dropoff.manage` — a scoped manager
can run their own location but can't grant other people access to it.

Response `200`: the updated point, with its new `managers` list.

---

### Admin: Dashboard & stats

#### `GET /admin/dashboard/` 🔒`dashboard.view`

A small set of counts for an admin landing page, computed fresh on every call (not cached).

Response `200`:
```json
{
  "open_reports_count": 3,
  "pending_requests_count": 12,
  "unverified_users_count": 45,
  "listings_created_today": 7,
  "scheduled_exchanges_count": 9
}
```

#### `GET /admin/stats/history/` 🔒`dashboard.view`

[Paginated](#pagination). List of [impact-stats](#impact-stats) snapshots over time (for a trend
chart) — the same object shape as `GET /stats/impact/`, just historical.

#### `POST /admin/stats/recompute/` 🔒`stats.recompute`

No body. Manually triggers a fresh snapshot rather than waiting for the next scheduled run — a
"refresh now" button. Separate capability from `dashboard.view` since this one writes.

Response `200`: the new snapshot, same shape as [`GET /stats/impact/`](#impact-stats).

---

### Admin: Leaderboard

Manages the editorial spotlight — see [`GET /leaderboard/featured/`](#get-leaderboardfeatured--public)
for the public-facing result.

#### `GET /admin/leaderboard/featured/` 🔒`leaderboard.manage`

[Paginated](#pagination). Lists **every** entry — past, currently-active, and scheduled for the
future — not just active ones, since staff need visibility into upcoming/expired spotlights too.

Response item shape:
```json
{
  "id": 3, "user": 42, "username": "donor_amara", "blurb": "Amazing contributor!",
  "featured_from": "2026-07-01T00:00:00Z", "featured_until": "2026-07-31T23:59:59Z",
  "created_by": 7, "created_at": "2026-06-28T09:00:00Z"
}
```

#### `POST /admin/leaderboard/featured/` 🔒`leaderboard.manage`

Request:
```json
{
  "user_id": 42,
  "blurb": "Amara has donated over 50 books to local schools this year!",
  "featured_from": "2026-07-01T00:00:00Z",
  "featured_until": "2026-07-31T23:59:59Z"
}
```
`user_id` required. `blurb` optional (defaults empty). `featured_from` optional (defaults to now).
`featured_until` optional (`null`/omitted = indefinite, no end date).

`400`/`code: "user_opted_out"` if the target user has `include_in_leaderboard: false` — someone
who's opted out of the algorithmic leaderboard can't be editorially featured either; the opt-out
covers public donor visibility generally, not just the ranked list specifically.

Response `201`: the created entry.

#### `DELETE /admin/leaderboard/featured/{id}/` 🔒`leaderboard.manage`

Ends a spotlight early (or removes a mistaken entry entirely). `204 No Content`.

---

### Admin: Partner applications

#### `GET /admin/partner-applications/` 🔒`partner_applications.review`

[Paginated](#pagination). Filter: `?status=`.

Response items match the [public submission response shape](#partner-applications).

#### `GET /admin/partner-applications/{id}/` 🔒`partner_applications.review`

Single application. `email_verified_at` will be set — an application only reaches this list once
its email is verified (that's what triggers the reviewer notification in the first place).

#### `POST /admin/partner-applications/{id}/approve/` 🔒`partner_applications.review`

Request:
```json
{ "admin_role_id": 3, "assign_dropoff_manager": true }
```
`admin_role_id` **required** — pick any existing role by id (see [`GET /admin/roles/`](#get-adminroles-rolesmanage));
there's no hardcoded "Partner" role, you decide what this application actually grants.
`assign_dropoff_manager` defaults `true` — set `false` to grant the role without also creating the
proposed drop-off point, if the application included one.

**What this does:** grants the role to the applicant's account (which already exists — see
[Partner applications](#partner-applications) for why), and, if the application proposed a
drop-off location and `assign_dropoff_manager` is true, creates a `DropOffPoint` from those
details and adds the applicant as its manager.

`400`/`code: "email_not_verified"` if somehow called before verification. `400`/
`code: "already_reviewed"` if not currently `pending`.

Response `200`: the updated application (`status: "approved"`).

#### `POST /admin/partner-applications/{id}/reject/` 🔒`partner_applications.review`

Request:
```json
{ "reason": "We don't currently have coverage in that area." }
```

**The applicant's account is completely untouched** — they keep full normal platform access and
can submit a new application later.

Response `200`: the updated application (`status: "rejected"`).

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
`open` \| `resolved` \| `dismissed` — the latter two are set via the
[Admin API](#post-adminreportsidresolve-reportsresolve) (`resolve`/`dismiss`) or Django Admin,
never by the person who filed the report.

#### Notification category
| Value | Meaning |
|---|---|
| `request_received` | Someone requested one of your listings. |
| `request_accepted` | A request you sent was accepted. |
| `request_declined` | A request you sent was declined. |
| `exchange_scheduled` | An exchange you're party to got a scheduled time. |
| `exchange_completed` | An exchange you're party to completed — you can now rate the other party. |
| `exchange_reminder` | An upcoming exchange reminder. |
| `report_resolved` | A report you filed was resolved or dismissed. |
| `partner_application_ready` | (reviewers only) A new partner application is ready for review. |
| `partner_application_approved` | Your partner application was approved. |
| `partner_application_rejected` | Your partner application was not approved. |
| `role_assigned` | Your admin role changed (granted, changed, or revoked). |
| `system` | Generic/catch-all. |

#### Partner application status
| Value | Meaning |
|---|---|
| `pending` | Submitted, awaiting email verification and/or review. |
| `approved` | A role (and optionally a drop-off point) was granted. |
| `rejected` | Not approved — the applicant's account is unaffected and they can reapply. |

#### Hero tier

Derived from [`GET /leaderboard/`](#leaderboard)'s `completed_donation_count` — not a stored
field, computed at read time. `null` below the first threshold.

| Tier | Minimum completed donations |
|---|---|
| `Contributor` | 1 |
| `Hero` | 5 |
| `Champion` | 15 |
| `Legend` | 50 |

#### Capabilities

The full fixed vocabulary an [admin role](#roles--capabilities) can be built from — also
available live via [`GET /admin/capabilities/`](#get-admincapabilities-rolesmanage):

| Code | Grants |
|---|---|
| `users.view` | View user profiles and account status |
| `users.suspend` | Suspend / reactivate user accounts |
| `users.edit` | Edit a user's profile fields directly |
| `roles.manage` | Create, edit, delete roles and assign them to users |
| `listings.view` | View listings, including removed ones |
| `listings.remove_restore` | Remove / restore listings |
| `listings.delete_photo` | Delete an individual listing photo |
| `categories.manage` | Create / edit / delete categories |
| `reports.view` | View filed reports |
| `reports.resolve` | Resolve / dismiss reports |
| `exchanges.view` | View all exchanges |
| `exchanges.force_override` | Force-cancel / force-complete a stuck exchange |
| `requests.view` | View all book requests |
| `ratings.view` | View all user ratings |
| `dropoff.view` | View drop-off points |
| `dropoff.manage` | Create / edit / delete drop-off points assigned to you |
| `dropoff.manage_all` | Create / edit / delete any drop-off point, not just assigned ones |
| `auditlog.view` | View the admin action audit log |
| `dashboard.view` | View the admin dashboard summary |
| `stats.recompute` | Manually trigger an impact-stats recompute |
| `partner_applications.review` | Review, approve, or reject partner/drop-off applications |
| `leaderboard.manage` | Feature/unfeature a donor on the public leaderboard spotlight |

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
