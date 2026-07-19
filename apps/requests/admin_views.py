from rest_framework import mixins, viewsets

from common.pagination import CursorSetPagination
from common.permissions import HasCapability

from .models import BookRequest
from .serializers import BookRequestSerializer


class AdminRequestPagination(CursorSetPagination):
    ordering = "-created_at"


class AdminBookRequestViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """/api/v1/admin/requests/ — every request, read-only support visibility."""

    queryset = BookRequest.objects.select_related("listing", "requester", "listing__owner")
    serializer_class = BookRequestSerializer
    permission_classes = [HasCapability("requests.view")]
    pagination_class = AdminRequestPagination
    filterset_fields = ["status"]
