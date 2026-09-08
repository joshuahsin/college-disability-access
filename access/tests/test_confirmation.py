from rest_framework import status

from access.models import Confirmation, Submission

from .base import NIL_UUID, BaseAPITestCase

CONFIRMATIONS_URL = "/api/confirmations/"


class ConfirmationViewSetTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self.submission = Submission.objects.create(
            venue=self.venue, feature=self.feature, reporter=self.user, claim=True
        )

    def test_anonymous_cannot_vote(self):
        response = self.client.post(
            CONFIRMATIONS_URL,
            {"submission": str(self.submission.id), "vote": "CONFIRM"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_first_vote_creates_confirmation_and_returns_201(self):
        self.authenticate()
        response = self.client.post(
            CONFIRMATIONS_URL,
            {"submission": str(self.submission.id), "vote": "CONFIRM"},
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
            {"submission": str(self.submission.id), "vote": "CONFIRM"},
            format="json",
        )
        response = self.client.post(
            CONFIRMATIONS_URL,
            {"submission": str(self.submission.id), "vote": "CONFIRM"},
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
            {"submission": str(self.submission.id), "vote": "CONFIRM"},
            format="json",
        )
        response = self.client.post(
            CONFIRMATIONS_URL,
            {"submission": str(self.submission.id), "vote": "DISPUTE"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        confirmations = Confirmation.objects.filter(submission=self.submission, user=self.user)
        self.assertEqual(confirmations.count(), 1)
        self.assertEqual(confirmations.first().vote, Confirmation.Vote.DISPUTE)

    def test_different_users_can_each_vote_independently(self):
        self.authenticate(self.user)
        self.client.post(
            CONFIRMATIONS_URL,
            {"submission": str(self.submission.id), "vote": "CONFIRM"},
            format="json",
        )
        self.authenticate(self.other_user)
        response = self.client.post(
            CONFIRMATIONS_URL,
            {"submission": str(self.submission.id), "vote": "DISPUTE"},
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
            CONFIRMATIONS_URL, {"submission": NIL_UUID, "vote": "CONFIRM"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("submission", response.data)

    def test_filter_by_submission(self):
        self.authenticate(self.user)
        self.client.post(
            CONFIRMATIONS_URL,
            {"submission": str(self.submission.id), "vote": "CONFIRM"},
            format="json",
        )
        other_submission = Submission.objects.create(
            venue=self.venue, feature=self.feature, reporter=self.other_user, claim=False
        )
        self.authenticate(self.other_user)
        self.client.post(
            CONFIRMATIONS_URL,
            {"submission": str(other_submission.id), "vote": "DISPUTE"},
            format="json",
        )

        response = self.client.get(CONFIRMATIONS_URL, {"submission": str(self.submission.id)})
        results = self.results(response)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["submission"], self.submission.id)
