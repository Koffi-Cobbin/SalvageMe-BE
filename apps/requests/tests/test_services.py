import datetime

import pytest
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.exchanges.models import Exchange
from apps.listings.models import Listing
from apps.requests import services
from apps.requests.models import BookRequest

pytestmark = pytest.mark.django_db


class TestCreateRequest:
    def test_cannot_request_own_listing(self, user_factory, listing_factory):
        owner = user_factory(username="owner")
        listing = listing_factory(owner=owner)
        with pytest.raises(ValidationError):
            services.create_request(listing=listing, requester=owner)

    def test_cannot_request_unavailable_listing(self, listing_factory, user_factory):
        listing = listing_factory(status=Listing.Status.CLAIMED)
        requester = user_factory(username="requester1")
        with pytest.raises(ValidationError):
            services.create_request(listing=listing, requester=requester)

    def test_duplicate_pending_request_rejected(self, listing_factory, user_factory):
        listing = listing_factory()
        requester = user_factory(username="requester2")
        services.create_request(listing=listing, requester=requester)
        with pytest.raises(ValidationError):
            services.create_request(listing=listing, requester=requester)

    def test_successful_request_creation(self, listing_factory, user_factory):
        listing = listing_factory()
        requester = user_factory(username="requester3")
        book_request = services.create_request(listing=listing, requester=requester, message="please")
        assert book_request.status == BookRequest.Status.PENDING
        assert book_request.message == "please"


class TestAcceptRequest:
    def test_only_owner_can_accept(self, book_request_factory, user_factory):
        book_request = book_request_factory()
        stranger = user_factory(username="stranger")
        with pytest.raises(PermissionDenied):
            services.accept_request(book_request=book_request, acting_user=stranger)

    def test_accept_creates_exchange_and_marks_listing_pending(self, book_request_factory):
        book_request = book_request_factory()
        owner = book_request.listing.owner

        result = services.accept_request(book_request=book_request, acting_user=owner)

        result.refresh_from_db()
        assert result.status == BookRequest.Status.ACCEPTED
        book_request.listing.refresh_from_db()
        assert book_request.listing.status == Listing.Status.PENDING
        assert Exchange.objects.filter(listing=book_request.listing).exists()

    def test_accept_already_accepted_request_rejected(self, book_request_factory):
        book_request = book_request_factory()
        owner = book_request.listing.owner
        services.accept_request(book_request=book_request, acting_user=owner)
        with pytest.raises(ValidationError):
            services.accept_request(book_request=book_request, acting_user=owner)

    def test_accepting_one_request_declines_other_pending_requests(self, listing_factory, user_factory, book_request_factory):
        listing = listing_factory()
        r1 = book_request_factory(listing=listing)
        r2 = book_request_factory(listing=listing)

        services.accept_request(book_request=r1, acting_user=listing.owner)

        r2.refresh_from_db()
        assert r2.status == BookRequest.Status.DECLINED


class TestDeclineRequest:
    def test_only_owner_can_decline(self, book_request_factory, user_factory):
        book_request = book_request_factory()
        stranger = user_factory(username="stranger2")
        with pytest.raises(PermissionDenied):
            services.decline_request(book_request=book_request, acting_user=stranger)

    def test_decline_success_leaves_listing_available(self, book_request_factory):
        book_request = book_request_factory()
        owner = book_request.listing.owner
        result = services.decline_request(book_request=book_request, acting_user=owner)
        assert result.status == BookRequest.Status.DECLINED
        book_request.listing.refresh_from_db()
        assert book_request.listing.status == Listing.Status.AVAILABLE

    def test_decline_already_declined_rejected(self, book_request_factory):
        book_request = book_request_factory()
        owner = book_request.listing.owner
        services.decline_request(book_request=book_request, acting_user=owner)
        with pytest.raises(ValidationError):
            services.decline_request(book_request=book_request, acting_user=owner)


class TestExpireStaleRequests:
    def test_expires_only_old_pending_requests(self, book_request_factory):
        old = book_request_factory()
        BookRequest.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - datetime.timedelta(days=30)
        )
        fresh = book_request_factory()

        count = services.expire_stale_requests(threshold_days=14)

        assert count == 1
        old.refresh_from_db()
        fresh.refresh_from_db()
        assert old.status == BookRequest.Status.CANCELLED
        assert fresh.status == BookRequest.Status.PENDING
