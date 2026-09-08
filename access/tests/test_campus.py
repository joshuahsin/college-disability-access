from rest_framework import status

from access.models import Campus

from .base import NIL_UUID, BaseAPITestCase

CAMPUSES_URL = "/api/campuses/"


def campus_detail_url(campus_id):
    return f"{CAMPUSES_URL}{campus_id}/"


class CampusViewSetTests(BaseAPITestCase):
    def test_anonymous_can_list(self):
        response = self.client.get(CAMPUSES_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(self.campus.name, [c["name"] for c in self.results(response)])

    def test_anonymous_can_retrieve(self):
        response = self.client.get(campus_detail_url(self.campus.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Main Campus")

    def test_retrieve_nonexistent_returns_404(self):
        response = self.client.get(campus_detail_url(NIL_UUID))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_anonymous_cannot_create(self):
        response = self.client.post(CAMPUSES_URL, {"name": "New Campus"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(Campus.objects.filter(name="New Campus").exists())

    def test_authenticated_can_create(self):
        self.authenticate()
        response = self.client.post(CAMPUSES_URL, {"name": "New Campus"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Campus.objects.filter(name="New Campus").exists())

    def test_create_missing_name_rejected(self):
        self.authenticate()
        response = self.client.post(CAMPUSES_URL, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("name", response.data)

    def test_create_duplicate_name_rejected(self):
        self.authenticate()
        response = self.client.post(CAMPUSES_URL, {"name": self.campus.name}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("name", response.data)

    def test_authenticated_can_update(self):
        self.authenticate()
        response = self.client.patch(
            campus_detail_url(self.campus.id), {"name": "Renamed Campus"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.campus.refresh_from_db()
        self.assertEqual(self.campus.name, "Renamed Campus")

    def test_anonymous_cannot_update(self):
        response = self.client.patch(
            campus_detail_url(self.campus.id), {"name": "Renamed Campus"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_can_delete(self):
        self.authenticate()
        response = self.client.delete(campus_detail_url(self.campus.id))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Campus.objects.filter(id=self.campus.id).exists())

    def test_anonymous_cannot_delete(self):
        response = self.client.delete(campus_detail_url(self.campus.id))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertTrue(Campus.objects.filter(id=self.campus.id).exists())
