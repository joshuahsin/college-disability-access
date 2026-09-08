import datetime

from django.utils import timezone
from rest_framework import status

from access.models import Confirmation, Feature, Submission

from .base import NIL_UUID, BaseAPITestCase, User

SUBMISSIONS_URL = "/api/submissions/"
LATEST_URL = "/api/submissions/latest/"


def submission_detail_url(submission_id):
    return f"{SUBMISSIONS_URL}{submission_id}/"


class SubmissionViewSetTests(BaseAPITestCase):
    def valid_payload(self, **overrides):
        payload = {
            "venue": str(self.venue.id),
            "feature": str(self.feature.id),
            "claim": True,
        }
        payload.update(overrides)
        return payload

    def test_anonymous_cannot_list(self):
        response = self.client.get(SUBMISSIONS_URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_anonymous_cannot_create(self):
        response = self.client.post(SUBMISSIONS_URL, self.valid_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_can_create(self):
        self.authenticate()
        response = self.client.post(SUBMISSIONS_URL, self.valid_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["reporter"]["username"], self.user.username)

    def test_reporter_cannot_be_spoofed(self):
        self.authenticate(self.user)
        response = self.client.post(
            SUBMISSIONS_URL,
            self.valid_payload(reporter=str(self.other_user.id)),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["reporter"]["username"], self.user.username)

    def test_create_missing_claim_rejected(self):
        self.authenticate()
        payload = self.valid_payload()
        del payload["claim"]
        response = self.client.post(SUBMISSIONS_URL, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("claim", response.data)

    def test_create_missing_venue_rejected(self):
        self.authenticate()
        payload = self.valid_payload()
        del payload["venue"]
        response = self.client.post(SUBMISSIONS_URL, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("venue", response.data)

    def test_create_invalid_venue_rejected(self):
        self.authenticate()
        response = self.client.post(
            SUBMISSIONS_URL, self.valid_payload(venue=NIL_UUID), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("venue", response.data)

    def test_create_invalid_feature_rejected(self):
        self.authenticate()
        response = self.client.post(
            SUBMISSIONS_URL, self.valid_payload(feature=NIL_UUID), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("feature", response.data)

    def test_new_submission_starts_pending_with_zero_votes(self):
        self.authenticate()
        response = self.client.post(SUBMISSIONS_URL, self.valid_payload(claim=True), format="json")
        self.assertEqual(response.data["confirm_count"], 0)
        self.assertEqual(response.data["dispute_count"], 0)
        self.assertEqual(response.data["dispute_rate"], 0.0)
        self.assertEqual(response.data["status"], Submission.Status.PENDING)

    def test_filter_by_venue_and_feature(self):
        self.authenticate()
        other_feature = Feature.objects.create(name="Elevator")
        Submission.objects.create(
            venue=self.venue, feature=self.feature, reporter=self.user, claim=True
        )
        Submission.objects.create(
            venue=self.venue, feature=other_feature, reporter=self.user, claim=False
        )
        response = self.client.get(
            SUBMISSIONS_URL,
            {"venue": str(self.venue.id), "feature": str(self.feature.id)},
        )
        results = self.results(response)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["feature"], self.feature.id)

    def test_latest_requires_authentication(self):
        response = self.client.get(
            LATEST_URL, {"venue": str(self.venue.id), "feature": str(self.feature.id)}
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_latest_missing_params_returns_400(self):
        self.authenticate()
        response = self.client.get(LATEST_URL, {"venue": str(self.venue.id)})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_latest_no_matching_submission_returns_404(self):
        self.authenticate()
        response = self.client.get(
            LATEST_URL, {"venue": str(self.venue.id), "feature": str(self.feature.id)}
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_latest_returns_most_recent_submission(self):
        self.authenticate()
        older = Submission.objects.create(
            venue=self.venue, feature=self.feature, reporter=self.user, claim=True
        )
        newer = Submission.objects.create(
            venue=self.venue, feature=self.feature, reporter=self.other_user, claim=False
        )
        # Force a clear ordering regardless of clock resolution between the
        # two create() calls above.
        Submission.objects.filter(pk=older.pk).update(
            created_at=timezone.now() - datetime.timedelta(minutes=5)
        )
        response = self.client.get(
            LATEST_URL, {"venue": str(self.venue.id), "feature": str(self.feature.id)}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], str(newer.id))


class SubmissionStatusComputationTests(BaseAPITestCase):
    """
    Exercises Submission.status directly via the ORM (bypassing the
    Confirmation API, which has its own tests) so these are isolated unit
    tests of the staged status logic itself: MIN_VOTES_FOR_RESOLUTION=3,
    CONFIDENCE_THRESHOLD=0.65.
    """

    def setUp(self):
        super().setUp()
        self.submission_true = Submission.objects.create(
            venue=self.venue, feature=self.feature, reporter=self.user, claim=True
        )
        other_feature = Feature.objects.create(name="Elevator")
        self.submission_false = Submission.objects.create(
            venue=self.venue, feature=other_feature, reporter=self.user, claim=False
        )
        self.voter_a = User.objects.create_user(username="voter-a", password="voter-a-pass")
        self.voter_b = User.objects.create_user(username="voter-b", password="voter-b-pass")
        self.voter_c = User.objects.create_user(username="voter-c", password="voter-c-pass")
        self.voter_d = User.objects.create_user(username="voter-d", password="voter-d-pass")
        self.voter_e = User.objects.create_user(username="voter-e", password="voter-e-pass")

    def get_submission(self, submission):
        self.authenticate()
        return self.client.get(submission_detail_url(submission.id))

    def _vote(self, submission, voter, vote):
        Confirmation.objects.create(submission=submission, user=voter, vote=vote)

    def test_zero_votes_is_pending(self):
        response = self.get_submission(self.submission_true)
        self.assertEqual(response.data["status"], Submission.Status.PENDING)

    def test_unanimous_but_below_minimum_votes_stays_pending(self):
        # 2-0 confirm is unanimous, but MIN_VOTES_FOR_RESOLUTION is 3 -- the
        # vote floor matters independently of how lopsided the split is.
        self._vote(self.submission_true, self.voter_a, Confirmation.Vote.CONFIRM)
        self._vote(self.submission_true, self.voter_b, Confirmation.Vote.CONFIRM)
        response = self.get_submission(self.submission_true)
        self.assertEqual(response.data["status"], Submission.Status.PENDING)

    def test_confirm_at_confidence_boundary_resolves_accessible(self):
        # claim=True, 2 confirm / 1 dispute = 66.7%, just clears 65%.
        self._vote(self.submission_true, self.voter_a, Confirmation.Vote.CONFIRM)
        self._vote(self.submission_true, self.voter_b, Confirmation.Vote.CONFIRM)
        self._vote(self.submission_true, self.voter_c, Confirmation.Vote.DISPUTE)
        response = self.get_submission(self.submission_true)
        self.assertEqual(response.data["status"], Submission.Status.CONFIRMED_ACCESSIBLE)

    def test_dispute_at_confidence_boundary_resolves_inaccessible(self):
        # claim=True, 2 dispute / 1 confirm = 66.7% -- community says the
        # opposite of what was reported.
        self._vote(self.submission_true, self.voter_a, Confirmation.Vote.DISPUTE)
        self._vote(self.submission_true, self.voter_b, Confirmation.Vote.DISPUTE)
        self._vote(self.submission_true, self.voter_c, Confirmation.Vote.CONFIRM)
        response = self.get_submission(self.submission_true)
        self.assertEqual(response.data["status"], Submission.Status.CONFIRMED_INACCESSIBLE)
        self.assertTrue(response.data["claim"])

    def test_dispute_unanimous_on_false_claim_resolves_accessible(self):
        # claim=False, 3-0 dispute -- community says it IS accessible,
        # contradicting the reporter.
        self._vote(self.submission_false, self.voter_a, Confirmation.Vote.DISPUTE)
        self._vote(self.submission_false, self.voter_b, Confirmation.Vote.DISPUTE)
        self._vote(self.submission_false, self.voter_c, Confirmation.Vote.DISPUTE)
        response = self.get_submission(self.submission_false)
        self.assertEqual(response.data["status"], Submission.Status.CONFIRMED_ACCESSIBLE)
        self.assertFalse(response.data["claim"])

    def test_even_split_is_disputed_not_resolved(self):
        # 2-2 tie: neither side reaches 65%, so this reads as DISPUTED
        # rather than confidently picking a winner off an even split.
        self._vote(self.submission_true, self.voter_a, Confirmation.Vote.CONFIRM)
        self._vote(self.submission_true, self.voter_b, Confirmation.Vote.CONFIRM)
        self._vote(self.submission_true, self.voter_c, Confirmation.Vote.DISPUTE)
        self._vote(self.submission_true, self.voter_d, Confirmation.Vote.DISPUTE)
        response = self.get_submission(self.submission_true)
        self.assertEqual(response.data["status"], Submission.Status.DISPUTED)

    def test_bare_majority_below_confidence_is_disputed(self):
        # 3-2 confirm is a real majority (60%) but doesn't clear the 65%
        # confidence bar -- this is exactly the razor-thin-split case the
        # confidence threshold exists to avoid confidently resolving.
        self._vote(self.submission_true, self.voter_a, Confirmation.Vote.CONFIRM)
        self._vote(self.submission_true, self.voter_b, Confirmation.Vote.CONFIRM)
        self._vote(self.submission_true, self.voter_c, Confirmation.Vote.CONFIRM)
        self._vote(self.submission_true, self.voter_d, Confirmation.Vote.DISPUTE)
        self._vote(self.submission_true, self.voter_e, Confirmation.Vote.DISPUTE)
        response = self.get_submission(self.submission_true)
        self.assertEqual(response.data["status"], Submission.Status.DISPUTED)

    def test_dispute_rate_computed_correctly(self):
        self._vote(self.submission_true, self.voter_a, Confirmation.Vote.DISPUTE)
        self._vote(self.submission_true, self.voter_b, Confirmation.Vote.CONFIRM)
        response = self.get_submission(self.submission_true)
        self.assertEqual(response.data["confirm_count"], 1)
        self.assertEqual(response.data["dispute_count"], 1)
        self.assertEqual(response.data["dispute_rate"], 0.5)

    def test_claim_never_mutated_in_db_regardless_of_votes(self):
        self._vote(self.submission_true, self.voter_a, Confirmation.Vote.DISPUTE)
        self._vote(self.submission_true, self.voter_b, Confirmation.Vote.DISPUTE)
        self._vote(self.submission_true, self.voter_c, Confirmation.Vote.DISPUTE)
        self.submission_true.refresh_from_db()
        self.assertTrue(self.submission_true.claim)
