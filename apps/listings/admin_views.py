from django_filters import rest_framework as django_filters
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from common.exceptions import ServiceUnavailableError
from common.fileforge_client import FileForgeError
from common.pagination import CursorSetPagination
from common.permissions import HasCapability

from . import services
from .models import Category, Listing, ListingPhoto
from .serializers import CategorySerializer, ListingSerializer


class AdminListingFilterSet(django_filters.FilterSet):
    category = django_filters.CharFilter(field_name="category__slug")

    class Meta:
        model = Listing
        fields = ["category", "condition", "status"]


class AdminListingPagination(CursorSetPagination):
    ordering = "-created_at"


class AdminListingViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """
    /api/v1/admin/listings/ — unlike the public endpoint, returns every
    status including `removed`, since staff need to review/undo removals.
    """

    queryset = Listing.objects.select_related("owner", "category").prefetch_related("images")
    serializer_class = ListingSerializer
    permission_classes = [HasCapability("listings.view")]
    filterset_class = AdminListingFilterSet
    pagination_class = AdminListingPagination

    @action(detail=True, methods=["post"], permission_classes=[HasCapability("listings.remove_restore")])
    def remove(self, request, pk=None):
        listing = self.get_object()
        listing.status = Listing.Status.REMOVED
        listing.save(update_fields=["status", "updated_at"])
        from apps.moderation.services import record_audit_log

        record_audit_log(actor=request.user, action="listing_removed", target_type="listing", target_id=listing.id)
        return Response(ListingSerializer(listing).data)

    @action(detail=True, methods=["post"], permission_classes=[HasCapability("listings.remove_restore")])
    def restore(self, request, pk=None):
        listing = self.get_object()
        if listing.status not in (Listing.Status.REMOVED,):
            from rest_framework.exceptions import ValidationError

            raise ValidationError(
                {"detail": f"Cannot restore a listing with status '{listing.status}'.", "code": "invalid_transition"}
            )
        listing.status = Listing.Status.AVAILABLE
        listing.save(update_fields=["status", "updated_at"])
        from apps.moderation.services import record_audit_log

        record_audit_log(actor=request.user, action="listing_restored", target_type="listing", target_id=listing.id)
        return Response(ListingSerializer(listing).data)

    @extend_schema(parameters=[OpenApiParameter("photo_id", OpenApiTypes.INT, location=OpenApiParameter.PATH)])
    @action(
        detail=True,
        methods=["delete"],
        url_path="photos/(?P<photo_id>[^/.]+)",
        permission_classes=[HasCapability("listings.delete_photo")],
    )
    def delete_photo(self, request, pk=None, photo_id=None):
        listing = self.get_object()
        photo = ListingPhoto.objects.filter(pk=photo_id, listing=listing).first()
        if photo is None:
            return Response({"detail": "Photo not found.", "code": "not_found"}, status=404)

        try:
            services.delete_listing_photo(photo)
        except FileForgeError as exc:
            raise ServiceUnavailableError(str(exc)) from exc

        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminCategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [HasCapability("categories.manage")]
    pagination_class = None

    def destroy(self, request, *args, **kwargs):
        from django.db.models import ProtectedError
        from rest_framework.exceptions import ValidationError

        instance = self.get_object()
        try:
            instance.delete()
        except ProtectedError as exc:
            raise ValidationError(
                {"detail": "This category has listings and cannot be deleted.", "code": "category_in_use"}
            ) from exc
        return Response(status=status.HTTP_204_NO_CONTENT)
