from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from access.models import Campus, Feature, Venue

User = get_user_model()

NIL_UUID = "00000000-0000-0000-0000-000000000000"


class BaseAPITestCase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="alice-pass-1")
        self.other_user = User.objects.create_user(username="bob", password="bob-pass-1")
        self.admin_user = User.objects.create_user(
            username="admin-carol", password="admin-carol-pass-1", is_staff=True
        )

        self.campus = Campus.objects.create(name="Main Campus")
        self.venue = Venue.objects.create(
            campus=self.campus,
            name="Library",
            latitude=33.6405,
            longitude=-117.8443,
            category=Venue.Category.LIBRARY,
        )
        self.feature = Feature.objects.create(name="Ramp", description="Wheelchair ramp")

    def authenticate(self, user=None):
        self.client.force_authenticate(user=user or self.user)

    @staticmethod
    def results(response):
        """List endpoints are paginated -- unwrap the `results` page."""
        return response.data["results"]
