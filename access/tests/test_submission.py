from rest_framework import status

from access.models import Confirmation, Feature, Submission

from .base import NIL_UUID, BaseAPITestCase, User

SUBMISSIONS_URL = "/api/submissions/"


def submission_detail_url(submission_id):
    return f"{SUBMISSIONS_URL}{submission_id}/"


class SubmissionViewSetTests(BaseAPITestCase):
    def valid_payload(self, **overrides):
        payload = {
            "venue": str(self.venue.id),
            "feature": str(self.feature.id),
        }
        payload.update(overrides)
        return payload

    def test_anonymous_cannot_list(self):
        response = self.client.get(SUBMISSIONS_URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_anonymous_cannot_create(self):
        response = self.client.post(SUBMISSIONS_URL, self.valid_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_staff_cannot_create(self):
        self.authenticate(self.user)
        response = self.client.post(SUBMISSIONS_URL, self.valid_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_can_create(self):
        self.authenticate(self.admin_user)
        response = self.client.post(SUBMISSIONS_URL, self.valid_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["reporter"]["username"], self.admin_user.username)

    def test_reporter_cannot_be_spoofed(self):
        self.authenticate(self.admin_user)
        response = self.client.post(
            SUBMISSIONS_URL,
            self.valid_payload(reporter=str(self.other_user.id)),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["reporter"]["username"], self.admin_user.username)

    def test_duplicate_venue_feature_pair_rejected(self):
        Submission.objects.create(
            venue=self.venue, feature=self.feature, reporter=self.admin_user
        )
        self.authenticate(self.admin_user)
        response = self.client.post(SUBMISSIONS_URL, self.valid_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_missing_venue_rejected(self):
        self.authenticate(self.admin_user)
        other_feature = Feature.objects.create(name="Elevator")
        payload = self.valid_payload(feature=str(other_feature.id))
        del payload["venue"]
        response = self.client.post(SUBMISSIONS_URL, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("venue", response.data)

    def test_create_invalid_venue_rejected(self):
        self.authenticate(self.admin_user)
        other_feature = Feature.objects.create(name="Elevator")
        response = self.client.post(
            SUBMISSIONS_URL,
            self.valid_payload(venue=NIL_UUID, feature=str(other_feature.id)),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("venue", response.data)

    def test_create_invalid_feature_rejected(self):
        self.authenticate(self.admin_user)
        response = self.client.post(
            SUBMISSIONS_URL, self.valid_payload(feature=NIL_UUID), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("feature", response.data)

    def test_new_submission_starts_pending_with_zero_votes(self):
        self.authenticate(self.admin_user)
        other_feature = Feature.objects.create(name="Elevator")
        response = self.client.post(
            SUBMISSIONS_URL, self.valid_payload(feature=str(other_feature.id)), format="json"
        )
        self.assertEqual(response.data["accessible_count"], 0)
        self.assertEqual(response.data["inaccessible_count"], 0)
        self.assertEqual(response.data["status"], Submission.Status.PENDING)

    def test_update_not_allowed(self):
        submission = Submission.objects.create(
            venue=self.venue, feature=self.feature, reporter=self.admin_user
        )
        self.authenticate(self.admin_user)
        response = self.client.patch(submission_detail_url(submission.id), {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_staff_can_delete(self):
        submission = Submission.objects.create(
            venue=self.venue, feature=self.feature, reporter=self.admin_user
        )
        self.authenticate(self.admin_user)
        response = self.client.delete(submission_detail_url(submission.id))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_non_staff_cannot_delete(self):
        submission = Submission.objects.create(
            venue=self.venue, feature=self.feature, reporter=self.admin_user
        )
        self.authenticate(self.user)
        response = self.client.delete(submission_detail_url(submission.id))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Submission.objects.filter(id=submission.id).exists())

    def test_filter_by_venue_and_feature(self):
        self.authenticate()
        other_feature = Feature.objects.create(name="Elevator")
        Submission.objects.create(
            venue=self.venue, feature=self.feature, reporter=self.admin_user
        )
        Submission.objects.create(
            venue=self.venue, feature=other_feature, reporter=self.admin_user
        )
        response = self.client.get(
            SUBMISSIONS_URL,
            {"venue": str(self.venue.id), "feature": str(self.feature.id)},
        )
        results = self.results(response)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["feature"], self.feature.id)


class SubmissionStatusComputationTests(BaseAPITestCase):
    """
    Exercises Submission.status directly via the ORM (bypassing the
    Confirmation API, which has its own tests) so these are isolated unit
    tests of the staged status logic itself: MIN_VOTES_FOR_RESOLUTION=3,
    CONFIDENCE_THRESHOLD=0.65. There's no `claim` direction to cross-test
    against anymore -- a vote directly asserts ACCESSIBLE or NOT_ACCESSIBLE.
    """

    def setUp(self):
        super().setUp()
        self.submission = Submission.objects.create(
            venue=self.venue, feature=self.feature, reporter=self.admin_user
        )
        self.voter_a = User.objects.create_user(username="voter-a", password="voter-a-pass")
        self.voter_b = User.objects.create_user(username="voter-b", password="voter-b-pass")
        self.voter_c = User.objects.create_user(username="voter-c", password="voter-c-pass")
        self.voter_d = User.objects.create_user(username="voter-d", password="voter-d-pass")
        self.voter_e = User.objects.create_user(username="voter-e", password="voter-e-pass")

    def get_submission(self):
        self.authenticate()
        return self.client.get(submission_detail_url(self.submission.id))

    def _vote(self, voter, vote):
        Confirmation.objects.create(submission=self.submission, user=voter, vote=vote)

    def test_zero_votes_is_pending(self):
        response = self.get_submission()
        self.assertEqual(response.data["status"], Submission.Status.PENDING)

    def test_unanimous_but_below_minimum_votes_stays_pending(self):
        # 2-0 is unanimous, but MIN_VOTES_FOR_RESOLUTION is 3 -- the vote
        # floor matters independently of how lopsided the split is.
        self._vote(self.voter_a, Confirmation.Vote.ACCESSIBLE)
        self._vote(self.voter_b, Confirmation.Vote.ACCESSIBLE)
        response = self.get_submission()
        self.assertEqual(response.data["status"], Submission.Status.PENDING)

    def test_accessible_at_confidence_boundary_resolves(self):
        # 2 accessible / 1 not-accessible = 66.7%, just clears 65%.
        self._vote(self.voter_a, Confirmation.Vote.ACCESSIBLE)
        self._vote(self.voter_b, Confirmation.Vote.ACCESSIBLE)
        self._vote(self.voter_c, Confirmation.Vote.NOT_ACCESSIBLE)
        response = self.get_submission()
        self.assertEqual(response.data["status"], Submission.Status.CONFIRMED_ACCESSIBLE)

    def test_not_accessible_at_confidence_boundary_resolves(self):
        # 2 not-accessible / 1 accessible = 66.7%.
        self._vote(self.voter_a, Confirmation.Vote.NOT_ACCESSIBLE)
        self._vote(self.voter_b, Confirmation.Vote.NOT_ACCESSIBLE)
        self._vote(self.voter_c, Confirmation.Vote.ACCESSIBLE)
        response = self.get_submission()
        self.assertEqual(response.data["status"], Submission.Status.CONFIRMED_INACCESSIBLE)

    def test_unanimous_not_accessible_resolves_decisively(self):
        self._vote(self.voter_a, Confirmation.Vote.NOT_ACCESSIBLE)
        self._vote(self.voter_b, Confirmation.Vote.NOT_ACCESSIBLE)
        self._vote(self.voter_c, Confirmation.Vote.NOT_ACCESSIBLE)
        response = self.get_submission()
        self.assertEqual(response.data["status"], Submission.Status.CONFIRMED_INACCESSIBLE)

    def test_even_split_is_disputed_not_resolved(self):
        # 2-2 tie: neither side reaches 65%, so this reads as DISPUTED
        # rather than confidently picking a winner off an even split.
        self._vote(self.voter_a, Confirmation.Vote.ACCESSIBLE)
        self._vote(self.voter_b, Confirmation.Vote.ACCESSIBLE)
        self._vote(self.voter_c, Confirmation.Vote.NOT_ACCESSIBLE)
        self._vote(self.voter_d, Confirmation.Vote.NOT_ACCESSIBLE)
        response = self.get_submission()
        self.assertEqual(response.data["status"], Submission.Status.DISPUTED)

    def test_bare_majority_below_confidence_is_disputed(self):
        # 3-2 is a real majority (60%) but doesn't clear the 65% confidence
        # bar -- exactly the razor-thin-split case the confidence threshold
        # exists to avoid confidently resolving.
        self._vote(self.voter_a, Confirmation.Vote.ACCESSIBLE)
        self._vote(self.voter_b, Confirmation.Vote.ACCESSIBLE)
        self._vote(self.voter_c, Confirmation.Vote.ACCESSIBLE)
        self._vote(self.voter_d, Confirmation.Vote.NOT_ACCESSIBLE)
        self._vote(self.voter_e, Confirmation.Vote.NOT_ACCESSIBLE)
        response = self.get_submission()
        self.assertEqual(response.data["status"], Submission.Status.DISPUTED)

    def test_vote_counts_computed_correctly(self):
        self._vote(self.voter_a, Confirmation.Vote.NOT_ACCESSIBLE)
        self._vote(self.voter_b, Confirmation.Vote.ACCESSIBLE)
        response = self.get_submission()
        self.assertEqual(response.data["accessible_count"], 1)
        self.assertEqual(response.data["inaccessible_count"], 1)
