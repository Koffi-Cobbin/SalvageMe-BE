# Notifications as a Feature — Plan

Right now `apps/notifications/` is real, shipped code — but it's email-only and fire-and-forget:
no persisted record, no in-app "what did I miss" list, no unread badge, no way to mark something
read. This plan turns it into an actual feature: a `Notification` model, a small user-facing API
(`GET /notifications/`, unread count, mark-read), and email as one delivery channel alongside it —
generalized so any part of the app can raise a notification, not just the partner-application
"notify reviewers" case that prompted this. **Design document, not yet implemented** (same status
as `ADMIN_API_PLAN.md` and `PARTNER_APPLICATION_PLAN.md`) — flagged separately at the end since,
unlike those two, this one touches real code already running in production.

---

## New model: `Notification`

Fills in `apps/notifications/models.py`, currently just an explanatory comment with no actual
model:

```python
class Notification(models.Model):
    class Category(models.TextChoices):
        REQUEST_RECEIVED = "request_received", "New request received"
        REQUEST_ACCEPTED = "request_accepted", "Request accepted"
        REQUEST_DECLINED = "request_declined", "Request declined"
        EXCHANGE_SCHEDULED = "exchange_scheduled", "Exchange scheduled"
        EXCHANGE_COMPLETED = "exchange_completed", "Exchange completed"
        EXCHANGE_REMINDER = "exchange_reminder", "Exchange reminder"
        REPORT_RESOLVED = "report_resolved", "Your report was resolved"       # new, see below
        PARTNER_APPLICATION_READY = "partner_application_ready", "Application ready for review"
        PARTNER_APPLICATION_APPROVED = "partner_application_approved", "Application approved"
        PARTNER_APPLICATION_REJECTED = "partner_application_rejected", "Application rejected"
        ROLE_ASSIGNED = "role_assigned", "Your admin role changed"            # new, see below
        SYSTEM = "system", "System notification"                             # generic catch-all

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="notifications", on_delete=models.CASCADE)
    category = models.CharField(max_length=32, choices=Category.choices)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    # Same target_type/target_id pattern already used by Report and AuditLog
    # elsewhere in this codebase — reused, not a new convention.
    target_type = models.CharField(max_length=32, blank=True)
    target_id = models.PositiveIntegerField(null=True, blank=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "is_read"])]
```

---

## Central dispatch — one function, two channels

Replaces the current pattern where every `notify_*` function calls the email-only `_send()`
directly. New central function:

```python
def notify(*, recipient, category: str, title: str, body: str = "",
           target_type: str = "", target_id: int | None = None, send_email: bool = True) -> Notification:
    notification = Notification.objects.create(
        recipient=recipient, category=category, title=title, body=body,
        target_type=target_type, target_id=target_id,
    )
    if send_email:
        _send(subject=title, message=body, to_email=recipient.email)  # existing helper, unchanged
    return notification
```

**Every existing `notify_request_received()`, `notify_exchange_scheduled()`, etc. becomes a thin
wrapper around `notify()` instead of calling `_send()` directly** — e.g.:

```python
def notify_request_received(book_request) -> None:
    notify(
        recipient=book_request.listing.owner,
        category=Notification.Category.REQUEST_RECEIVED,
        title=f"New request for '{book_request.listing.title}'",
        body=f"{book_request.requester.username} has requested your listing '{book_request.listing.title}'.",
        target_type="request",
        target_id=book_request.id,
    )
```

**No call sites elsewhere in the codebase need to change** — `apps/requests/services.py` and
`apps/exchanges/services.py` already call these exact function names (`notify_request_accepted`,
`notify_exchange_completed`, etc.); only the inside of `apps/notifications/services.py` changes.
This is a genuinely low-risk upgrade to code that's already shipped and tested.

---

## Two real gaps this surfaces (bonus fixes, not scope creep for its own sake)

1. **`resolve_report()` never notifies the reporter today.** When staff resolve or dismiss a
   report, the person who filed it currently hears nothing — they'd have to keep checking back.
   Adding `notify_report_resolved(report)` (called from `apps/moderation/services.py::resolve_report`,
   category `REPORT_RESOLVED`) is a straightforward fix that falls naturally out of generalizing
   this.
2. **Role changes are currently silent** (per `docs/ADMIN_API_PLAN.md`'s `assign-role` design) —
   someone granted or revoked a role has no idea unless they happen to notice new admin nav
   options appear. `notify_role_assigned(user, old_role, new_role)` closes that.

---

## User-facing API (new — currently `apps/notifications/` has no `views.py`/`urls.py` at all)

### `GET /notifications/` 🔒

[Cursor-paginated](../API_REFERENCE.md#pagination), scoped to `request.user` — never another
user's notifications. Filterable: `?is_read=false`, `?category=exchange_reminder`.

```json
{
  "next": null, "previous": null,
  "results": [
    {
      "id": 12, "category": "request_accepted", "title": "Your request for 'Intro to Algebra' was accepted",
      "body": "...", "target_type": "request", "target_id": 15,
      "is_read": false, "created_at": "2026-07-16T10:05:00Z"
    }
  ]
}
```
`target_type`/`target_id` let the frontend build a deep link (e.g. `request_type: "request"` →
link to that request's detail view) without needing per-category routing logic hardcoded on the
frontend — one generic "click a notification, navigate to its target" handler covers every
category.

### `GET /notifications/unread-count/` 🔒

```json
{ "count": 4 }
```
For a bell-icon badge — cheap enough to poll every so often (e.g. on route change, or a short
interval) given this backend has no websocket/push infrastructure (see
[Real-time delivery](#explicitly-out-of-scope) below).

### `POST /notifications/{id}/read/` 🔒

No body. Sets `is_read=True`, `read_at=now()`. `404` if it's not this user's notification (same
not-a-party-so-invisible pattern used throughout the rest of this codebase's scoped resources).

### `POST /notifications/mark-all-read/` 🔒

No body. Marks every unread notification belonging to `request.user` as read in one call — the
"clear the badge" action.

### `DELETE /notifications/{id}/` 🔒

Lets a user dismiss/remove their own notification from the list. `404` per the same scoping rule.

---

## Update to `PARTNER_APPLICATION_PLAN.md`

That document's "Notifying reviewers" section currently proposes a bespoke
`notify_partner_application_ready()` that only sends email. Under this plan, it becomes a thin
wrapper calling the shared `notify()` — same trigger condition and `reviewers_notified_at` guard
as already designed, just also creating a `Notification` row per reviewer (category
`PARTNER_APPLICATION_READY`, `target_type="partner_application"`) so it shows up in their in-app
list too, not only their inbox. No other change to that document's design.

---

## Explicitly out of scope

- **Real-time delivery** (websockets, push notifications, SSE). This backend has no persistent
  worker/connection infrastructure by design (see the existing `ASYNC & SCHEDULED WORK` section of
  the main README — PythonAnywhere free tier). This plan is deliberately pull-based: the frontend
  polls `unread-count`/`list`, it doesn't get pushed to. A move to real-time delivery later would
  be a much bigger infrastructure change, not a small addition to this plan.
- **Per-category notification preferences** (e.g. "email me for exchange reminders but not new
  requests"). Reasonable future addition — would be a `NotificationPreference` model keyed on
  `(user, category)` — but adds real complexity for a first version. Every category currently
  always sends both an in-app row and an email, same as today's behavior, just now also persisted.
- **Auto-expiring/pruning old notifications.** Would fit naturally into the existing
  `run_daily_jobs` management command (one more function alongside `expire_stale_requests`,
  `recompute_impact_stats`, etc.) if the table grows large enough to matter — not needed at launch.

---

## A note on scope, since this crosses from planning into real code

`ADMIN_API_PLAN.md` and `PARTNER_APPLICATION_PLAN.md` propose entirely new apps/models that don't
exist yet — pure planning, zero risk to anything currently running. **This plan is different: it
proposes changing `apps/notifications/services.py`, which is real code already called from
`apps/requests/services.py` and `apps/exchanges/services.py` in the currently-deployed backend**,
plus a genuinely new model + migration + new public endpoints. Low risk (the wrapper functions
keep the same signatures, so nothing calling them needs to change), but it's still a real schema
migration against your production database, not just a markdown file. I'd want to actually
implement and test this properly (migration, full test coverage including the notify-wrapping
behavior, a verification run against real Postgres+PostGIS like everything else in this repo) —
say the word whenever you want that started, separately from continuing to flesh out the
admin/partner plans if you'd rather keep those moving first.
