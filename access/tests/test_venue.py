from rest_framework import status

from access.models import Campus, Venue

from .base import NIL_UUID, BaseAPITestCase

VENUES_URL = "/api/venues/"


def venue_detail_url(venue_id):
    return f"{VENUES_URL}{venue_id}/"


class VenueViewSetTests(BaseAPITestCase):
    def valid_payload(self, **overrides):
        payload = {
            "campus": str(self.campus.id),
            "name": "Student Union",
            "address": "123 Campus Dr",
            "latitude": 33.64,
            "longitude": -117.84,
            "category": Venue.Category.DINING,
        }
        payload.update(overrides)
        return payload

    def test_anonymous_can_list(self):
        response = self.client.get(VENUES_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(str(self.venue.id), [v["id"] for v in self.results(response)])

    def test_anonymous_can_retrieve(self):
        response = self.client.get(venue_detail_url(self.venue.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_retrieve_nonexistent_returns_404(self):
        response = self.client.get(venue_detail_url(NIL_UUID))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_anonymous_cannot_create(self):
        response = self.client.post(VENUES_URL, self.valid_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_can_create(self):
        self.authenticate()
        response = self.client.post(VENUES_URL, self.valid_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_duplicate_name_same_campus_rejected(self):
        self.authenticate()
        response = self.client.post(
            VENUES_URL, self.valid_payload(name=self.venue.name), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_same_name_different_campus_allowed(self):
        self.authenticate()
        other_campus = Campus.objects.create(name="Other Campus")
        response = self.client.post(
            VENUES_URL,
            self.valid_payload(campus=str(other_campus.id), name=self.venue.name),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_missing_campus_rejected(self):
        self.authenticate()
        payload = self.valid_payload()
        del payload["campus"]
        response = self.client.post(VENUES_URL, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("campus", response.data)

    def test_create_nonexistent_campus_rejected(self):
        self.authenticate()
        response = self.client.post(
            VENUES_URL, self.valid_payload(campus=NIL_UUID), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("campus", response.data)

    def test_latitude_above_max_rejected(self):
        self.authenticate()
        response = self.client.post(VENUES_URL, self.valid_payload(latitude=91.0), format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("latitude", response.data)

    def test_latitude_below_min_rejected(self):
        self.authenticate()
        response = self.client.post(VENUES_URL, self.valid_payload(latitude=-91.0), format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("latitude", response.data)

    def test_latitude_at_boundary_accepted(self):
        self.authenticate()
        response = self.client.post(VENUES_URL, self.valid_payload(latitude=90.0), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_longitude_above_max_rejected(self):
        self.authenticate()
        response = self.client.post(VENUES_URL, self.valid_payload(longitude=181.0), format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("longitude", response.data)

    def test_longitude_below_min_rejected(self):
        self.authenticate()
        response = self.client.post(
            VENUES_URL, self.valid_payload(longitude=-181.0), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("longitude", response.data)

    def test_invalid_category_rejected(self):
        self.authenticate()
        response = self.client.post(VENUES_URL, self.valid_payload(category="spa"), format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("category", response.data)

    def test_address_optional(self):
        self.authenticate()
        payload = self.valid_payload()
        del payload["address"]
        response = self.client.post(VENUES_URL, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["address"], "")

    def test_filter_by_campus(self):
        other_campus = Campus.objects.create(name="Other Campus")
        Venue.objects.create(
            campus=other_campus,
            name="Other Venue",
            latitude=1.0,
            longitude=1.0,
            category=Venue.Category.REC,
        )
        response = self.client.get(VENUES_URL, {"campus": str(self.campus.id)})
        results = self.results(response)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], str(self.venue.id))

    def test_filter_by_category(self):
        Venue.objects.create(
            campus=self.campus,
            name="Dining Hall",
            latitude=1.0,
            longitude=1.0,
            category=Venue.Category.DINING,
        )
        response = self.client.get(VENUES_URL, {"category": Venue.Category.LIBRARY})
        results = self.results(response)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], str(self.venue.id))

    def test_authenticated_can_update(self):
        self.authenticate()
        response = self.client.patch(
            venue_detail_url(self.venue.id), {"name": "Renamed Venue"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_authenticated_can_delete(self):
        self.authenticate()
        response = self.client.delete(venue_detail_url(self.venue.id))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Venue.objects.filter(id=self.venue.id).exists())
