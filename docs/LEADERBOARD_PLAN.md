# Leaderboard / Heroes — Plan

A public feature recognizing top donors — a ranked list plus a lightweight "Hero" tier system,
grounded in real completed exchanges already tracked in this codebase (`Exchange`, `UserRating`).
**Design document, not yet implemented.**

---

## What "counts," and why

The obvious metric is **completed donations**: how many `Exchange` rows a user appears on as
`donor` with `status=completed`. This is already a real, existing signal — no new tracking needed,
and it's inherently hard to fake trivially: `apps/requests/services.py::create_request` already
blocks requesting your own listing, so a completed exchange means two distinct accounts actually
went through the request → accept → schedule → complete flow.

**Two numbers, not one**, since count alone rewards volume over quality:

- **Primary: completed-donation count** — the headline leaderboard ranking.
- **Secondary: average rating received as a donor** — pulled from `UserRating` where
  `rated_user=<donor>` and the associated `exchange.donor_id == <donor>.id` (a `UserRating` row
  doesn't currently distinguish "rated as donor" vs "rated as recipient," since the same model
  covers both directions — see [Open questions](#open-questions)). Shown alongside the count, and
  used as a tiebreaker, not the primary sort — a donor with one 5-star exchange shouldn't outrank
  one with fifty 4.8-star exchanges.

---

## "Hero" tiers — thresholds, not a new model

A simple, code-defined threshold table (same pattern as `common/admin_capabilities.py` — a fixed
vocabulary in code, not database rows), derived from the count above rather than stored anywhere:

```python
# common/hero_tiers.py
HERO_TIERS = [
    (1, "Contributor"),
    (5, "Hero"),
    (15, "Champion"),
    (50, "Legend"),
]

def get_hero_tier(completed_donation_count: int) -> str | None:
    tier = None
    for threshold, name in HERO_TIERS:
        if completed_donation_count >= threshold:
            tier = name
    return tier  # None if below the first threshold (1) — i.e. zero completed donations
```

No new model, no admin-configurable thresholds for v1 — these are meant to be tuned by editing
this one small file, not a runtime-configurable system like the capability roles. Flag if you'd
rather these be admin-editable from the start (see [Open questions](#open-questions)); it's a
reasonable escalation later, but a fixed table is simpler to ship first and tune once you see real
distribution of donation counts.

---

## Data model: computed live, not a new persisted table

Unlike `ImpactStatsSnapshot` (which exists because *aggregate platform-wide* counts are cheap to
cache once and expensive to feel out on every page load across many users), a leaderboard is a
`GROUP BY donor_id, COUNT(*), ORDER BY count DESC LIMIT N` query — cheap even at meaningful scale,
and needs to reflect fresh data (someone hitting "Hero" status should show up promptly, not wait
for a nightly job). **Proposal: compute it live on every request, no new table.**

```python
# apps/accounts/services.py (new file — this app doesn't have one yet, only admin_services.py)
def get_leaderboard(*, period: str = "all_time", limit: int = 20) -> list[dict]:
    from django.db.models import Avg, Count, Q

    from apps.exchanges.models import Exchange

    exchanges = Exchange.objects.filter(status=Exchange.Status.COMPLETED)
    if period == "this_month":
        exchanges = exchanges.filter(completed_at__gte=start_of_current_month())

    ranked = (
        exchanges.exclude(donor__include_in_leaderboard=False)  # see opt-out below
        .values("donor_id", "donor__username", "donor__avatar_url")
        .annotate(completed_donation_count=Count("id"))
        .order_by("-completed_donation_count")[:limit]
    )
    # average rating pulled in a second query per result, or a subquery —
    # implementation detail, not a design decision worth locking in here.
    return list(ranked)
```

If this ever *does* need caching (e.g. once the platform is large enough that the aggregate query
shows up in slow-query logs), it's a small addition — wrap the result in `django.core.cache` with
a short TTL (minutes, not the 24h `ImpactStatsSnapshot` uses), since freshness matters more here
than for platform-wide totals. Not needed to ship v1.

---

## Privacy: an opt-out, flagged proactively

This wasn't part of your request, but worth raising before shipping, same as the email-verification
point in the partner-application plan: **being featured on a public leaderboard is a visibility
choice, not everyone wants it**, even for something positive. A donor might have good reasons to
not want their username and donation activity surfaced on a public page (safety, personal
preference, an organization donating anonymously). Proposal: a new `User.include_in_leaderboard`
boolean field, **default `True`** (opt-out, not opt-in — most people are fine being recognized for
donating, and opt-in would likely leave the leaderboard nearly empty), toggleable via the existing
`PATCH /users/me/`. Excluded from the ranking query as shown above. Flag if you'd rather default
this the other way, or skip the field entirely.

**What's already safe by construction, reusing existing patterns:** leaderboard entries only ever
expose `username`/`avatar_url`/counts — never phone/location/email, the same
`PublicUserSerializer`-style boundary already enforced everywhere else in this API (see
`API_REFERENCE.md` → [Contact/location privacy](../API_REFERENCE.md#contactlocation-privacy)).
Nothing new to get wrong here, just reusing the existing boundary.

---

## API

### `GET /leaderboard/` 🔓 (public)

Query params: `?period=all_time` (default) or `?period=this_month`. `?limit=20` (default,
capped at 100 — this is a "top N" endpoint, not a paginated list of every donor).

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
`hero_tier` is `null` for anyone below the first threshold — such a user wouldn't typically appear
in a top-20 list anyway, but is possible with a small `limit` on a low-activity instance.

### `GET /leaderboard/me/` 🔒

The nice UX touch a top-N list alone can't give you: **your own rank even when you're not in the
top N.** No query params beyond the same `?period=`.

Response `200`:
```json
{
  "rank": 47,
  "username": "donor_felix",
  "completed_donation_count": 3,
  "average_rating": 5.0,
  "hero_tier": "Contributor"
}
```
`rank: null` if you have zero completed donations (not ranked at all, rather than a misleading
"last place" number) — the frontend can show a "make your first donation to join the leaderboard"
prompt in that case instead of a number.

---

## Admin tie-in: featuring/excluding (new capability)

Two admin-only powers worth having from day one, both reusing the [role/capability
system](./ADMIN_API_PLAN.md#2-roles--access-control) already built — new capability
`leaderboard.manage`, added to the vocabulary in `common/admin_capabilities.py`:

- **Exclude a specific user from the public leaderboard** without suspending their account
  entirely — e.g. a flagged-but-not-yet-resolved account, or a request from the user themselves
  handled on their behalf. This is really just staff being able to set the same
  `include_in_leaderboard` field described above on someone else's account
  (`PATCH /admin/users/{id}/` already exists — just add `include_in_leaderboard` to that
  serializer's writable fields, gated by the existing `users.edit` capability; **no new admin
  endpoint needed** for this half).
- **Editorially feature/spotlight a donor** with a short curated blurb — e.g. a homepage "Donor of
  the Month" card that's a human pick, not purely algorithmic. This *is* new: a small
  `FeaturedDonor` model (`user`, `blurb`, `featured_from`, `featured_until`, `created_by`) and
  `GET /leaderboard/featured/` (public) + `POST/DELETE /admin/leaderboard/featured/` (admin,
  `leaderboard.manage`). Flagging this as an optional add-on, not core to "leaderboard" — say if
  you want it in v1 or would rather keep the first version purely algorithmic.

---

## Anti-gaming: known limitation, not solved here

Worth naming plainly rather than implying this is airtight: two colluding accounts could inflate
a donation count by creating throwaway listings and completing fake exchanges between themselves.
This is a known risk class for *any* peer-to-peer reputation/leaderboard system, not specific to
this design, and this plan doesn't attempt automated fraud detection. What's already in place and
does help: `create_request` blocks self-requesting your own listing (so it takes two distinct
accounts, not one), and the existing [reporting system](../API_REFERENCE.md#reports) gives users a
way to flag suspicious activity, which staff can act on manually (e.g. excluding an account from
the leaderboard via the toggle above) while a fuller investigation happens. If gaming turns out to
be a real problem in practice, that's a good trigger for revisiting this section specifically,
rather than something to over-engineer against speculatively now.

---

## Open questions

- **Does a `UserRating` need to record which "side" it was given from?** Right now the model
  doesn't distinguish "rated as donor" from "rated as recipient" — `rate_exchange()` just rates
  "the other party," so a donor's average rating (as computed above) is technically "average
  rating received across all exchanges where this person happened to be the donor," which is
  correct but slightly indirect. Fine as-is for v1; flagging in case you want a cleaner
  `UserRating.rated_as` field for other reasons later.
- **Opt-out default** (`include_in_leaderboard=True` by default) — confirm this is the right
  default, per the privacy note above.
- **Hero tier thresholds and names** — the four-tier table above (`Contributor`/`Hero`/
  `Champion`/`Legend` at 1/5/15/50) is a starting guess with no data behind it yet. Easy to tune
  once you see real donation-count distribution after launch; not worth guessing precisely now.
- **Featured/curated spotlight** (`FeaturedDonor`) — in scope for v1, or a later addition once the
  algorithmic leaderboard is live and you know whether editorial curation is actually wanted?
- **`period` values** — this plan proposes `all_time` and `this_month`. A rolling window (e.g.
  "last 30 days") is a small variation if that fits better than calendar-month resets.

Happy to start implementing once these are confirmed — this one's simpler than the admin/partner
work (no new state machine, no account-creation edge cases), mostly a couple of read endpoints and
one small opt-out field.
