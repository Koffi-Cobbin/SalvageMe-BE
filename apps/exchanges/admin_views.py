from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from common.pagination import CursorSetPagination
from common.permissions import HasCapability

from . import services
from .admin_serializers import ForceOverrideSerializer
from .models import Exchange
from .serializers import ExchangeSerializer


class AdminExchangePagination(CursorSetPagination):
    ordering = "-id"


class AdminExchangeViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """
    /api/v1/admin/exchanges/ — every exchange, not scoped to the current
    user (unlike the public /exchanges/ endpoint).
    """

    queryset = Exchange.objects.select_related("listing", "donor", "recipient", "dropoff_point")
    serializer_class = ExchangeSerializer
    permission_classes = [HasCapability("exchanges.view")]
    pagination_class = AdminExchangePagination
    filterset_fields = ["status"]

    @action(detail=True, methods=["post"], url_path="force-cancel", permission_classes=[HasCapability("exchanges.force_override")])
    def force_cancel(self, request, pk=None):
        exchange = self.get_object()
        serializer = ForceOverrideSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        exchange = services.force_cancel_exchange(
            exchange=exchange, acting_user=request.user, reason=serializer.validated_data["reason"]
        )
        return Response(ExchangeSerializer(exchange, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="force-complete", permission_classes=[HasCapability("exchanges.force_override")])
    def force_complete(self, request, pk=None):
        exchange = self.get_object()
        serializer = ForceOverrideSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        exchange = services.force_complete_exchange(
            exchange=exchange, acting_user=request.user, reason=serializer.validated_data["reason"]
        )
        return Response(ExchangeSerializer(exchange, context={"request": request}).data)
