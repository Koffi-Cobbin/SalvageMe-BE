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
