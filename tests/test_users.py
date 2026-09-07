import pytest
from django.urls import reverse
from rest_framework import status

from apps.users.models import User, UserRole


@pytest.mark.django_db
class TestUserModel:
    def test_create_user_successful(self):
        user = User.objects.create_user(
            email="newuser@example.com",
            password="StrongPassword123!",
            first_name="Пётр",
        )
        assert user.email == "newuser@example.com"
        assert user.check_password("StrongPassword123!")
        assert user.is_active is True
        assert user.is_staff is False
        assert user.is_superuser is False
        assert user.role == UserRole.CUSTOMER

    def test_create_user_without_email_raises_error(self):
        with pytest.raises(ValueError):
            User.objects.create_user(email="", password="StrongPassword123!")

    def test_create_superuser_successful(self):
        admin_user = User.objects.create_superuser(
            email="admin@example.com",
            password="AdminPassword123!",
        )
        assert admin_user.email == "admin@example.com"
        assert admin_user.is_staff is True
        assert admin_user.is_superuser is True
        assert admin_user.role == UserRole.ADMIN


@pytest.mark.django_db
class TestUserAPI:
    def test_register_user_api(self, api_client):
        url = reverse("users:register")
        payload = {
            "email": "customer@example.com",
            "password": "SecretPassword123!",
            "password_confirm": "SecretPassword123!",
            "first_name": "Алексей",
            "last_name": "Смирнов",
        }
        response = api_client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert "user" in response.data
        assert response.data["user"]["email"] == "customer@example.com"
        assert User.objects.filter(email="customer@example.com").exists()

    def test_register_user_passwords_mismatch(self, api_client):
        url = reverse("users:register")
        payload = {
            "email": "customer2@example.com",
            "password": "Password123!",
            "password_confirm": "DifferentPassword123!",
        }
        response = api_client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_get_profile_authenticated(self, authenticated_client, test_user):
        url = reverse("users:profile")
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["email"] == test_user.email

    def test_get_profile_unauthenticated(self, api_client):
        url = reverse("users:profile")
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
