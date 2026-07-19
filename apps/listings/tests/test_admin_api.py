import pytest
from django.urls import reverse

from apps.listings.models import Listing

pytestmark = pytest.mark.django_db


class TestAdminListingViewSet:
    def test_list_requires_capability(self, auth_client, listing_factory):
        client, user = auth_client(username="noview")
        response = client.get(reverse("admin-listing-list"))
        assert response.status_code == 403

    def test_list_includes_removed(self, auth_client, admin_role_factory, listing_factory):
        role = admin_role_factory(capabilities=["listings.view"])
        client, user = auth_client(admin_role=role)
        listing_factory(status=Listing.Status.REMOVED)
        listing_factory(status=Listing.Status.AVAILABLE)
        response = client.get(reverse("admin-listing-list"))
        assert len(response.data["results"]) == 2

    def test_remove_requires_capability(self, auth_client, admin_role_factory, listing_factory):
        role = admin_role_factory(capabilities=["listings.view"])
        client, user = auth_client(admin_role=role)
        listing = listing_factory()
        response = client.post(reverse("admin-listing-remove", args=[listing.id]))
        assert response.status_code == 403

    def test_remove_success(self, auth_client, admin_role_factory, listing_factory):
        role = admin_role_factory(capabilities=["listings.view", "listings.remove_restore"])
        client, user = auth_client(admin_role=role)
        listing = listing_factory()
        response = client.post(reverse("admin-listing-remove", args=[listing.id]))
        assert response.status_code == 200
        listing.refresh_from_db()
        assert listing.status == Listing.Status.REMOVED

    def test_restore_success(self, auth_client, admin_role_factory, listing_factory):
        role = admin_role_factory(capabilities=["listings.view", "listings.remove_restore"])
        client, user = auth_client(admin_role=role)
        listing = listing_factory(status=Listing.Status.REMOVED)
        response = client.post(reverse("admin-listing-restore", args=[listing.id]))
        assert response.status_code == 200
        listing.refresh_from_db()
        assert listing.status == Listing.Status.AVAILABLE

    def test_restore_pending_listing_rejected(self, auth_client, admin_role_factory, listing_factory):
        role = admin_role_factory(capabilities=["listings.view", "listings.remove_restore"])
        client, user = auth_client(admin_role=role)
        listing = listing_factory(status=Listing.Status.PENDING)
        response = client.post(reverse("admin-listing-restore", args=[listing.id]))
        assert response.status_code == 400

    def test_delete_photo_requires_capability(self, auth_client, admin_role_factory, listing_photo_factory):
        role = admin_role_factory(capabilities=["listings.view"])
        client, user = auth_client(admin_role=role)
        photo = listing_photo_factory()
        response = client.delete(
            f"/api/v1/admin/listings/{photo.listing_id}/photos/{photo.id}/"
        )
        assert response.status_code == 403

    def test_delete_photo_success(self, auth_client, admin_role_factory, listing_photo_factory, mocker):
        role = admin_role_factory(capabilities=["listings.view", "listings.delete_photo"])
        client, user = auth_client(admin_role=role)
        photo = listing_photo_factory()
        mocker.patch("apps.listings.services.get_fileforge_client")
        response = client.delete(
            f"/api/v1/admin/listings/{photo.listing_id}/photos/{photo.id}/"
        )
        assert response.status_code == 204


class TestAdminCategoryViewSet:
    def test_requires_capability(self, auth_client, category_factory):
        client, user = auth_client(username="nocat")
        response = client.get(reverse("admin-category-list"))
        assert response.status_code == 403

    def test_create_success(self, auth_client, admin_role_factory):
        role = admin_role_factory(capabilities=["categories.manage"])
        client, user = auth_client(admin_role=role)
        response = client.post(reverse("admin-category-list"), {"name": "Poetry"})
        assert response.status_code == 201
        assert response.data["slug"] == "poetry"

    def test_delete_in_use_rejected(self, auth_client, admin_role_factory, category_factory, listing_factory):
        role = admin_role_factory(capabilities=["categories.manage"])
        client, user = auth_client(admin_role=role)
        category = category_factory()
        listing_factory(category=category)
        response = client.delete(reverse("admin-category-detail", args=[category.id]))
        assert response.status_code == 400

    def test_delete_unused_success(self, auth_client, admin_role_factory, category_factory):
        role = admin_role_factory(capabilities=["categories.manage"])
        client, user = auth_client(admin_role=role)
        category = category_factory()
        response = client.delete(reverse("admin-category-detail", args=[category.id]))
        assert response.status_code == 204
