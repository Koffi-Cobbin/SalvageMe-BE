import pytest
from pytest_factoryboy import register
from rest_framework.test import APIClient

from tests.factories import (
    AdminRoleFactory,
    AuditLogFactory,
    BookRequestFactory,
    CategoryFactory,
    DropOffPointFactory,
    ExchangeFactory,
    ListingFactory,
    ListingPhotoFactory,
    PartnerApplicationFactory,
    ReportFactory,
    UserFactory,
    UserRatingFactory,
)

register(UserFactory)
register(AdminRoleFactory)
register(CategoryFactory)
register(ListingFactory)
register(ListingPhotoFactory)
register(BookRequestFactory)
register(ExchangeFactory)
register(DropOffPointFactory)
register(ReportFactory)
register(AuditLogFactory)
register(UserRatingFactory)
register(PartnerApplicationFactory)


@pytest.fixture(autouse=True)
def _clear_cache():
    """
    Django's LocMemCache (see CACHES in settings) persists across tests
    within the same process — without this, tests that write to the
    impact-stats cache key (or any future cache usage) leak state into
    unrelated tests run later in the same session.
    """
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def auth_client(api_client, user_factory):
    def _make(user=None, **kwargs):
        user = user or user_factory(**kwargs)
        api_client.force_authenticate(user=user)
        return api_client, user

    return _make
