from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()

REGISTER_URL = "/api/auth/register/"
ME_URL = "/api/auth/me/"
TOKEN_URL = "/api/auth/token/"
REFRESH_URL = "/api/auth/token/refresh/"
CAMPUSES_URL = "/api/campuses/"


class RegisterViewTests(APITestCase):
    def test_register_success(self):
        response = self.client.post(
            REGISTER_URL, {"username": "newuser", "password": "s3cur3pass"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(username="newuser").exists())

    def test_register_does_not_echo_password(self):
        response = self.client.post(
            REGISTER_URL, {"username": "newuser", "password": "s3cur3pass"}, format="json"
        )
        self.assertNotIn("password", response.data)

    def test_register_hashes_password(self):
        self.client.post(
            REGISTER_URL, {"username": "newuser", "password": "s3cur3pass"}, format="json"
        )
        user = User.objects.get(username="newuser")
        self.assertNotEqual(user.password, "s3cur3pass")
        self.assertTrue(user.check_password("s3cur3pass"))

    def test_register_missing_username(self):
        response = self.client.post(REGISTER_URL, {"password": "s3cur3pass"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("username", response.data)

    def test_register_missing_password(self):
        response = self.client.post(REGISTER_URL, {"username": "newuser"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)

    def test_register_password_too_short(self):
        response = self.client.post(
            REGISTER_URL, {"username": "newuser", "password": "short"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)

    def test_register_duplicate_username_rejected(self):
        User.objects.create_user(username="dupe", password="s3cur3pass")
        response = self.client.post(
            REGISTER_URL, {"username": "dupe", "password": "s3cur3pass2"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("username", response.data)


class TokenObtainAndRefreshTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="alice-pass-1")

    def test_obtain_token_success(self):
        response = self.client.post(
            TOKEN_URL, {"username": "alice", "password": "alice-pass-1"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_obtain_token_wrong_password(self):
        response = self.client.post(
            TOKEN_URL, {"username": "alice", "password": "wrong-password"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_obtain_token_nonexistent_user(self):
        response = self.client.post(
            TOKEN_URL, {"username": "ghost", "password": "whatever12"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_obtain_token_missing_fields(self):
        response = self.client.post(TOKEN_URL, {"username": "alice"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_refresh_token_success(self):
        obtain = self.client.post(
            TOKEN_URL, {"username": "alice", "password": "alice-pass-1"}, format="json"
        )
        response = self.client.post(
            REFRESH_URL, {"refresh": obtain.data["refresh"]}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)

    def test_refresh_token_invalid(self):
        response = self.client.post(REFRESH_URL, {"refresh": "not-a-real-token"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_token_missing(self):
        response = self.client.post(REFRESH_URL, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_access_token_actually_authenticates_protected_endpoint(self):
        obtain = self.client.post(
            TOKEN_URL, {"username": "alice", "password": "alice-pass-1"}, format="json"
        )
        access = obtain.data["access"]
        # Submissions require only IsAuthenticated to read (no staff
        # needed), so this isolates "does the token authenticate at all"
        # from any authorization/staff concern.
        response = self.client.get(
            "/api/submissions/", HTTP_AUTHORIZATION=f"Bearer {access}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class MeViewTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="alice-pass-1")
        self.admin_user = User.objects.create_user(
            username="admin-carol", password="admin-carol-pass-1", is_staff=True
        )

    def _token_for(self, username, password):
        response = self.client.post(
            TOKEN_URL, {"username": username, "password": password}, format="json"
        )
        return response.data["access"]

    def test_anonymous_cannot_fetch_me(self):
        response = self.client.get(ME_URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_regular_user_sees_own_profile_not_staff(self):
        access = self._token_for("alice", "alice-pass-1")
        response = self.client.get(ME_URL, HTTP_AUTHORIZATION=f"Bearer {access}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], "alice")
        self.assertFalse(response.data["is_staff"])

    def test_staff_user_sees_own_profile_is_staff(self):
        access = self._token_for("admin-carol", "admin-carol-pass-1")
        response = self.client.get(ME_URL, HTTP_AUTHORIZATION=f"Bearer {access}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], "admin-carol")
        self.assertTrue(response.data["is_staff"])

    def test_me_does_not_expose_password(self):
        access = self._token_for("alice", "alice-pass-1")
        response = self.client.get(ME_URL, HTTP_AUTHORIZATION=f"Bearer {access}")
        self.assertNotIn("password", response.data)


class ProtectedEndpointAuthTests(APITestCase):
    def test_write_without_token_is_401(self):
        response = self.client.post(CAMPUSES_URL, {"name": "No Auth Campus"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_write_with_garbage_token_is_401(self):
        response = self.client.post(
            CAMPUSES_URL,
            {"name": "No Auth Campus"},
            format="json",
            HTTP_AUTHORIZATION="Bearer not-a-real-token",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
