from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.listings.models import Listing
from common.pagination import CursorSetPagination

from . import services
from .models import BookRequest
from .serializers import BookRequestSerializer, CreateBookRequestSerializer


class ListingRequestCreateView(mixins.CreateModelMixin, viewsets.GenericViewSet):
    """POST /api/v1/listings/{listing_id}/request/"""

    serializer_class = CreateBookRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, listing_pk=None):
        listing = get_object_or_404(Listing, pk=listing_pk)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        book_request = services.create_request(
            listing=listing, requester=request.user, message=serializer.validated_data.get("message", "")
        )
        return Response(BookRequestSerializer(book_request).data, status=status.HTTP_201_CREATED)


class BookRequestViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """
    GET /api/v1/requests/ — scoped to the current user (sent + received)
    POST /api/v1/requests/{id}/accept/
    POST /api/v1/requests/{id}/decline/
    """

    serializer_class = BookRequestSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = CursorSetPagination

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False) or not self.request.user.is_authenticated:
            return BookRequest.objects.none()
        user = self.request.user
        return (
            BookRequest.objects.select_related("listing", "requester", "listing__owner")
            .filter(Q(requester=user) | Q(listing__owner=user))
        )

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        book_request = self.get_object()
        book_request = services.accept_request(book_request=book_request, acting_user=request.user)
        return Response(BookRequestSerializer(book_request).data)

    @action(detail=True, methods=["post"])
    def decline(self, request, pk=None):
        book_request = self.get_object()
        book_request = services.decline_request(book_request=book_request, acting_user=request.user)
        return Response(BookRequestSerializer(book_request).data)
