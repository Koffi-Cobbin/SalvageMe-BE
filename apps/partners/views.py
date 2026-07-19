from rest_framework import permissions, status
from rest_framework.generics import CreateAPIView
from rest_framework.response import Response

from . import services
from .serializers import PartnerApplicationSerializer, SubmitPartnerApplicationSerializer


class SubmitPartnerApplicationView(CreateAPIView):
    """POST /partner-applications/ — public."""

    serializer_class = SubmitPartnerApplicationSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        application = services.submit_partner_application(
            requesting_user=request.user if request.user.is_authenticated else None,
            **serializer.validated_data,
        )
        return Response(PartnerApplicationSerializer(application).data, status=status.HTTP_201_CREATED)
