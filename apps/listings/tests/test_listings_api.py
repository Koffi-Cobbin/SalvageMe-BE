import pytest
from django.contrib.gis.geos import Point
from django.urls import reverse

from apps.listings.models import Listing

pytestmark = pytest.mark.django_db


class TestListListings:
    def test_list_is_public(self, api_client, listing_factory):
        listing_factory.create_batch(3)
        response = api_client.get(reverse("listing-list"))
        assert response.status_code == 200
        assert len(response.data["results"]) == 3

    def test_list_hides_non_available_from_public(self, api_client, listing_factory):
        listing_factory(status=Listing.Status.AVAILABLE)
        listing_factory(status=Listing.Status.CLAIMED)
        response = api_client.get(reverse("listing-list"))
        assert response.status_code == 200
        assert len(response.data["results"]) == 1

    def test_filter_by_category(self, api_client, listing_factory, category_factory):
        cat_a = category_factory(name="Math")
        cat_b = category_factory(name="Science")
        listing_factory(category=cat_a)
        listing_factory(category=cat_b)
        response = api_client.get(reverse("listing-list"), {"category": cat_a.slug})
        assert response.status_code == 200
        assert len(response.data["results"]) == 1

    def test_search_by_query(self, api_client, listing_factory):
        listing_factory(title="Algebra Basics")
        listing_factory(title="Chemistry 101")
        response = api_client.get(reverse("listing-list"), {"q": "algebra"})
        assert len(response.data["results"]) == 1

    def test_near_radius_filters_and_orders_by_distance(self, api_client, listing_factory):
        # London
        near = listing_factory(location=Point(-0.1276, 51.5072, srid=4326))
        # New York — far away
        far = listing_factory(location=Point(-74.0060, 40.7128, srid=4326))
        response = api_client.get(
            reverse("listing-list"), {"near": "51.5072,-0.1276", "radius": "50"}
        )
        assert response.status_code == 200
        ids = [item["id"] for item in response.data["results"]]
        assert near.id in ids
        assert far.id not in ids

    def test_owner_can_see_own_pending_listing(self, auth_client, listing_factory):
        client, user = auth_client(username="owner1")
        listing_factory(owner=user, status=Listing.Status.PENDING)
        response = client.get(reverse("listing-list"))
        assert len(response.data["results"]) == 1


class TestCreateListing:
    def test_create_requires_auth(self, api_client, category_factory):
        category = category_factory()
        response = api_client.post(
            reverse("listing-list"),
            {"title": "New book", "description": "desc", "category": category.id, "condition": "good"},
        )
        assert response.status_code == 401

    def test_create_success(self, auth_client, category_factory):
        client, user = auth_client(username="creator")
        category = category_factory()
        response = client.post(
            reverse("listing-list"),
            {
                "title": "New book",
                "description": "desc",
                "category": category.id,
                "condition": "good",
                "latitude": 51.5072,
                "longitude": -0.1276,
            },
        )
        assert response.status_code == 201
        assert response.data["title"] == "New book"
        assert response.data["owner"]["username"] == "creator"
        assert response.data["status"] == "available"

    def test_create_missing_required_field_rejected(self, auth_client, category_factory):
        client, user = auth_client(username="creator2")
        category = category_factory()
        response = client.post(reverse("listing-list"), {"description": "desc", "category": category.id})
        assert response.status_code == 400

    def test_status_field_not_writable_on_create(self, auth_client, category_factory):
        client, user = auth_client(username="creator3")
        category = category_factory()
        response = client.post(
            reverse("listing-list"),
            {
                "title": "Sneaky",
                "description": "desc",
                "category": category.id,
                "condition": "good",
                "status": "claimed",
            },
        )
        assert response.status_code == 201
        assert response.data["status"] == "available"


class TestUpdateDeleteListing:
    def test_update_by_non_owner_rejected(self, auth_client, listing_factory):
        listing = listing_factory()
        client, user = auth_client(username="stranger")
        response = client.patch(reverse("listing-detail", args=[listing.id]), {"title": "Hijacked"})
        assert response.status_code == 403

    def test_update_by_owner_success(self, auth_client, listing_factory):
        client, user = auth_client(username="owner2")
        listing = listing_factory(owner=user)
        response = client.patch(reverse("listing-detail", args=[listing.id]), {"title": "Updated title"})
        assert response.status_code == 200
        assert response.data["title"] == "Updated title"

    def test_patch_cannot_set_status_directly(self, auth_client, listing_factory):
        client, user = auth_client(username="owner3")
        listing = listing_factory(owner=user)
        response = client.patch(reverse("listing-detail", args=[listing.id]), {"status": "claimed"})
        assert response.status_code == 200
        listing.refresh_from_db()
        assert listing.status == Listing.Status.AVAILABLE

    def test_delete_by_owner_soft_deletes(self, auth_client, listing_factory):
        client, user = auth_client(username="owner4")
        listing = listing_factory(owner=user)
        response = client.delete(reverse("listing-detail", args=[listing.id]))
        assert response.status_code == 204
        listing.refresh_from_db()
        assert listing.status == Listing.Status.REMOVED

    def test_delete_by_non_owner_rejected(self, auth_client, listing_factory):
        listing = listing_factory()
        client, user = auth_client(username="stranger2")
        response = client.delete(reverse("listing-detail", args=[listing.id]))
        assert response.status_code == 403


class TestListingPhotos:
    def test_upload_photo_by_owner_success(self, auth_client, listing_factory, mocker):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from common.fileforge_client import FileForgeUploadResult

        client, user = auth_client(username="photoowner")
        listing = listing_factory(owner=user)

        mock_client = mocker.patch("apps.listings.services.get_fileforge_client").return_value
        mock_client.upload_file.return_value = FileForgeUploadResult(file_id=99, url="https://cdn/99.jpg")

        photo_file = SimpleUploadedFile("cover.jpg", b"fake-bytes", content_type="image/jpeg")
        response = client.post(
            reverse("listing-photos", args=[listing.id]), {"file": photo_file}, format="multipart"
        )
        assert response.status_code == 201
        assert response.data["url"] == "https://cdn/99.jpg"

    def test_upload_photo_by_non_owner_rejected(self, auth_client, listing_factory):
        from django.core.files.uploadedfile import SimpleUploadedFile

        listing = listing_factory()
        client, user = auth_client(username="notowner")
        photo_file = SimpleUploadedFile("cover.jpg", b"fake-bytes", content_type="image/jpeg")
        response = client.post(
            reverse("listing-photos", args=[listing.id]), {"file": photo_file}, format="multipart"
        )
        assert response.status_code == 403

    def test_upload_photo_missing_file_rejected(self, auth_client, listing_factory):
        client, user = auth_client(username="photoowner2")
        listing = listing_factory(owner=user)
        response = client.post(reverse("listing-photos", args=[listing.id]), {}, format="multipart")
        assert response.status_code == 400
