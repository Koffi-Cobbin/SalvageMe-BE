import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


class TestAdminUserRatingViewSet:
    def test_requires_capability(self, auth_client, user_rating_factory):
        client, user = auth_client(username="noratingview")
        response = client.get(reverse("admin-rating-list"))
        assert response.status_code == 403

    def test_returns_all_ratings(self, auth_client, admin_role_factory, user_rating_factory):
        role = admin_role_factory(capabilities=["ratings.view"])
        client, user = auth_client(admin_role=role)
        user_rating_factory.create_batch(2)
        response = client.get(reverse("admin-rating-list"))
        assert len(response.data["results"]) == 2
