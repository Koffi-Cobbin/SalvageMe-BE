from django.db.models import Q
from rest_framework import mixins, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from common.pagination import CursorSetPagination

from . import services
from .models import Exchange
from .serializers import ExchangeSerializer, RateExchangeSerializer, ScheduleExchangeSerializer


class ExchangePagination(CursorSetPagination):
    ordering = "-id"


class ExchangeViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = ExchangeSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = ExchangePagination

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False) or not self.request.user.is_authenticated:
            return Exchange.objects.none()
        user = self.request.user
        return Exchange.objects.select_related(
            "listing", "donor", "recipient", "dropoff_point"
        ).filter(Q(donor=user) | Q(recipient=user))

    @action(detail=True, methods=["post"])
    def schedule(self, request, pk=None):
        exchange = self.get_object()
        serializer = ScheduleExchangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        exchange = services.schedule_exchange(
            exchange=exchange,
            acting_user=request.user,
            scheduled_at=serializer.validated_data["scheduled_at"],
            dropoff_point=serializer.validated_data.get("dropoff_point"),
        )
        return Response(ExchangeSerializer(exchange, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        exchange = self.get_object()
        exchange = services.complete_exchange(exchange=exchange, acting_user=request.user)
        return Response(ExchangeSerializer(exchange, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        exchange = self.get_object()
        exchange = services.cancel_exchange(exchange=exchange, acting_user=request.user)
        return Response(ExchangeSerializer(exchange, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def rate(self, request, pk=None):
        exchange = self.get_object()
        serializer = RateExchangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        rating = services.rate_exchange(
            exchange=exchange,
            acting_user=request.user,
            score=serializer.validated_data["score"],
            comment=serializer.validated_data.get("comment", ""),
        )
        from apps.accounts.serializers import UserRatingSerializer

        return Response(UserRatingSerializer(rating).data, status=201)
