from django.urls import path

from . import views

urlpatterns = [
    path("users/me/", views.UserMeView.as_view(), name="user-me"),
]
