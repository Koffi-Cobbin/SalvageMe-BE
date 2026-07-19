from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models import Q

from .models import ImpactStatsSnapshot

IMPACT_STATS_CACHE_KEY = "impact_stats"
IMPACT_STATS_CACHE_TTL_SECONDS = 60 * 60 * 24  # 24h — refreshed by the daily job anyway


def recompute_impact_stats() -> ImpactStatsSnapshot:
    """
    Called by the daily `run_daily_jobs` management command. Writes a new
    ImpactStatsSnapshot row and refreshes the cache entry that
    /api/stats/impact/ reads from.
    """
    from django.contrib.auth import get_user_model

    from apps.exchanges.models import Exchange
    from apps.listings.models import Listing

    User = get_user_model()

    snapshot = ImpactStatsSnapshot.objects.create(
        total_listings=Listing.objects.exclude(status=Listing.Status.REMOVED).count(),
        total_exchanges_completed=Exchange.objects.filter(status=Exchange.Status.COMPLETED).count(),
        total_active_donors=User.objects.filter(
            Q(role=User.Role.DONOR) | Q(role=User.Role.BOTH), listings__isnull=False
        ).distinct().count(),
        total_active_recipients=User.objects.filter(
            Q(role=User.Role.RECIPIENT) | Q(role=User.Role.BOTH), sent_requests__isnull=False
        ).distinct().count(),
    )

    cache.set(IMPACT_STATS_CACHE_KEY, snapshot, IMPACT_STATS_CACHE_TTL_SECONDS)
    return snapshot


def get_cached_impact_stats() -> ImpactStatsSnapshot | None:
    snapshot = cache.get(IMPACT_STATS_CACHE_KEY)
    if snapshot is not None:
        return snapshot

    snapshot = ImpactStatsSnapshot.objects.order_by("-computed_at").first()
    if snapshot is not None:
        cache.set(IMPACT_STATS_CACHE_KEY, snapshot, IMPACT_STATS_CACHE_TTL_SECONDS)
    return snapshot


def get_dashboard_summary() -> dict:
    """
    Called by GET /admin/dashboard/ — small, hand-picked set of counts for
    an admin landing page. Deliberately not the same as ImpactStatsSnapshot
    (which is public-facing, cached, and recomputed daily); this is
    computed fresh on every call since it's admin-only and low-traffic.
    """
    from django.utils import timezone

    from apps.exchanges.models import Exchange
    from apps.listings.models import Listing
    from apps.moderation.models import Report
    from apps.requests.models import BookRequest

    User = get_user_model()

    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)

    return {
        "open_reports_count": Report.objects.filter(status=Report.Status.OPEN).count(),
        "pending_requests_count": BookRequest.objects.filter(status=BookRequest.Status.PENDING).count(),
        "unverified_users_count": User.objects.filter(is_verified=False).count(),
        "listings_created_today": Listing.objects.filter(created_at__gte=today_start).count(),
        "scheduled_exchanges_count": Exchange.objects.filter(status=Exchange.Status.SCHEDULED).count(),
    }
