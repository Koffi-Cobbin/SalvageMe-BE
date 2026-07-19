# Partner Application Flow — Plan

A public form for someone to apply to become a Partner and/or offer their location as a drop-off
point, reviewed by an Admin, who can approve (granting a role, and optionally creating a drop-off
point) or reject. This builds directly on `docs/ADMIN_API_PLAN.md` — read that first; this
document assumes the role/capability system and drop-off scoping design from it already exist.
**Design document, not yet implemented.**

---

## The flow, end to end

```
1. Visitor fills out a public form → POST /partner-applications/

   Authenticated at submission:
     → applicant_user = request.user immediately (no new account)
     → treated as already verified (they're logged in) → notify reviewers now (step 3)

   Not authenticated:
     → a new User is created immediately, as a completely normal user — same
       as anyone who used POST /auth/register/, just with an unusable
       password instead of one they chose. This account is real and usable
       for everything else on the platform (browsing, listing, requesting)
       regardless of what happens to the application.
     → PartnerApplication.applicant_user is set to this new user right away
     → ONE email is sent: verify your email + set your password (combined,
       since both need doing before this account is fully theirs)
     → reviewers are NOT notified yet — wait for step 2

2. (unauthenticated path only) Applicant clicks the link
   → POST /auth/set-password/  →  password set, user.is_verified = True,
     application.email_verified_at = now()
   → THIS triggers step 3

3. (new) Every user holding the `partner_applications.review` capability is
   emailed: "New partner application ready for review: {applicant_name}"

4. Admin (or Volunteer, or whoever holds that capability) reviews it
   → GET /admin/partner-applications/
   → GET /admin/partner-applications/{id}/

5a. Approve
    → POST /admin/partner-applications/{id}/approve/   {"admin_role_id": 4}
    → applicant_user already exists by now, always — no create-or-match
      branching needed here anymore, unlike the previous draft of this plan.
    → grant admin_role_id to that user
    → if drop-off details were included: create a DropOffPoint, assign
      that user as its manager
    → email the applicant: approval notice

5b. Reject
    → POST /admin/partner-applications/{id}/reject/   {"reason": "..."}
    → status: rejected. The applicant's account is completely untouched —
      they keep normal platform access and can submit a fresh application
      later (the pending-only dedup constraint doesn't block reapplying
      once the old one is no longer pending).
```

This is a real simplification over the previous draft: because the account always exists by the
time an Admin reviews it, `approve` no longer has to decide whether to create one — it just grants
a role to a user that's already there.

---

## New app: `apps/partners/`

A new small domain app, matching the existing one-app-per-concept pattern (`apps/dropoff/`,
`apps/moderation/`, etc.) rather than bolting this onto an unrelated app.

### Model: `PartnerApplication`

```python
class PartnerApplication(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    # Always stored as submitted, even for an authenticated applicant — the
    # application is a stable historical record independent of later profile
    # edits (e.g. if they change their email afterward).
    applicant_name = models.CharField(max_length=200)
    applicant_email = models.EmailField()
    applicant_phone = models.CharField(max_length=32, blank=True)

    # Always set at creation time now, one way or the other — either to the
    # already-authenticated requester, or to a brand-new account created for
    # this submission. Never null once the row exists (unlike the previous
    # draft, where this stayed null until approval for new applicants).
    applicant_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="partner_applications"
    )

    organization_name = models.CharField(max_length=200, blank=True)
    message = models.TextField(blank=True)

    # Optional — present only if they're also offering a physical location.
    proposed_dropoff_name = models.CharField(max_length=200, blank=True)
    proposed_dropoff_address = models.CharField(max_length=300, blank=True)
    proposed_location = gis_models.PointField(null=True, blank=True, geography=True, srid=4326)

    # Set once the applicant confirms their email (immediately, for an
    # applicant who was already authenticated — see submission logic below).
    email_verified_at = models.DateTimeField(null=True, blank=True)
    # Set once reviewer_notified fires, so a retry/replay of the verification
    # click doesn't re-notify everyone a second time.
    reviewers_notified_at = models.DateTimeField(null=True, blank=True)

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    # Set on approval, for a clean audit trail of what this application actually produced.
    granted_role = models.ForeignKey(
        "accounts.AdminRole", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_dropoff_point = models.ForeignKey(
        "dropoff.DropOffPoint", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # Mirrors the existing Report dedup pattern (one open report per
            # reporter per target) — one pending application per email at a
            # time; a rejected one doesn't block reapplying later.
            models.UniqueConstraint(
                fields=["applicant_email"],
                condition=models.Q(status="pending"),
                name="one_pending_application_per_email",
            )
        ]
```

`applicant_user` changed from nullable (previous draft) to required, non-nullable — a direct
consequence of creating the account at submission instead of approval. `on_delete` changed from
`SET_NULL` to `CASCADE` to match (a null `applicant_user` on an existing row would no longer be a
valid state, so there's nothing sensible to leave behind if the user is ever deleted).

---

## Public endpoint

### `POST /partner-applications/` 🔓 (public — no auth required)

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
Required: `applicant_name`, `applicant_email`. Everything else optional — someone applying just to
volunteer generally (not offering a location) omits the `proposed_*` fields entirely (the
distinction between "wants a role," "wants to host a location," or both is resolved at
**approval** time by which role the Admin actually grants and whether they also create the
drop-off point — see [open questions](#open-questions) if you'd rather split these into genuinely
separate application types).

**Server-side logic:**

1. **If the request is authenticated:** `applicant_user = request.user`.
   `applicant_name`/`applicant_email`/`applicant_phone` are pre-filled from their account
   server-side (never trust a logged-in request to claim a different identity than the account
   making it — ignore/overwrite whatever the client sent for those three fields). Set
   `email_verified_at = now()` immediately — they're already logged in, which is itself proof of
   email ownership via however they originally verified (or via `is_verified` already being true
   on their account). Immediately notify reviewers (step below) — no wait needed.
2. **If not authenticated:** look up `User.objects.filter(email__iexact=applicant_email).first()`.
   - **If a matching account already exists** (someone with an account applying without bothering
     to log in first): use that account as `applicant_user`. If that account's own
     `is_verified` is already `True`, treat this the same as the authenticated path (verified
     immediately, notify reviewers now). If not, fall through to the verification-email step below
     using their existing account rather than creating a new one.
   - **If no account exists:** create one — `username` generated from the email locally-part +
     a uniqueness suffix if needed (e.g. `amara`, or `amara2` on collision), `email`,
     `first`/`last` split from `applicant_name` if you want that level of parity with `register`
     (optional), `role` left at its model default, `set_unusable_password()`. This is a completely
     ordinary account from that point on — nothing marks it as "pending partner review" at the
     `User` level, only the `PartnerApplication` row does.
   - Either way, send **one combined email**: verify your email address and set your password (a
     single link/flow, not two separate emails — see the `set-password` endpoint below).

`400`/`code: "duplicate_application"` if this email already has a pending application.

Response `201`: the created application (`status: "pending"`).

---

## Why email verification is still required (even though creation moved earlier)

Moving account creation to submission time doesn't remove the original spoofing concern — if
anything it sharpens it slightly, since now a spoofed submission immediately creates a real
account tied to someone else's email, not just a pending row. The mitigation is the same as
before: **`approve` requires `email_verified_at` to be set**, so nobody gets a role granted off an
unverified email regardless of when the account itself was created. This still wasn't part of your
original request — flagging it the same way as before, as a deliberate addition I'd lean toward
keeping rather than an assumption to quietly build in.

---

## Notifying reviewers

**Updated: routed through the general Notification feature, not a bespoke email-only function** —
see [`docs/NOTIFICATIONS_PLAN.md`](./NOTIFICATIONS_PLAN.md) for the full design (a persisted
`Notification` model + in-app list/unread-count/mark-read API, email as one delivery channel
alongside it, generalized beyond just this use case). What follows is this specific trigger.

### `notify_partner_application_ready(application)` in `apps/notifications/services.py`

Fires once `email_verified_at` gets set (either immediately, for the already-authenticated/
already-verified paths above, or after the applicant completes the combined verify+set-password
step). Guarded by `reviewers_notified_at` so it only ever fires once per application:

```python
def notify_partner_application_ready(application):
    if application.reviewers_notified_at is not None:
        return  # already sent — don't re-notify on a retry/replay

    reviewers = User.objects.filter(
        admin_role__capabilities__contains=["partner_applications.review"]
    )
    for reviewer in reviewers:
        notify(  # the shared dispatch function — creates a Notification row AND sends the email
            recipient=reviewer,
            category=Notification.Category.PARTNER_APPLICATION_READY,
            title=f"New partner application: {application.applicant_name}",
            body=f"{application.applicant_name} applied to become a partner. Review it at ...",
            target_type="partner_application",
            target_id=application.id,
        )
    application.reviewers_notified_at = timezone.now()
    application.save(update_fields=["reviewers_notified_at"])
```

Same synchronous, wrapped-in-try/except pattern as every other notification in this codebase — no
queue, and one failed send doesn't block the request. Sends to **every** current holder of
`partner_applications.review`, not just one designated admin, consistent with the plan treating
that as a capability multiple people can hold, not a single named role. Because it now goes
through `notify()`, reviewers also see this in their own in-app notification list, not only their
inbox — they don't have to rely on email alone to catch it.

*(If you end up with many reviewers, one notification per application per reviewer could get noisy —
a daily digest instead of per-application pings is a reasonable future improvement, not needed for
a first version.)*

---

## Admin endpoints

New capability: **`partner_applications.review`** (added to the vocabulary in
`docs/ADMIN_API_PLAN.md`).

### `GET /admin/partner-applications/` 🔒`partner_applications.review`

List/search/filter. Search: `applicant_name`, `applicant_email`, `organization_name`. Filter:
`status`. (The previous draft's `has_account` filter no longer makes sense — every application now
has an account by definition.)

### `GET /admin/partner-applications/{id}/` 🔒`partner_applications.review`

Full detail, including `email_verified_at` (the frontend disables the approve button until it's
set — though in practice, an application only reaches the reviewer's queue *after* verification
now, since that's what triggers the notification in the first place, so this should rarely if ever
show up unverified in the list at all).

### `POST /admin/partner-applications/{id}/approve/` 🔒`partner_applications.review`

```json
{
  "admin_role_id": 4,
  "assign_dropoff_manager": true
}
```
`admin_role_id` — **required**, the Admin picks which role to grant (no hardcoded "Partner" role
name, consistent with the rest of the admin plan). `assign_dropoff_manager` — defaults `true`; set
`false` to grant the role without also creating/assigning the proposed location.

**Server-side logic (simpler than the previous draft — no user resolution needed):**
1. `400`/`code: "email_not_verified"` if `email_verified_at` is null.
2. `400`/`code: "already_reviewed"` if `status != "pending"`.
3. Grant `admin_role_id` to `application.applicant_user` (reuse the `assign-role` service function
   directly, not a duplicate implementation).
4. If `proposed_dropoff_name`/`proposed_location` are present and `assign_dropoff_manager` is
   true: create a `DropOffPoint` from those fields, then reuse the `assign-managers` logic to add
   `applicant_user` as its manager.
5. Update the application: `status=approved`, `granted_role`, `created_dropoff_point`,
   `reviewed_by`, `reviewed_at`.
6. `record_audit_log(action="partner_application_approved", ...)`.
7. Email the applicant a plain approval notice — no account-setup link needed anymore, since
   they've already had one since submission.

### `POST /admin/partner-applications/{id}/reject/` 🔒`partner_applications.review`

```json
{ "reason": "We don't currently have coverage in that area." }
```
`status=rejected`, `rejection_reason` stored, `AuditLog` entry, applicant emailed the reason.
**Nothing happens to their account** — per your requirement, they keep it and can use the platform
normally, and can submit a new application later once this one is no longer `pending`.

---

## New dependency this plan surfaces: a password-set/invite flow

An account created with `set_unusable_password()` needs a way for that person to actually set a
real password — **this doesn't exist yet** in the current auth endpoints (only
`register`/`login`/`refresh`/`logout`). Needed alongside this feature, and now doing double duty
as the email-verification step too (one link, one action, not two):

### `POST /auth/set-password/` 🔓 (public — the token itself is the auth)

```json
{ "uid": "MTIz", "token": "abc123-...", "new_password": "NewSecurePassword!" }
```
Standard Django idiom, reusing what's already in the framework rather than inventing new crypto:
`uid` is `urlsafe_base64_encode(force_bytes(user.pk))`, `token` is generated by Django's built-in
`django.contrib.auth.tokens.PasswordResetTokenGenerator` (already available, no new package).
Server-side, on success: sets the new password, sets `user.is_verified = True`, and — if there's a
`PartnerApplication` with `applicant_user=user` and `email_verified_at IS NULL` — sets
`email_verified_at = now()` and calls `notify_partner_application_ready()`. `400` on an
invalid/expired/already-used token.

*(This same endpoint doubles as the foundation for a normal "forgot password" flow later, if that
doesn't already exist — worth checking before building, since it'd be wasteful to build it twice
under two different names. If a general password-reset flow already exists or gets built first,
this partner-application flow should just call into it rather than defining its own copy.)*

---

## Open questions

- **Is email verification wanted, given it wasn't in the original request?** Still flagged, same
  reasoning as before — moving account creation earlier didn't remove the underlying spoofing
  concern, if anything it made an unverified spoof slightly more consequential (a real account now
  exists, not just a pending row). I'd lean toward keeping it.
- **One combined form vs. two application types.** Unchanged from the previous draft — this plan
  assumes one form with optional drop-off fields, resolved at approval time by what the Admin
  actually grants. Say so if you want two genuinely separate application types instead.
- **Should an applicant be able to check their own application's status?** Now straightforward to
  add, since they always have an account by submission time: `GET /partner-applications/mine/`
  (authenticated). Worth including from the start given accounts always exist now — say if you
  want this in scope.
- **Does `password-set` already need to exist for something else** (e.g. a plain "forgot my
  password" feature)? If so, build that first as its own thing and this flow just reuses it.
- **Username generation for a new account** — the plan above generates one from the email's local
  part with a numeric-suffix fallback on collision, since the public `register` endpoint requires
  a username and this flow never collects one. Flag if you'd rather ask for a username on the
  form, or generate it differently.

Happy to start on this once the underlying role/capability system from `ADMIN_API_PLAN.md` Phase 1
is in place — this depends on it directly (`admin_role_id`, `assign-role`, `assign-managers` are
all reused here, not reimplemented).
