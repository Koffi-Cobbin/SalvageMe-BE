from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.listings.services import (
    PhotoValidationError,
    add_listing_photo,
    delete_listing_photo,
    reconcile_pending_photos,
    validate_uploaded_photo,
)
from common.fileforge_client import FileForgeError, FileForgeUploadResult

pytestmark = pytest.mark.django_db


def make_image_file(name="cover.jpg", content_type="image/jpeg", size=10):
    return SimpleUploadedFile(name, b"x" * size, content_type=content_type)


class TestValidateUploadedPhoto:
    def test_rejects_bad_content_type(self):
        f = make_image_file(content_type="application/pdf")
        with pytest.raises(PhotoValidationError):
            validate_uploaded_photo(f)

    def test_rejects_oversized_file(self):
        f = make_image_file(size=9 * 1024 * 1024)
        with pytest.raises(PhotoValidationError):
            validate_uploaded_photo(f)

    def test_accepts_valid_jpeg(self):
        f = make_image_file()
        validate_uploaded_photo(f)  # should not raise


class TestAddListingPhoto:
    @patch("apps.listings.services.get_fileforge_client")
    def test_uploads_and_persists_photo(self, mock_get_client, listing_factory):
        listing = listing_factory()
        mock_client = mock_get_client.return_value
        mock_client.upload_file.return_value = FileForgeUploadResult(file_id=42, url="https://cdn/42.jpg")

        photo = add_listing_photo(listing=listing, uploaded_file=make_image_file(), order=0)

        assert photo.fileforge_file_id == 42
        assert photo.url == "https://cdn/42.jpg"
        assert photo.listing_id == listing.id
        mock_client.upload_file.assert_called_once()

    @patch("apps.listings.services.get_fileforge_client")
    def test_fileforge_failure_does_not_create_photo_row(self, mock_get_client, listing_factory):
        listing = listing_factory()
        mock_client = mock_get_client.return_value
        mock_client.upload_file.side_effect = FileForgeError("boom")

        with pytest.raises(FileForgeError):
            add_listing_photo(listing=listing, uploaded_file=make_image_file(), order=0)

        assert listing.images.count() == 0

    def test_invalid_photo_never_reaches_fileforge(self, listing_factory):
        listing = listing_factory()
        with patch("apps.listings.services.get_fileforge_client") as mock_get_client:
            with pytest.raises(PhotoValidationError):
                add_listing_photo(
                    listing=listing, uploaded_file=make_image_file(content_type="text/plain"), order=0
                )
            mock_get_client.assert_not_called()


class TestDeleteListingPhoto:
    @patch("apps.listings.services.get_fileforge_client")
    def test_deletes_remote_then_local(self, mock_get_client, listing_photo_factory):
        photo = listing_photo_factory(fileforge_file_id=7)
        mock_client = mock_get_client.return_value

        delete_listing_photo(photo)

        mock_client.delete_file.assert_called_once_with(7)
        from apps.listings.models import ListingPhoto

        assert not ListingPhoto.objects.filter(pk=photo.pk).exists()

    @patch("apps.listings.services.get_fileforge_client")
    def test_local_row_survives_remote_delete_failure(self, mock_get_client, listing_photo_factory):
        photo = listing_photo_factory(fileforge_file_id=8)
        mock_client = mock_get_client.return_value
        mock_client.delete_file.side_effect = FileForgeError("boom")

        with pytest.raises(FileForgeError):
            delete_listing_photo(photo)

        from apps.listings.models import ListingPhoto

        assert ListingPhoto.objects.filter(pk=photo.pk).exists()


class TestReconcilePendingPhotos:
    @patch("apps.listings.services.get_fileforge_client")
    def test_removes_photos_whose_remote_file_is_gone(self, mock_get_client, listing_photo_factory):
        alive = listing_photo_factory(fileforge_file_id=1)
        dead = listing_photo_factory(fileforge_file_id=2)

        mock_client = mock_get_client.return_value

        def get_file_status(file_id):
            if file_id == 2:
                raise FileForgeError("not found")
            return {"id": file_id, "status": "ready"}

        mock_client.get_file_status.side_effect = get_file_status

        reconciled = reconcile_pending_photos()

        assert reconciled == 1
        from apps.listings.models import ListingPhoto

        assert ListingPhoto.objects.filter(pk=alive.pk).exists()
        assert not ListingPhoto.objects.filter(pk=dead.pk).exists()
