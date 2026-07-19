from django.urls import path

from .views import SubmitPartnerApplicationView

urlpatterns = [
    path("partner-applications/", SubmitPartnerApplicationView.as_view(), name="partner-application-submit"),
]
