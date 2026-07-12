import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


class TestRegister:
    def test_register_success(self, api_client):
        url = reverse("auth-register")
        payload = {
            "username": "newdonor",
            "email": "newdonor@example.com",
            "password": "S3cure!Pass123",
            "role": "donor",
        }
        response = api_client.post(url, payload)
        assert response.status_code == 201
        assert "access" in response.data
        assert response.data["user"]["username"] == "newdonor"
        assert "salvageme_refresh" in response.cookies
        assert response.cookies["salvageme_refresh"]["httponly"] is True

    def test_register_invalid_password_rejected(self, api_client):
        url = reverse("auth-register")
        payload = {"username": "weakpass", "email": "x@example.com", "password": "123"}
        response = api_client.post(url, payload)
        assert response.status_code == 400

    def test_register_duplicate_username_rejected(self, api_client, user_factory):
        user_factory(username="taken")
        url = reverse("auth-register")
        payload = {"username": "taken", "email": "y@example.com", "password": "S3cure!Pass123"}
        response = api_client.post(url, payload)
        assert response.status_code == 400


class TestLogin:
    def test_login_success_sets_refresh_cookie(self, api_client, user_factory):
        user_factory(username="loginuser", password="knownpass123!")
        url = reverse("auth-login")
        response = api_client.post(url, {"username": "loginuser", "password": "knownpass123!"})
        assert response.status_code == 200
        assert "access" in response.data
        assert "salvageme_refresh" in response.cookies

    def test_login_wrong_password_rejected(self, api_client, user_factory):
        user_factory(username="loginuser2", password="knownpass123!")
        url = reverse("auth-login")
        response = api_client.post(url, {"username": "loginuser2", "password": "wrong"})
        assert response.status_code == 401


class TestRefresh:
    def test_refresh_without_cookie_rejected(self, api_client):
        url = reverse("auth-refresh")
        response = api_client.post(url)
        assert response.status_code == 401

    def test_refresh_with_valid_cookie_issues_new_access(self, api_client, user_factory):
        user_factory(username="refreshuser", password="knownpass123!")
        login_url = reverse("auth-login")
        login_resp = api_client.post(login_url, {"username": "refreshuser", "password": "knownpass123!"})
        refresh_cookie = login_resp.cookies["salvageme_refresh"].value

        api_client.cookies["salvageme_refresh"] = refresh_cookie
        response = api_client.post(reverse("auth-refresh"))
        assert response.status_code == 200
        assert "access" in response.data


class TestLogout:
    def test_logout_clears_cookie(self, api_client, user_factory):
        user_factory(username="logoutuser", password="knownpass123!")
        login_resp = api_client.post(reverse("auth-login"), {"username": "logoutuser", "password": "knownpass123!"})
        api_client.cookies["salvageme_refresh"] = login_resp.cookies["salvageme_refresh"].value

        response = api_client.post(reverse("auth-logout"))
        assert response.status_code == 204
        assert response.cookies["salvageme_refresh"].value == ""


class TestUserMe:
    def test_get_me_requires_auth(self, api_client):
        response = api_client.get(reverse("user-me"))
        assert response.status_code == 401

    def test_get_me_success(self, auth_client):
        client, user = auth_client(username="meuser")
        response = client.get(reverse("user-me"))
        assert response.status_code == 200
        assert response.data["username"] == "meuser"
        assert "phone" in response.data  # self-view includes contact info

    def test_patch_me_updates_role_and_location(self, auth_client):
        client, user = auth_client(username="patchuser")
        response = client.patch(
            reverse("user-me"), {"role": "recipient", "latitude": 40.7128, "longitude": -74.0060}
        )
        assert response.status_code == 200
        assert response.data["role"] == "recipient"
        assert response.data["latitude"] == pytest.approx(40.7128, abs=1e-3)
