"""
Service-layer functions for the public leaderboard — see
docs/LEADERBOARD_PLAN.md. Computed live on every call, not cached/
snapshotted like ImpactStatsSnapshot — freshness matters more here, and
the aggregate query is cheap at this project's scale. If that ever
changes, wrapping the result in django.core.cache with a short TTL is a
small, isolated addition — nothing about the API shape needs to change.
"""
from __future__ import annotations

from django.db.models import Avg, Count, F, Q
from django.utils import timezone

from common.hero_tiers import get_hero_tier

VALID_PERIODS = ("all_time", "this_month")


def _start_of_current_month():
    now = timezone.now()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _completed_exchanges_queryset(period: str):
    from apps.exchanges.models import Exchange

    if period not in VALID_PERIODS:
        from rest_framework.exceptions import ValidationError

        raise ValidationError(
            {"detail": f"Invalid period '{period}'. Must be one of {VALID_PERIODS}.", "code": "invalid_period"}
        )

    queryset = Exchange.objects.filter(status=Exchange.Status.COMPLETED)
    if period == "this_month":
        queryset = queryset.filter(completed_at__gte=_start_of_current_month())
    return queryset.exclude(donor__include_in_leaderboard=False)


def _average_ratings_by_donor(donor_ids: list[int]) -> dict[int, float]:
    """
    Average rating received specifically *as donor* — a UserRating row
    doesn't distinguish which side it was given from (see
    docs/LEADERBOARD_PLAN.md "Open questions"), so this filters to ratings
    tied to an exchange where this same person was the donor.
    """
    from apps.accounts.models import UserRating

    rows = (
        UserRating.objects.filter(rated_user_id__in=donor_ids, exchange__donor_id=F("rated_user_id"))
        .values("rated_user_id")
        .annotate(avg_score=Avg("score"))
    )
    return {row["rated_user_id"]: round(row["avg_score"], 2) for row in rows}


def get_leaderboard(*, period: str = "all_time", limit: int = 20) -> dict:
    limit = max(1, min(limit, 100))

    ranked = (
        _completed_exchanges_queryset(period)
        .values("donor_id", "donor__username", "donor__avatar_url")
        .annotate(completed_donation_count=Count("id"))
        .order_by("-completed_donation_count", "donor_id")[:limit]
    )
    ranked = list(ranked)
    donor_ids = [row["donor_id"] for row in ranked]
    avg_ratings = _average_ratings_by_donor(donor_ids)

    results = []
    for rank, row in enumerate(ranked, start=1):
        count = row["completed_donation_count"]
        results.append(
            {
                "rank": rank,
                "username": row["donor__username"],
                "avatar_url": row["donor__avatar_url"],
                "completed_donation_count": count,
                "average_rating": avg_ratings.get(row["donor_id"]),
                "hero_tier": get_hero_tier(count),
            }
        )
    return {"period": period, "results": results}


def get_my_leaderboard_rank(*, user, period: str = "all_time") -> dict:
    """
    Your own rank, even outside the top N — computed by counting how many
    *other* donors have a strictly higher completed-donation count than
    you, rather than materializing the full ranking. Correct at any scale
    without needing an OFFSET-style full ordered scan.
    """
    queryset = _completed_exchanges_queryset(period)

    my_count = queryset.filter(donor=user).count()

    if my_count == 0:
        return {
            "rank": None,
            "username": user.username,
            "completed_donation_count": 0,
            "average_rating": None,
            "hero_tier": None,
        }

    donors_ahead = (
        queryset.exclude(donor=user)
        .values("donor_id")
        .annotate(count=Count("id"))
        .filter(count__gt=my_count)
        .count()
    )

    avg_ratings = _average_ratings_by_donor([user.id])

    return {
        "rank": donors_ahead + 1,
        "username": user.username,
        "completed_donation_count": my_count,
        "average_rating": avg_ratings.get(user.id),
        "hero_tier": get_hero_tier(my_count),
    }


def get_active_featured_donors(at=None):
    """Currently-active FeaturedDonor entries, for the public spotlight endpoint."""
    from django.utils import timezone

    from .models import FeaturedDonor

    at = at or timezone.now()
    return (
        FeaturedDonor.objects.filter(featured_from__lte=at)
        .filter(Q(featured_until__isnull=True) | Q(featured_until__gte=at))
        .select_related("user")
    )


def create_featured_donor(*, user, blurb: str, featured_from, featured_until, acting_user):
    """
    Admin-only (gated by leaderboard.manage at the view layer). Refuses to
    feature someone who's opted out of the leaderboard entirely — the
    whole point of that opt-out is "don't put me on public donor
    displays," and a spotlight is exactly that, just editorial rather than
    algorithmic. See docs/LEADERBOARD_PLAN.md "Privacy".
    """
    from rest_framework.exceptions import ValidationError

    from .models import FeaturedDonor

    if not user.include_in_leaderboard:
        raise ValidationError(
            {
                "detail": "This user has opted out of the public leaderboard and cannot be featured.",
                "code": "user_opted_out",
            }
        )

    entry = FeaturedDonor.objects.create(
        user=user,
        blurb=blurb,
        featured_from=featured_from,
        featured_until=featured_until,
        created_by=acting_user,
    )

    from apps.moderation.services import record_audit_log

    record_audit_log(
        actor=acting_user, action="donor_featured", target_type="user", target_id=user.id,
        metadata={"featured_donor_id": entry.id, "featured_from": str(featured_from), "featured_until": str(featured_until)},
    )
    return entry


def remove_featured_donor(*, entry, acting_user):
    from apps.moderation.services import record_audit_log

    entry_id, user_id = entry.id, entry.user_id
    entry.delete()

    record_audit_log(
        actor=acting_user, action="donor_unfeatured", target_type="user", target_id=user_id,
        metadata={"featured_donor_id": entry_id},
    )
