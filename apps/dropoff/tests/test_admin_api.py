import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


class TestAdminDropOffPointList:
    def test_scoped_manager_sees_only_assigned_points(self, auth_client, admin_role_factory, drop_off_point_factory):
        role = admin_role_factory(capabilities=["dropoff.manage"])
        client, user = auth_client(admin_role=role)
        mine = drop_off_point_factory()
        mine.managers.add(user)
        other = drop_off_point_factory()
        response = client.get(reverse("admin-dropoff-point-list"))
        ids = [p["id"] for p in response.data]
        assert mine.id in ids
        assert other.id not in ids

    def test_manage_all_sees_everything(self, auth_client, admin_role_factory, drop_off_point_factory):
        role = admin_role_factory(capabilities=["dropoff.manage_all"])
        client, user = auth_client(admin_role=role)
        drop_off_point_factory.create_batch(3)
        response = client.get(reverse("admin-dropoff-point-list"))
        assert len(response.data) == 3

    def test_view_only_capability_can_list_but_not_edit(self, auth_client, admin_role_factory, drop_off_point_factory):
        role = admin_role_factory(capabilities=["dropoff.view"])
        client, user = auth_client(admin_role=role)
        point = drop_off_point_factory()
        point.managers.add(user)
        response = client.get(reverse("admin-dropoff-point-list"))
        assert response.status_code == 200

        edit_response = client.patch(reverse("admin-dropoff-point-detail", args=[point.id]), {"name": "New"})
        assert edit_response.status_code == 403


class TestAdminDropOffPointCreate:
    def test_create_requires_manage_all(self, auth_client, admin_role_factory):
        role = admin_role_factory(capabilities=["dropoff.manage"])  # scoped, not _all
        client, user = auth_client(admin_role=role)
        response = client.post(reverse("admin-dropoff-point-list"), {"name": "New Point", "address": "1 Main St"})
        assert response.status_code == 403

    def test_create_success_with_manage_all(self, auth_client, admin_role_factory):
        role = admin_role_factory(capabilities=["dropoff.manage_all"])
        client, user = auth_client(admin_role=role)
        response = client.post(
            reverse("admin-dropoff-point-list"),
            {"name": "New Point", "address": "1 Main St", "latitude": 51.5, "longitude": -0.1},
        )
        assert response.status_code == 201
        assert response.data["name"] == "New Point"


class TestAdminDropOffPointEdit:
    def test_scoped_manager_can_edit_own_point(self, auth_client, admin_role_factory, drop_off_point_factory):
        role = admin_role_factory(capabilities=["dropoff.manage"])
        client, user = auth_client(admin_role=role)
        point = drop_off_point_factory()
        point.managers.add(user)
        response = client.patch(reverse("admin-dropoff-point-detail", args=[point.id]), {"name": "Renamed"})
        assert response.status_code == 200

    def test_scoped_manager_cannot_edit_unassigned_point(self, auth_client, admin_role_factory, drop_off_point_factory):
        role = admin_role_factory(capabilities=["dropoff.manage"])
        client, user = auth_client(admin_role=role)
        point = drop_off_point_factory()  # not assigned to this user
        response = client.patch(reverse("admin-dropoff-point-detail", args=[point.id]), {"name": "Renamed"})
        assert response.status_code == 404


class TestAssignManagers:
    def test_requires_manage_all(self, auth_client, admin_role_factory, drop_off_point_factory, user_factory):
        role = admin_role_factory(capabilities=["dropoff.manage_all"])
        client, user = auth_client(admin_role=role)
        point = drop_off_point_factory()
        target = user_factory()
        response = client.post(
            reverse("admin-dropoff-point-assign-managers", args=[point.id]), {"user_ids": [target.id]}
        )
        assert response.status_code == 200
        assert target in point.managers.all()

    def test_scoped_manager_cannot_assign_managers(self, auth_client, admin_role_factory, drop_off_point_factory, user_factory):
        role = admin_role_factory(capabilities=["dropoff.manage"])
        client, user = auth_client(admin_role=role)
        point = drop_off_point_factory()
        point.managers.add(user)
        target = user_factory()
        response = client.post(
            reverse("admin-dropoff-point-assign-managers", args=[point.id]), {"user_ids": [target.id]}
        )
        assert response.status_code == 403
