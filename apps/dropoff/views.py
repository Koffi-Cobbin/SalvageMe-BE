from rest_framework import permissions, viewsets

from .models import DropOffPoint
from .serializers import DropOffPointSerializer


class DropOffPointViewSet(viewsets.ReadOnlyModelViewSet):
    """GET /api/v1/dropoff-points/ — public, used to populate a scheduling picker."""

    queryset = DropOffPoint.objects.select_related("coordinator").all()
    serializer_class = DropOffPointSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None
