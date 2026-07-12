import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_dropoff_points_list_is_public(api_client, drop_off_point_factory):
    drop_off_point_factory.create_batch(2)
    response = api_client.get(reverse("dropoff-point-list"))
    assert response.status_code == 200
    assert len(response.data) == 2


def test_dropoff_point_exposes_lat_lng(api_client, drop_off_point_factory):
    point = drop_off_point_factory()
    response = api_client.get(reverse("dropoff-point-detail", args=[point.id]))
    assert response.status_code == 200
    assert response.data["latitude"] is not None
    assert response.data["longitude"] is not None
