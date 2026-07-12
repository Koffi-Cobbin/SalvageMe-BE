from rest_framework import mixins, permissions, status, viewsets
from rest_framework.response import Response

from . import services
from .serializers import ReportSerializer


class ReportViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    """POST /api/v1/reports/ — any authenticated user can file a report."""

    serializer_class = ReportSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        report = services.create_report(reporter=request.user, **serializer.validated_data)
        return Response(self.get_serializer(report).data, status=status.HTTP_201_CREATED)
