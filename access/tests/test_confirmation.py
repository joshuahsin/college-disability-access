from rest_framework import status

from access.models import Confirmation, Feature, Submission

from .base import NIL_UUID, BaseAPITestCase

CONFIRMATIONS_URL = "/api/confirmations/"


def confirmation_detail_url(confirmation_id):
    return f"{CONFIRMATIONS_URL}{confirmation_id}/"


class ConfirmationViewSetTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self.submission = Submission.objects.create(
            venue=self.venue, feature=self.feature, reporter=self.admin_user
        )

    def test_anonymous_cannot_vote(self):
        response = self.client.post(
            CONFIRMATIONS_URL,
            {"submission": str(self.submission.id), "vote": "ACCESSIBLE"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_first_vote_creates_confirmation_and_returns_201(self):
        self.authenticate()
        response = self.client.post(
            CONFIRMATIONS_URL,
            {"submission": str(self.submission.id), "vote": "ACCESSIBLE"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            Confirmation.objects.filter(submission=self.submission, user=self.user).count(), 1
        )

    def test_recasting_same_vote_is_noop_and_returns_200(self):
        self.authenticate()
        self.client.post(
            CONFIRMATIONS_URL,
            {"submission": str(self.submission.id), "vote": "ACCESSIBLE"},
            format="json",
        )
        response = self.client.post(
            CONFIRMATIONS_URL,
            {"submission": str(self.submission.id), "vote": "ACCESSIBLE"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            Confirmation.objects.filter(submission=self.submission, user=self.user).count(), 1
        )

    def test_switching_vote_updates_in_place_and_returns_200(self):
        self.authenticate()
        self.client.post(
            CONFIRMATIONS_URL,
            {"submission": str(self.submission.id), "vote": "ACCESSIBLE"},
            format="json",
        )
        response = self.client.post(
            CONFIRMATIONS_URL,
            {"submission": str(self.submission.id), "vote": "NOT_ACCESSIBLE"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        confirmations = Confirmation.objects.filter(submission=self.submission, user=self.user)
        self.assertEqual(confirmations.count(), 1)
        self.assertEqual(confirmations.first().vote, Confirmation.Vote.NOT_ACCESSIBLE)

    def test_different_users_can_each_vote_independently(self):
        self.authenticate(self.user)
        self.client.post(
            CONFIRMATIONS_URL,
            {"submission": str(self.submission.id), "vote": "ACCESSIBLE"},
            format="json",
        )
        self.authenticate(self.other_user)
        response = self.client.post(
            CONFIRMATIONS_URL,
            {"submission": str(self.submission.id), "vote": "NOT_ACCESSIBLE"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Confirmation.objects.filter(submission=self.submission).count(), 2)

    def test_invalid_vote_choice_rejected(self):
        self.authenticate()
        response = self.client.post(
            CONFIRMATIONS_URL,
            {"submission": str(self.submission.id), "vote": "MAYBE"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("vote", response.data)

    def test_missing_vote_rejected(self):
        self.authenticate()
        response = self.client.post(
            CONFIRMATIONS_URL, {"submission": str(self.submission.id)}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("vote", response.data)

    def test_vote_on_nonexistent_submission_rejected(self):
        self.authenticate()
        response = self.client.post(
            CONFIRMATIONS_URL, {"submission": NIL_UUID, "vote": "ACCESSIBLE"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("submission", response.data)

    def test_filter_by_submission(self):
        self.authenticate(self.user)
        self.client.post(
            CONFIRMATIONS_URL,
            {"submission": str(self.submission.id), "vote": "ACCESSIBLE"},
            format="json",
        )
        other_feature = Feature.objects.create(name="Elevator")
        other_submission = Submission.objects.create(
            venue=self.venue, feature=other_feature, reporter=self.admin_user
        )
        self.authenticate(self.other_user)
        self.client.post(
            CONFIRMATIONS_URL,
            {"submission": str(other_submission.id), "vote": "NOT_ACCESSIBLE"},
            format="json",
        )

        response = self.client.get(CONFIRMATIONS_URL, {"submission": str(self.submission.id)})
        results = self.results(response)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["submission"], self.submission.id)

    def test_non_owner_cannot_patch_someone_elses_vote(self):
        confirmation = Confirmation.objects.create(
            submission=self.submission, user=self.user, vote=Confirmation.Vote.ACCESSIBLE
        )
        self.authenticate(self.other_user)
        response = self.client.patch(
            confirmation_detail_url(confirmation.id),
            {"vote": "NOT_ACCESSIBLE"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        confirmation.refresh_from_db()
        self.assertEqual(confirmation.vote, Confirmation.Vote.ACCESSIBLE)

    def test_non_owner_cannot_delete_someone_elses_vote(self):
        confirmation = Confirmation.objects.create(
            submission=self.submission, user=self.user, vote=Confirmation.Vote.ACCESSIBLE
        )
        self.authenticate(self.other_user)
        response = self.client.delete(confirmation_detail_url(confirmation.id))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Confirmation.objects.filter(id=confirmation.id).exists())

    def test_owner_can_patch_own_vote(self):
        confirmation = Confirmation.objects.create(
            submission=self.submission, user=self.user, vote=Confirmation.Vote.ACCESSIBLE
        )
        self.authenticate(self.user)
        response = self.client.patch(
            confirmation_detail_url(confirmation.id),
            {"vote": "NOT_ACCESSIBLE"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        confirmation.refresh_from_db()
        self.assertEqual(confirmation.vote, Confirmation.Vote.NOT_ACCESSIBLE)
