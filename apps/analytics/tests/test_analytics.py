import pytest
from django.urls import reverse

from apps.analytics import services

pytestmark = pytest.mark.django_db


def test_impact_stats_endpoint_is_public_and_computes_on_first_call(api_client, listing_factory):
    listing_factory.create_batch(3)
    response = api_client.get(reverse("impact-stats"))
    assert response.status_code == 200
    assert response.data["total_listings"] == 3


def test_recompute_impact_stats_counts_completed_exchanges(exchange_factory):
    exchange_factory(status="completed")
    exchange_factory(status="scheduled")
    snapshot = services.recompute_impact_stats()
    assert snapshot.total_exchanges_completed == 1


def test_get_cached_impact_stats_uses_cache(exchange_factory):
    services.recompute_impact_stats()
    from django.core.cache import cache

    assert cache.get(services.IMPACT_STATS_CACHE_KEY) is not None
    snapshot = services.get_cached_impact_stats()
    assert snapshot is not None
