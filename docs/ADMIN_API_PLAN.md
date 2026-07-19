# Admin API Plan

A proposal for a set of staff-only REST endpoints so the frontend can build a custom admin panel,
instead of moderators/staff using Django Admin directly. **This is a design document, not yet
implemented** — nothing in this file exists in the API today. It's grounded in exactly what
Django Admin currently does across `apps/*/admin.py`, so nothing gets lost in the move and nothing
speculative gets added without being flagged as such.

---

## Why build this at all

Right now, every moderation/admin action (suspend a user, remove a listing, resolve a report,
manage categories/drop-off points) only exists in Django Admin (`/admin/`). That's fine for an
MVP, but it means:
- Staff need a separate login flow and UI (Django's server-rendered admin) instead of your app's
  own design system.
- There's no way for the frontend to show staff-relevant info (open report count, etc.) inline in
  your own UI.
- Django Admin doesn't have a mobile-friendly UI, which matters if moderators are checking things
  on the go.

## What Django Admin currently provides (the source of truth for this plan)

| Model | Django Admin capability | Where |
|---|---|---|
| `User` | list/search/filter (role, verified, staff, active); edit any field including `is_staff`/`is_active`; bulk **suspend**/**reactivate** (writes an `AuditLog` entry); inline view of their listings + reports filed | `apps/accounts/admin.py` |
| `UserRating` | list/search — no admin actions defined | `apps/accounts/admin.py` |
| `Listing` | list/search/filter (status, category, condition); bulk **remove**/**restore** (writes `AuditLog`); inline photos (read-only) | `apps/listings/admin.py` |
| `Category` | full CRUD (add/change/delete), slug auto-prepopulated | `apps/listings/admin.py` |
| `Report` | list/search/filter (status, reason, target_type); bulk **resolve**/**dismiss** (writes `AuditLog`, via `moderation.services.resolve_report`) | `apps/moderation/admin.py` |
| `AuditLog` | list/search/filter — **read-only**, add disabled entirely | `apps/moderation/admin.py` |
| `Exchange` | list/search/filter (status); marked "read-mostly view for support/debugging" — `listing`/`donor`/`recipient`/`completed_at` are read-only, but `status`/`scheduled_at`/`dropoff_point` are editable | `apps/exchanges/admin.py` |
| `BookRequest` | list/search/filter (status) — no admin actions defined | `apps/requests/admin.py` |
| `DropOffPoint` | full CRUD — **currently the only way to create one at all**; the public API only exposes `GET` | `apps/dropoff/admin.py` |
| `ImpactStatsSnapshot` | list only — add/change both explicitly disabled (it's a computed, immutable log) | `apps/analytics/admin.py` |

Everything below maps directly to a row in this table, plus a small number of clearly-flagged
additions that don't exist in Django Admin today but are natural for a dashboard-style admin UI.

---

## Architecture decisions

### 1. Where this code lives: extend existing apps, not a new `apps/admin` app

Admin endpoints for users live in `apps/accounts/`, admin endpoints for listings live in
`apps/listings/`, etc. — same pattern the codebase already uses (e.g.
`apps/requests/services.py::accept_request` is called from both the public `accept` action *and*
could back an admin override). A single monolithic `apps/adminpanel` app would either duplicate
model imports across app boundaries or create a circular-import mess. Each app gets:
- `AdminXSerializer` classes in its existing `serializers.py` (or a new `admin_serializers.py` if
  the file gets big)
- `AdminXViewSet` classes in its existing `views.py`
- Routes registered under an `admin/` prefix in a new `admin_urls.py` per app, wired into
  `config/api_urls.py` similarly to how `auth_urls.py` is separated from `urls.py` today.

Resulting URL shape: `/api/v1/admin/users/`, `/api/v1/admin/listings/`, etc.

### 2. Roles & access control

This section changed twice now: originally a single `is_staff` flag, then a fixed four-role enum
(`admin`/`volunteer`/`partner`/`none`), and now **fully dynamic** — an Admin can create new named
roles at any time and choose exactly which capabilities each one grants, without a code deploy.
This is a real architecture shift from the previous draft, closer to Django's own Groups/
Permissions model than a hardcoded enum. Old approaches are kept at the bottom under
[Rejected alternatives](#rejected-alternatives) so the reasoning for the change stays visible.

#### The core idea: capabilities are fixed in code, roles are data

A **capability** is a specific, named permission check tied to a specific admin action — e.g.
`listings.remove_restore`, `reports.resolve`, `users.suspend`. Capabilities can only be defined in
code, because each one corresponds to an actual permission check guarding actual endpoint logic —
a capability with no matching `if` statement anywhere would do nothing. The list of capabilities
grows only when new admin endpoints get built.

A **role**, however, is just a database row: a name, a description, and a set of capability codes
picked from that fixed list. **Roles are fully admin-creatable and editable at runtime** — that's
the flexibility you asked for. An Admin can create a "Content Moderator" role with just
`listings.remove_restore` + `reports.resolve`, or a "Regional Partner Lead" role with a totally
different set, at any time, with no deploy.

#### New models

```python
# apps/accounts/models.py (or a new apps/accounts/rbac.py if this grows large)

class AdminRole(models.Model):
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    # Validated against common/admin_capabilities.py::ALL_CAPABILITIES at the serializer level —
    # not a DB-level FK-to-capability table, since capabilities are code-defined, not data.
    capabilities = models.JSONField(default=list)
    # True only for the single built-in "Admin" role seeded by migration — see safeguards below.
    is_protected = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class User(AbstractUser):
    ...
    # Null = no admin access at all. FK, not a TextChoices field — this is the change from the
    # previous draft that makes roles dynamic instead of a fixed enum.
    admin_role = models.ForeignKey(
        AdminRole, null=True, blank=True, on_delete=models.PROTECT, related_name="users"
    )
```

`on_delete=PROTECT` on the FK means a role that's currently assigned to any user can't be deleted
out from under them — see the `DELETE /admin/roles/{id}/` entry below.

#### The fixed capability vocabulary

Defined once in code (`common/admin_capabilities.py`), imported by both the permission class and
the `GET /admin/capabilities/` endpoint that feeds the frontend's role-editor checkbox list:

```python
# common/admin_capabilities.py
ALL_CAPABILITIES = {
    "users.view": "View user profiles and account status",
    "users.suspend": "Suspend / reactivate user accounts",
    "users.edit": "Edit a user's profile fields directly",
    "roles.manage": "Create, edit, delete roles and assign them to users",
    "listings.view": "View listings, including removed ones",
    "listings.remove_restore": "Remove / restore listings",
    "listings.delete_photo": "Delete an individual listing photo",
    "categories.manage": "Create / edit / delete categories",
    "reports.view": "View filed reports",
    "reports.resolve": "Resolve / dismiss reports",
    "exchanges.view": "View all exchanges",
    "exchanges.force_override": "Force-cancel / force-complete a stuck exchange",
    "requests.view": "View all book requests",
    "ratings.view": "View all user ratings",
    "dropoff.view": "View drop-off points",
    "dropoff.manage": "Create / edit / delete drop-off points assigned to you",
    "dropoff.manage_all": "Create / edit / delete any drop-off point, not just assigned ones",
    "auditlog.view": "View the admin action audit log",
    "dashboard.view": "View the admin dashboard summary",
    "stats.recompute": "Manually trigger an impact-stats recompute",
    "partner_applications.review": "Review, approve, or reject partner/drop-off applications",
}
```
This list is exactly the set of capabilities referenced by the endpoint tables further down —
nothing here is speculative beyond what's actually enforced somewhere.

#### Permission class: `HasCapability`

Replaces the role-name-based `HasAdminRole` from the previous draft. Every endpoint declares which
*capability* it needs, completely decoupled from what any role happens to be named:

```python
# common/permissions.py
class HasCapability(BasePermission):
    """Usage: permission_classes = [HasCapability("listings.remove_restore")]"""
    def __init__(self, capability: str):
        self.capability = capability

    def has_permission(self, request, view):
        role = getattr(request.user, "admin_role", None)
        return bool(
            request.user
            and request.user.is_authenticated
            and role is not None
            and self.capability in role.capabilities
        )
```

#### `GET /admin/me/` 🔓 (any authenticated user)

Unchanged in purpose from the previous draft, updated shape — now returns concrete capabilities
rather than a role name, since that's what the frontend actually needs to decide what UI to show.
**Normal users (`admin_role` null) must never even see admin navigation** — this is the endpoint
that decision is based on, called once after login:

```json
{
  "admin_role": { "id": 3, "name": "Content Moderator" },
  "capabilities": ["listings.remove_restore", "reports.resolve", "reports.view", "listings.view"],
  "can_access_admin": true
}
```
For a normal user: `{ "admin_role": null, "capabilities": [], "can_access_admin": false }`. The
frontend router hides/blocks the entire `/admin` route tree on that response, and can also use the
`capabilities` array directly to show/hide individual admin sections/buttons — e.g. hide the
"Categories" nav item entirely if `categories.manage` isn't present, rather than showing it and
having every action inside 403.

#### `GET /admin/capabilities/` 🔒 requires `roles.manage`

Returns the fixed vocabulary above, for the role-editor UI's checkbox list:
```json
[
  { "code": "users.view", "description": "View user profiles and account status" },
  { "code": "users.suspend", "description": "Suspend / reactivate user accounts" }
]
```

#### `GET /admin/roles/` 🔒 requires `roles.manage`

```json
[
  { "id": 1, "name": "Admin", "description": "Full access.", "capabilities": ["users.view", "..."], "is_protected": true },
  { "id": 3, "name": "Content Moderator", "description": "Handles listing/report moderation.", "capabilities": ["listings.remove_restore", "reports.resolve"], "is_protected": false }
]
```

#### `POST /admin/roles/` 🔒 requires `roles.manage`

```json
{ "name": "Content Moderator", "description": "Handles listing/report moderation.", "capabilities": ["listings.remove_restore", "reports.resolve", "reports.view", "listings.view"] }
```
`400`/`code: "unknown_capability"` if any code isn't in `ALL_CAPABILITIES`. `400`/
`code: "duplicate_name"` on a repeated name. Writes an `AuditLog` entry (`action: "role_created"`).

#### `PATCH /admin/roles/{id}/` 🔒 requires `roles.manage`

Edit `name`, `description`, `capabilities`. **The built-in `is_protected` role's `capabilities`
field cannot be edited** (`400`/`code: "role_protected"`) — `name`/`description` can still be
changed for cosmetic reasons, but its capability set is fixed. This guarantees there's always at
least one role with every capability including `roles.manage` itself, so the system can never be
edited into a state where nobody can manage roles anymore (a broader, more correct version of the
"last-admin lockout" safeguard from the previous draft — see below). Writes an `AuditLog` entry
(`action: "role_updated"`, `metadata` includes the diff).

#### `DELETE /admin/roles/{id}/` 🔒 requires `roles.manage`

`400`/`code: "role_protected"` for the built-in role. `400`/`code: "role_in_use"` if any user
currently has this role assigned (mirrors the existing `Category`/`Listing` `on_delete=PROTECT`
pattern already used elsewhere in this codebase — same design language, not a new concept).
Reassign or clear (`assign-role` with `admin_role_id: null`) every affected user first.

#### `POST /admin/users/{id}/assign-role/` 🔒 requires `roles.manage`

```json
{ "admin_role_id": 3 }
```
`admin_role_id: null` revokes admin access entirely (back to a normal user). `404` if the role id
doesn't exist. Writes an `AuditLog` entry (`action: "user_role_assigned"`, `metadata:
{"old_role_id": 1, "new_role_id": 3}`).

**Safeguard — last-capable-user lockout:** if this call would leave **zero users** holding a role
with `roles.manage`, reject with `400`/`code: "last_role_manager"`. This is the generalized,
correct version of the earlier draft's "last Admin" check — with dynamic roles, what actually
matters isn't "is there still an Admin" (a name), it's "can anyone still manage roles at all."
Combined with the protected built-in role above, this closes the lockout footgun completely: the
protected role always has `roles.manage`, and this check ensures at least one user always holds a
role that includes it.

#### Seeding: the one built-in role

A data migration creates a single `AdminRole(name="Admin", capabilities=<all of them>,
is_protected=True)` and assigns it to whichever user(s) currently have `is_staff=True` (if any) —
so nobody loses access when this ships, and there's always at least one usable "break-glass" role
out of the box that satisfies "Main Admin/superuser has full control." Everything past that first
role — Volunteer, Partner, or anything else — is created through the API by whoever holds it, not
seeded by this plan. That's the actual flexibility being asked for: this document deliberately
does **not** hardcode Volunteer/Partner as special-cased role names anywhere in the schema or
permission logic anymore, only as *suggested starting points* an Admin would likely create first
via `POST /admin/roles/`.

#### Suggested starting roles (created via the API, not hardcoded)

Not part of the schema — just a sensible starting point once the system ships, listing which
capabilities from the vocabulary above a first "Volunteer" and "Partner" role would likely include,
based on the previous draft's reasoning:

| Suggested role | Suggested capabilities |
|---|---|
| Volunteer | `listings.view`, `listings.remove_restore`, `reports.view`, `reports.resolve`, `exchanges.view`, `requests.view`, `ratings.view`, `auditlog.view`, `dashboard.view` |
| Partner | `dropoff.view`, `dropoff.manage`, `listings.view`, `exchanges.view` |

Because roles are just data now, this table is a suggestion for whoever holds the built-in Admin
role to create after deployment (or a `seed_demo_data`-style management command could create them
as a convenience) — not something this plan needs to lock in.

#### Drop-off scoping: **confirmed — Option B, scoped to assigned points**

A user with `dropoff.manage` (as opposed to the broader `dropoff.manage_all`) only sees/manages
drop-off points they've been explicitly assigned to — not the full list. Requires a real schema
addition:

```python
# apps/dropoff/models.py
class DropOffPoint(models.Model):
    ...
    managers = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="managed_dropoff_points"
    )
```

**How the scoping actually applies, end to end:**

- `GET /admin/dropoff-points/` — a user with `dropoff.manage` (not `_all`) only gets points in
  `request.user.managed_dropoff_points`. A user with `dropoff.manage_all` gets every point,
  same as today's unscoped read.
- `PATCH` / `DELETE /admin/dropoff-points/{id}/` — `404` (not `403` — same reasoning as the
  book-request/exchange scoping already in this plan: don't reveal that a point exists to someone
  who isn't assigned to it) if the point isn't in their `managed_dropoff_points` and they don't
  hold `dropoff.manage_all`.
- `POST /admin/dropoff-points/` (**create**) — a brand-new point has no managers yet, so creating
  one requires `dropoff.manage_all` specifically, not plain `dropoff.manage`. A scoped-only
  manager can edit what they're assigned to but can't conjure a new, unassigned point into
  existence (there'd be nothing stopping them from creating points nobody scoped them to, which
  defeats the point of scoping). If your actual workflow is "a partner should be able to register
  their own new location," say so and this rule can be relaxed — auto-assigning the creator as a
  manager of whatever they just created would be the natural fix.
- **`GET /admin/exchanges/`, `GET /admin/listings/`** — for a `dropoff.manage`-only user, also
  filtered to `dropoff_point__in=request.user.managed_dropoff_points` if they don't separately
  hold `exchanges.view`/`listings.view` unscoped. (If they *do* hold those broader capabilities —
  e.g. an Admin also happens to have `dropoff.manage` — the broader capability wins; scoping only
  narrows access for someone who has *only* the scoped capability, it never further restricts
  someone who already has the unscoped one.)

#### New endpoint: assigning managers to a drop-off point

Someone has to grant that assignment in the first place. Proposed:

##### `POST /admin/dropoff-points/{id}/assign-managers/` 🔒`dropoff.manage_all`

```json
{ "user_ids": [42, 57] }
```
Replaces the full manager list for this point with exactly these users (not additive — simpler
mental model than separate add/remove endpoints, and a drop-off point's manager list is small
enough that resending the full set each time isn't a burden). Deliberately gated to
`dropoff.manage_all`, not plain `dropoff.manage` — a scoped manager can run *their* location but
can't grant *other people* access to it (that's an escalation decision, reserved for whoever has
the unscoped capability, same reasoning as `roles.manage` being separate from `users.edit`
earlier in this doc). Writes an `AuditLog` entry (`action: "dropoff_managers_assigned"`).

`GET /admin/dropoff-points/{id}/` now also includes a `managers` field (list of
`{id, username}`) so the frontend can show who's currently assigned without a separate call.

#### Rejected alternatives

1. **Single `is_staff` flag** — the very first draft. Superseded because it can't express "limited
   control" at all, only all-or-nothing.
2. **Fixed four-role enum** (`admin`/`volunteer`/`partner`/`none`) — the second draft, built
   directly from your first message about roles. Superseded by this version because you asked for
   roles to be creatable at any time with associated permissions, which a hardcoded
   `TextChoices` enum structurally can't do without a migration + deploy every time a new role is
   needed.

### 3. Every mutating admin action writes an `AuditLog` entry — no exceptions

This isn't new — it's already the pattern (`record_audit_log()` calls inside every Django Admin
action in the table above). The plan carries that forward as a hard rule: **any endpoint below
that changes state must call `apps.moderation.services.record_audit_log()`**, using the same
`action` naming convention already in use (`user_suspended`, `listing_removed`,
`report_resolved`, etc.) so the existing `AuditLog` viewer keeps working as a unified trail across
both Django Admin and the new API, without needing to distinguish which surface an action came
from.

### 4. Status-bearing resources: action endpoints, not open `PATCH`

Django Admin's `Exchange` admin currently allows directly editing `status` via the change form —
that's a footgun once this becomes an API a frontend calls programmatically (nothing stops a
buggy PATCH from setting an invalid status combination the state-machine functions in
`apps/exchanges/services.py` would never produce). This plan deliberately **does not** expose raw
`status` PATCH for `Listing`/`Exchange`/`BookRequest`; instead it adds narrow, named admin
override actions (`force-cancel`, etc.) that go through the same service-layer functions the
public API already uses wherever possible, or clearly-scoped new ones where an admin-only
transition doesn't have a public equivalent (e.g. force-completing a stuck exchange).

### 5. Pagination: page-number, not cursor — deliberately different from the public API

The public API uses cursor pagination (`common/pagination.py::CursorSetPagination`), which is
right for an infinite-scroll public listings feed but wrong for an admin data table, where staff
expect page numbers and a total count ("Showing 21–40 of 214"). This plan adds a new
`AdminPageNumberPagination` (in `common/pagination.py`, alongside the existing class) used only by
`/admin/` endpoints. This is an intentional UX-driven inconsistency with the public API, not an
oversight — flagging it explicitly so it isn't "fixed" into consistency by mistake later.

### 6. Search/filter/ordering: `django-filter` + DRF's `SearchFilter`/`OrderingFilter`

Django Admin's `list_filter`/`search_fields`/default ordering map directly onto DRF's
`DjangoFilterBackend` (already a project dependency, used by the public listings endpoint),
`filters.SearchFilter`, and `filters.OrderingFilter`. Each admin viewset below lists which fields
get which treatment, mirroring its `admin.py` counterpart's `list_filter`/`search_fields` almost
1:1.

### 7. Schema/docs: tag everything `Admin` in drf-spectacular

`drf-spectacular` (already generating `/api/schema/`, `/api/docs/`) supports `@extend_schema(tags=[...])`.
Every admin viewset gets `tags=["Admin"]` so Swagger UI groups them separately from the public
API — useful given this doc proposes roughly doubling the endpoint count.

---

## Proposed endpoints

Legend: 🔒`capability.code` = requires that specific capability (see the vocabulary above) — a
user's `admin_role.capabilities` must include it, via whatever role an Admin assigned them. All
under `/api/v1/admin/`.

### Roles & capabilities (the meta-endpoints — see above for full detail)

| Method & path | Required capability |
|---|---|
| `GET /admin/me/` | none — any authenticated user |
| `GET /admin/capabilities/` | 🔒`roles.manage` |
| `GET /admin/roles/`, `POST`, `PATCH /{id}/`, `DELETE /{id}/` | 🔒`roles.manage` |
| `POST /admin/users/{id}/assign-role/` | 🔒`roles.manage` |

### Users

| Method & path | Required capability | Maps to | Notes |
|---|---|---|---|
| `GET /admin/users/` | 🔒`users.view` | list/search/filter | Search: `username`, `email`, `phone`. Filter: `role`, `is_verified`, `is_active`, `admin_role`. |
| `GET /admin/users/{id}/` | 🔒`users.view` | detail | Full profile — same shape as `GET /users/me/`, plus `is_active`/`admin_role` (never exposed on the self-service endpoint). Consider nesting `listings` (id/title/status) and `reports_filed` (id/reason/status) summaries, mirroring the two Django Admin inlines. |
| `PATCH /admin/users/{id}/` | 🔒`users.edit` | edit profile fields | `role`, `phone`, `is_verified`. **Does not include `admin_role`** — that's exclusively via `assign-role` (`roles.manage`), so a role with `users.edit` but not `roles.manage` can't grant themselves/others admin access through the back door via a generic PATCH. Writes an `AuditLog` entry (`user_updated`) with a diff in `metadata`. |
| `POST /admin/users/{id}/suspend/` | 🔒`users.suspend` | `suspend_users` action | Sets `is_active=False`. `400` if already suspended. |
| `POST /admin/users/{id}/reactivate/` | 🔒`users.suspend` | `reactivate_users` action | Sets `is_active=True`. Same capability as suspend — they're the inverse of the same power, not split into two. |

### Listings

| Method & path | Required capability | Maps to | Notes |
|---|---|---|---|
| `GET /admin/listings/` | 🔒`listings.view` | list/search/filter | Search: `title`, `owner__username`. Filter: `status`, `category`, `condition`. **Unlike the public endpoint, returns all statuses including `removed`.** |
| `GET /admin/listings/{id}/` | 🔒`listings.view` | detail | Full listing, any status. |
| `POST /admin/listings/{id}/remove/` | 🔒`listings.remove_restore` | `remove_listings` action | Sets `status=removed`. |
| `POST /admin/listings/{id}/restore/` | 🔒`listings.remove_restore` | `restore_listings` action | Sets `status=available`. `400` if currently `pending`/`claimed`. |
| `DELETE /admin/listings/{id}/photos/{photo_id}/` | 🔒`listings.delete_photo` | *(new — no equivalent today)* | Uses `apps.listings.services.delete_listing_photo()` (already exists, currently unused by any endpoint). |

### Categories

| Method & path | Required capability | Maps to | Notes |
|---|---|---|---|
| `GET /admin/categories/` | 🔒`categories.manage` | list | Reuses the existing public `CategorySerializer`. |
| `POST /admin/categories/` | 🔒`categories.manage` | add | `slug` auto-generated from `name` if omitted. |
| `PATCH /admin/categories/{id}/` | 🔒`categories.manage` | change | |
| `DELETE /admin/categories/{id}/` | 🔒`categories.manage` | delete | `Listing.category` is `on_delete=PROTECT` — surfaced as `400`/`code: "category_in_use"` rather than a raw 500. |

*(Read access isn't split from write here — categories are low-stakes reference data and the
public `GET /categories/` already exists unauthenticated, so there's no separate `categories.view`
capability; a role either manages them or doesn't need this section at all.)*

### Reports

| Method & path | Required capability | Maps to | Notes |
|---|---|---|---|
| `GET /admin/reports/` | 🔒`reports.view` | list/search/filter | Search: `reporter__username`, `detail`. Filter: `status`, `reason`, `target_type`. |
| `GET /admin/reports/{id}/` | 🔒`reports.view` | detail | |
| `POST /admin/reports/{id}/resolve/` | 🔒`reports.resolve` | `resolve_reports` action | Calls existing `moderation.services.resolve_report(outcome=RESOLVED)` directly. |
| `POST /admin/reports/{id}/dismiss/` | 🔒`reports.resolve` | `dismiss_reports` action | Same, `outcome=DISMISSED`. Resolve/dismiss share one capability (both are "handle this report"), not split in two. |

### Exchanges (support/intervention)

| Method & path | Required capability | Maps to | Notes |
|---|---|---|---|
| `GET /admin/exchanges/` | 🔒`exchanges.view` | list/search/filter | Search: `listing__title`, `donor__username`, `recipient__username`. Filter: `status`. Every exchange, not scoped to the current user. |
| `GET /admin/exchanges/{id}/` | 🔒`exchanges.view` | detail | |
| `POST /admin/exchanges/{id}/force-cancel/` | 🔒`exchanges.force_override` | *(replaces open `status` PATCH)* | Reuses `exchanges.services.cancel_exchange()` logic, bypassing the party-only check. Requires a `reason` field, stored in the `AuditLog` `metadata`. |
| `POST /admin/exchanges/{id}/force-complete/` | 🔒`exchanges.force_override` | *(new)* | For a handoff confirmed outside the app. Same `reason`-required treatment. |

### Book requests (read-only support visibility)

| Method & path | Required capability | Maps to | Notes |
|---|---|---|---|
| `GET /admin/requests/` | 🔒`requests.view` | list/search/filter | Search: `listing__title`, `requester__username`. Filter: `status`. All requests. |
| `GET /admin/requests/{id}/` | 🔒`requests.view` | detail | No write endpoints — accept/decline are inherently the listing owner's call, not staff's. |

### User ratings (trust & safety, read-only for MVP)

| Method & path | Required capability | Maps to | Notes |
|---|---|---|---|
| `GET /admin/ratings/` | 🔒`ratings.view` | list/search/filter | Search: `rated_user__username`, `rated_by__username`. Filter: `score`. |
| `GET /admin/ratings/{id}/` | 🔒`ratings.view` | detail | |

### Drop-off points

| Method & path | Required capability | Maps to | Notes |
|---|---|---|---|
| `GET /admin/dropoff-points/` | 🔒`dropoff.view`, scoped by `managed_dropoff_points` unless `dropoff.manage_all` | list | Includes a `managers` field (list of `{id, username}`) on each point. |
| `GET /admin/dropoff-points/{id}/` | 🔒`dropoff.view`, same scoping | detail | `404` (not `403`) if not assigned and lacking `dropoff.manage_all` — same not-a-party-so-invisible pattern as requests/exchanges elsewhere in this doc. |
| `POST /admin/dropoff-points/` | 🔒`dropoff.manage_all` only | add | **Closes a real gap** — currently only Django Admin can create one. Deliberately *not* available to plain `dropoff.manage`, since a brand-new point has no managers yet — see the note above if you'd rather let a scoped manager self-create-and-auto-assign instead. |
| `PATCH /admin/dropoff-points/{id}/` | 🔒`dropoff.manage` (assigned points only) or `dropoff.manage_all` (any) | change | Scoped per the design above. |
| `DELETE /admin/dropoff-points/{id}/` | same as PATCH | delete | `Exchange.dropoff_point` is `on_delete=SET_NULL` — always safe, no protected-delete case here. |
| `POST /admin/dropoff-points/{id}/assign-managers/` | 🔒`dropoff.manage_all` only | *(new)* | `{"user_ids": [42, 57]}` — replaces the full manager list. See detail above. |

### Audit log (read-only)

| Method & path | Required capability | Maps to | Notes |
|---|---|---|---|
| `GET /admin/audit-log/` | 🔒`auditlog.view` | list/search/filter | Search: `actor__username`. Filter: `action`, `target_type`. Default ordering `-created_at`. Single trail covering every admin action, including role/capability changes. |
| `GET /admin/audit-log/{id}/` | 🔒`auditlog.view` | detail | Includes the full `metadata` JSON field. |

*No write endpoints — matches Django Admin's `has_add_permission() = False`.*

### Dashboard & stats

| Method & path | Required capability | Notes |
|---|---|---|
| `GET /admin/dashboard/` | 🔒`dashboard.view` | Aggregation endpoint for an admin landing page: `open_reports_count`, `pending_requests_count`, `unverified_users_count`, `listings_created_today`, etc. |
| `GET /admin/stats/history/` | 🔒`dashboard.view` | List of `ImpactStatsSnapshot` over time — read-only. |
| `POST /admin/stats/recompute/` | 🔒`stats.recompute` | Manually triggers the existing `recompute_impact_stats()` — split into its own capability since it's a write action, unlike the two read-only entries above. |

### Partner applications

Full design — model, public submission endpoint, email-verification requirement, and the admin
approve/reject flow (accounts are created at **submission** time, not approval — a rejected
applicant keeps a fully normal account) — is in its own document:
**[`docs/PARTNER_APPLICATION_PLAN.md`](./PARTNER_APPLICATION_PLAN.md)**, since it's substantial
enough (and involves a new public-facing form, not just admin-side endpoints) to not cram into
this table. It reuses this plan's `assign-role` and `assign-managers` logic rather than
duplicating it, adds one capability — `partner_applications.review` — to the vocabulary above, and
its reviewer-notification step is itself powered by
**[`docs/NOTIFICATIONS_PLAN.md`](./NOTIFICATIONS_PLAN.md)**, a general in-app + email notification
feature (not specific to partner applications) that also closes a couple of existing gaps in the
already-shipped codebase — e.g. report resolutions currently never notify the reporter.

---

## Explicitly out of scope for this plan

- **Bulk actions** (Django Admin's checkbox-select-many-then-apply-action UI). Every action above
  is single-object (`/admin/listings/{id}/remove/`, not a bulk endpoint taking a list of ids).
  Recommend shipping single-object first and adding bulk variants only if staff actually hit a
  workflow where it matters — bulk actions need more careful partial-failure handling (what
  happens if 3 of 10 selected listings are already removed?) that isn't worth designing
  speculatively.
- **Per-user custom permission grids** beyond the four roles (Admin/Volunteer/Partner/None) —
  e.g. a Volunteer who can resolve reports but not touch listings. The four-role model above
  covers the stated requirement; a fully generalized permission system (individual capability
  toggles per user) is a bigger, separate design question if it turns out four roles isn't
  granular enough in practice.
- **Editing `UserRating`** beyond read-only listing (see note above).
- **User impersonation / "log in as"** — a common admin-panel feature, but security-sensitive
  enough to deserve its own dedicated design (session handling, audit requirements, JWT
  implications) rather than a line item here.

---

## Suggested phasing

1. **Phase 1 — the role/capability system itself, plus highest-value endpoints.** `AdminRole`
   model + `User.admin_role` FK + migration + data migration seeding the protected "Admin" role
   for existing staff, `common/admin_capabilities.py` vocabulary, `HasCapability` permission class,
   `GET /admin/me/`, `GET /admin/capabilities/`, `GET/POST/PATCH/DELETE /admin/roles/`,
   `POST /admin/users/{id}/assign-role/` (with the last-role-manager safeguard) — this is the
   prerequisite for everything else. Bundled with it: Users (list/detail/suspend/reactivate),
   Listings (list/detail/remove/restore), Reports (list/detail/resolve/dismiss) — these three reuse
   existing service-layer functions with zero new business logic. Once this phase ships, whoever
   holds the built-in Admin role creates the actual Volunteer/Partner/etc. roles through the API —
   no further code changes needed to introduce a new role.
2. **Phase 2 — straightforward CRUD, no state-machine risk.** Categories, Drop-off points — built
   scoped from the start now that Option B is confirmed (the `managers` M2M field,
   `assign-managers` endpoint, and `dropoff.manage` vs `dropoff.manage_all` split all ship
   together, not as a later fast-follow).
3. **Phase 3 — the partner application flow** (see
   [`docs/PARTNER_APPLICATION_PLAN.md`](./PARTNER_APPLICATION_PLAN.md)). Depends directly on
   Phases 1–2 (`assign-role`, `assign-managers`, drop-off points all need to exist first), plus a
   new prerequisite of its own: the `POST /auth/set-password/` invite flow. Worth sequencing here
   rather than earlier or later since it's the first place in this plan multiple pieces (roles,
   drop-off management, and now account provisioning) compose together — a good integration-risk
   checkpoint before moving on to the exchange overrides below.
4. **Phase 4 — needs the most care.** Exchange force-cancel/force-complete (bypasses the normal
   party-only state machine — get the `reason`-required + audit-log design right before shipping),
   plus the read-only Requests/Ratings list views. Also apply the same `managed_dropoff_points`
   scoping here for `dropoff.manage`-only users, per the note in the drop-off scoping section
   above (their `GET /admin/exchanges/`/`GET /admin/listings/` results narrow to their assigned
   point(s) unless they separately hold the unscoped `exchanges.view`/`listings.view`).
5. **Phase 5 — polish once the core moderation loop is live.** Dashboard aggregation, audit log
   viewer, stats history/manual recompute.

---

## What I'd need from you to move to implementation

- Confirmation on the pagination/URL-namespace decisions (page-number pagination,
  `/api/v1/admin/` prefix, per-app file layout) — the parts most annoying to change after the fact.
- Whether `PATCH /admin/users/{id}/` (direct field edit, gated by `users.edit`) is wanted at all,
  or too broad even scoped that way — everything else in this plan is a named action rather than
  an open field edit.
- Whether the [suggested starting capability sets](#suggested-starting-roles-created-via-the-api-not-hardcoded)
  for a first Volunteer/Partner role look right, or you'd rather define those yourself once the
  system is live (nothing in the schema forces using the suggestions — they're not seeded by
  default, see the seeding note above).
- One small residual call on drop-off scoping: should `POST /admin/dropoff-points/` stay
  `dropoff.manage_all`-only (an Admin creates a point, then assigns a Partner to it), or should a
  scoped Partner be allowed to self-create a new point and get auto-assigned as its manager? The
  plan currently assumes the former (Admin-provisions-then-assigns) as the safer default — flag if
  partners are expected to onboard new locations themselves.
- Priority order if it doesn't match the phasing above.

Happy to start implementing Phase 1 as soon as you'd like — same standard as the rest of this
codebase (real service-layer functions, full test coverage including permission tests per
capability, audit-log assertions, and a schema that stays clean under `--fail-on-warn`).
audit-log assertions, and a schema that stays clean under `--fail-on-warn`).
