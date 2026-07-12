import pytest
from django.urls import reverse


pytestmark = pytest.mark.django_db


class TestCreateRequestEndpoint:
    def test_requires_auth(self, api_client, listing_factory):
        listing = listing_factory()
        response = api_client.post(reverse("listing-request-create", args=[listing.id]), {"message": "hi"})
        assert response.status_code == 401

    def test_success(self, auth_client, listing_factory):
        client, user = auth_client(username="req1")
        listing = listing_factory()
        response = client.post(reverse("listing-request-create", args=[listing.id]), {"message": "please"})
        assert response.status_code == 201
        assert response.data["status"] == "pending"

    def test_self_request_rejected(self, auth_client, listing_factory):
        client, user = auth_client(username="req2")
        listing = listing_factory(owner=user)
        response = client.post(reverse("listing-request-create", args=[listing.id]), {"message": "please"})
        assert response.status_code == 400


class TestListRequestsEndpoint:
    def test_scoped_to_current_user(self, auth_client, book_request_factory, listing_factory):
        client, user = auth_client(username="listuser")
        mine = book_request_factory(requester=user)
        others = book_request_factory()
        response = client.get(reverse("request-list"))
        assert response.status_code == 200
        ids = [r["id"] for r in response.data["results"]]
        assert mine.id in ids
        assert others.id not in ids

    def test_owner_sees_received_requests(self, auth_client, book_request_factory, listing_factory):
        client, user = auth_client(username="ownerlist")
        listing = listing_factory(owner=user)
        received = book_request_factory(listing=listing)
        response = client.get(reverse("request-list"))
        ids = [r["id"] for r in response.data["results"]]
        assert received.id in ids


class TestAcceptDeclineEndpoints:
    def test_accept_by_owner_success(self, auth_client, book_request_factory):
        book_request = book_request_factory()
        owner = book_request.listing.owner
        client, _ = auth_client(user=owner)
        response = client.post(reverse("request-accept", args=[book_request.id]))
        assert response.status_code == 200
        assert response.data["status"] == "accepted"

    def test_accept_by_non_owner_rejected(self, auth_client, book_request_factory):
        book_request = book_request_factory()
        client, _ = auth_client(username="notowner")
        response = client.post(reverse("request-accept", args=[book_request.id]))
        # The viewset's queryset is scoped to requester/listing-owner, so a
        # request this user isn't party to is invisible (404) rather than
        # visible-but-forbidden (403) — this avoids leaking the existence
        # of other users' requests.
        assert response.status_code == 404

    def test_accept_by_requester_themselves_rejected(self, auth_client, book_request_factory):
        """The requester CAN see their own request (in-scope) but isn't the
        listing owner, so this is a 403, distinct from the 404 case above
        where the acting user isn't a party to the request at all."""
        book_request = book_request_factory()
        client, _ = auth_client(user=book_request.requester)
        response = client.post(reverse("request-accept", args=[book_request.id]))
        assert response.status_code == 403

    def test_decline_by_owner_success(self, auth_client, book_request_factory):
        book_request = book_request_factory()
        owner = book_request.listing.owner
        client, _ = auth_client(user=owner)
        response = client.post(reverse("request-decline", args=[book_request.id]))
        assert response.status_code == 200
        assert response.data["status"] == "declined"
