"""
Service-layer functions for listings — kept out of views/serializers so the
business logic is unit-testable in isolation (see WHAT NOT TO DO: no
business logic living only in views/serializers).
"""

from common.fileforge_client import FileForgeError, get_fileforge_client

from .models import Listing, ListingPhoto

ALLOWED_PHOTO_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_PHOTO_SIZE_BYTES = 8 * 1024 * 1024  # 8MB


class PhotoValidationError(Exception):
    """Raised when an uploaded photo fails server-side validation."""


def validate_uploaded_photo(uploaded_file) -> None:
    """
    Server-side enforcement of content-type and size limits — never trust
    the frontend's own validation (see SECURITY REQUIREMENTS).
    """
    if uploaded_file.content_type not in ALLOWED_PHOTO_CONTENT_TYPES:
        raise PhotoValidationError(
            f"Unsupported content type '{uploaded_file.content_type}'. "
            f"Allowed: {', '.join(sorted(ALLOWED_PHOTO_CONTENT_TYPES))}."
        )
    if uploaded_file.size > MAX_PHOTO_SIZE_BYTES:
        raise PhotoValidationError(
            f"File too large ({uploaded_file.size} bytes). "
            f"Max is {MAX_PHOTO_SIZE_BYTES} bytes."
        )


def add_listing_photo(*, listing: Listing, uploaded_file, order: int = 0) -> ListingPhoto:
    """
    Validates and forwards a photo to FileForge, then persists the returned
    reference. Raises PhotoValidationError for bad input (-> 400) or
    FileForgeError if the upstream call fails (-> 502), and never creates a
    ListingPhoto row with no backing file.
    """
    validate_uploaded_photo(uploaded_file)

    client = get_fileforge_client()
    result = client.upload_file(
        uploaded_file,
        filename=uploaded_file.name,
        content_type=uploaded_file.content_type,
    )

    return ListingPhoto.objects.create(
        listing=listing,
        fileforge_file_id=result.file_id,
        url=result.url,
        order=order,
    )


def reconcile_pending_photos() -> int:
    """
    Called by the daily `run_daily_jobs` management command. Our upload
    flow only ever creates a ListingPhoto row after a successful synchronous
    FileForge response (see add_listing_photo), so there is no long-lived
    "pending" state to sweep up under normal operation. This pass instead
    catches drift: any ListingPhoto whose backing FileForge file no longer
    exists (e.g. deleted directly via FileForge's own admin) is removed
    locally so the frontend never renders a broken image reference.
    """
    client = get_fileforge_client()
    reconciled = 0

    for photo in ListingPhoto.objects.all():
        try:
            client.get_file_status(photo.fileforge_file_id)
        except FileForgeError:
            photo.delete()
            reconciled += 1

    return reconciled


def delete_listing_photo(photo: ListingPhoto) -> None:
    """
    Deletes the FileForge-backed file first, then the local row — if
    FileForge deletion fails, we deliberately leave the local row in place
    (surfacing a 502) rather than orphaning the remote file silently.
    """
    client = get_fileforge_client()
    client.delete_file(photo.fileforge_file_id)
    photo.delete()
