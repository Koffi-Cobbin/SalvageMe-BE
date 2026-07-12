"""
Consistent error response shape for the whole API: {"detail": ..., "code": ...}

DRF's default exception handler already does most of the work; we wrap it so
every error — validation, permission, throttling, not-found, or an
unexpected 500 that bubbles up as a DRF exception — comes back in the same
shape the frontend can branch on.
"""
import logging

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger("salvageme")


class ServiceUnavailableError(APIException):
    """
    Raised by views when a service-layer call (e.g. the FileForge client)
    fails because an upstream dependency is unreachable or errors out.
    Results in a clean 502 response instead of a bare 500, and never lets
    local/remote state drift (e.g. no ListingPhoto row is created without a
    backing FileForge file).
    """

    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "An upstream service is currently unavailable. Please try again shortly."
    default_code = "service_unavailable"


def custom_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)

    if response is None:
        return None

    code = getattr(exc, "default_code", None) or exc.__class__.__name__.lower()

    if isinstance(response.data, dict) and "detail" in response.data:
        detail = response.data["detail"]
        extra = {k: v for k, v in response.data.items() if k != "detail"}
    else:
        detail = response.data
        extra = {}

    payload = {"detail": detail, "code": code}
    if extra:
        payload["errors"] = extra

    response.data = payload
    return response
