from rest_framework import status

from .base import NIL_UUID, BaseAPITestCase

FEATURES_URL = "/api/features/"


def feature_detail_url(feature_id):
    return f"{FEATURES_URL}{feature_id}/"


class FeatureViewSetTests(BaseAPITestCase):
    def test_anonymous_can_list(self):
        response = self.client.get(FEATURES_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(self.feature.name, [f["name"] for f in self.results(response)])

    def test_retrieve_nonexistent_returns_404(self):
        response = self.client.get(feature_detail_url(NIL_UUID))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_anonymous_cannot_create(self):
        response = self.client.post(FEATURES_URL, {"name": "Elevator"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_can_create(self):
        self.authenticate()
        response = self.client.post(
            FEATURES_URL,
            {"name": "Elevator", "description": "Accessible elevator"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_missing_name_rejected(self):
        self.authenticate()
        response = self.client.post(FEATURES_URL, {"description": "no name"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("name", response.data)

    def test_create_duplicate_name_rejected(self):
        self.authenticate()
        response = self.client.post(FEATURES_URL, {"name": self.feature.name}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("name", response.data)

    def test_description_optional(self):
        self.authenticate()
        response = self.client.post(FEATURES_URL, {"name": "Braille Signage"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["description"], "")

    def test_authenticated_can_update(self):
        self.authenticate()
        response = self.client.patch(
            feature_detail_url(self.feature.id), {"description": "Updated"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_authenticated_can_delete(self):
        self.authenticate()
        response = self.client.delete(feature_detail_url(self.feature.id))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
