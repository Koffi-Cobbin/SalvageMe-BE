import pytest
from pytest_factoryboy import register
from rest_framework.test import APIClient

from tests.factories import (
    AuditLogFactory,
    BookRequestFactory,
    CategoryFactory,
    DropOffPointFactory,
    ExchangeFactory,
    ListingFactory,
    ListingPhotoFactory,
    ReportFactory,
    UserFactory,
    UserRatingFactory,
)

register(UserFactory)
register(CategoryFactory)
register(ListingFactory)
register(ListingPhotoFactory)
register(BookRequestFactory)
register(ExchangeFactory)
register(DropOffPointFactory)
register(ReportFactory)
register(AuditLogFactory)
register(UserRatingFactory)


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
