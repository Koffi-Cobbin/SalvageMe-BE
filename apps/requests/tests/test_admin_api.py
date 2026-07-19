import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


class TestAdminBookRequestViewSet:
    def test_requires_capability(self, auth_client, book_request_factory):
        client, user = auth_client(username="noreqview")
        response = client.get(reverse("admin-request-list"))
        assert response.status_code == 403

    def test_returns_all_requests(self, auth_client, admin_role_factory, book_request_factory):
        role = admin_role_factory(capabilities=["requests.view"])
        client, user = auth_client(admin_role=role)
        book_request_factory.create_batch(3)
        response = client.get(reverse("admin-request-list"))
        assert len(response.data["results"]) == 3
