from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.db.models import Q
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from common.exceptions import ServiceUnavailableError
from common.fileforge_client import FileForgeError
from common.pagination import CursorSetPagination

from .filters import ListingFilterSet
from .models import Category, Listing
from .permissions import IsListingOwnerOrReadOnly
from .serializers import CategorySerializer, ListingPhotoSerializer, ListingSerializer, ListingWriteSerializer
from .services import PhotoValidationError, add_listing_photo


class ListingPagination(CursorSetPagination):
    ordering = "-created_at"


class ListingViewSet(viewsets.ModelViewSet):
    """
    /api/v1/listings/

    Public read access (list/retrieve show only `available` listings unless
    the requester is the owner or staff); write access requires
    authentication and, for update/delete/photos, ownership.
    """

    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsListingOwnerOrReadOnly]
    filterset_class = ListingFilterSet
    pagination_class = ListingPagination

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return ListingWriteSerializer
        return ListingSerializer

    def get_queryset(self):
        queryset = Listing.objects.select_related("owner", "category").prefetch_related("images")

        user = self.request.user
        if self.action in ("list", "retrieve"):
            if user.is_authenticated:
                # Owners/staff can see their own non-available listings too
                # (e.g. pending/claimed) — everyone else only sees available.
                visible = Q(status=Listing.Status.AVAILABLE) | Q(owner=user)
                if user.is_staff:
                    visible = Q()
                queryset = queryset.filter(visible)
            else:
                queryset = queryset.filter(status=Listing.Status.AVAILABLE)

        query = self.request.query_params.get("q")
        if query:
            queryset = queryset.filter(Q(title__icontains=query) | Q(description__icontains=query))

        near = self.request.query_params.get("near")
        if near:
            try:
                lat_str, lng_str = near.split(",")
                origin = Point(float(lng_str), float(lat_str), srid=4326)
            except (ValueError, TypeError):
                return queryset.none()

            queryset = queryset.filter(location__isnull=False).annotate(
                distance=Distance("location", origin)
            )

            radius_km = self.request.query_params.get("radius")
            if radius_km:
                try:
                    queryset = queryset.filter(location__distance_lte=(origin, D(km=float(radius_km))))
                except (ValueError, TypeError):
                    pass

            queryset = queryset.order_by("distance")

        return queryset

    def perform_destroy(self, instance):
        # Soft delete: preserves history/audit trail rather than hard
        # deleting user-generated content outright.
        instance.status = Listing.Status.REMOVED
        instance.save(update_fields=["status", "updated_at"])

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(
        detail=True,
        methods=["post"],
        parser_classes=[MultiPartParser, FormParser],
        permission_classes=[permissions.IsAuthenticated, IsListingOwnerOrReadOnly],
    )
    def photos(self, request, pk=None):
        listing = self.get_object()
        uploaded_file = request.FILES.get("file")
        if uploaded_file is None:
            return Response({"detail": "No file provided.", "code": "missing_file"}, status=400)

        next_order = listing.images.count()
        try:
            photo = add_listing_photo(listing=listing, uploaded_file=uploaded_file, order=next_order)
        except PhotoValidationError as exc:
            return Response({"detail": str(exc), "code": "invalid_photo"}, status=400)
        except FileForgeError as exc:
            raise ServiceUnavailableError(str(exc)) from exc

        return Response(ListingPhotoSerializer(photo).data, status=status.HTTP_201_CREATED)


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None
