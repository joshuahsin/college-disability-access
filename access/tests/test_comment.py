from rest_framework import status

from access.models import Comment, Feature, Submission

from .base import NIL_UUID, BaseAPITestCase

COMMENTS_URL = "/api/comments/"


def comment_detail_url(comment_id):
    return f"{COMMENTS_URL}{comment_id}/"


class CommentViewSetTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self.submission = Submission.objects.create(
            venue=self.venue, feature=self.feature, reporter=self.admin_user
        )

    def test_anonymous_cannot_list(self):
        response = self.client.get(COMMENTS_URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_anonymous_cannot_create(self):
        response = self.client.post(
            COMMENTS_URL,
            {"submission": str(self.submission.id), "body": "Nice find!"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_can_create(self):
        self.authenticate()
        response = self.client.post(
            COMMENTS_URL,
            {"submission": str(self.submission.id), "body": "Confirmed today."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["user"]["username"], self.user.username)
        self.assertIsNone(response.data["parent"])
        self.assertEqual(response.data["like_count"], 0)
        self.assertEqual(response.data["dislike_count"], 0)

    def test_author_cannot_be_spoofed(self):
        self.authenticate(self.user)
        response = self.client.post(
            COMMENTS_URL,
            {
                "submission": str(self.submission.id),
                "body": "hi",
                "user": str(self.other_user.id),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["user"]["username"], self.user.username)

    def test_empty_body_rejected(self):
        self.authenticate()
        response = self.client.post(
            COMMENTS_URL, {"submission": str(self.submission.id), "body": ""}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("body", response.data)

    def test_whitespace_only_body_rejected(self):
        self.authenticate()
        response = self.client.post(
            COMMENTS_URL,
            {"submission": str(self.submission.id), "body": "   \n  "},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("body", response.data)

    def test_body_over_max_length_rejected(self):
        self.authenticate()
        response = self.client.post(
            COMMENTS_URL,
            {"submission": str(self.submission.id), "body": "x" * 2001},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("body", response.data)

    def test_body_at_max_length_accepted(self):
        self.authenticate()
        response = self.client.post(
            COMMENTS_URL,
            {"submission": str(self.submission.id), "body": "x" * 2000},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_comment_on_nonexistent_submission_rejected(self):
        self.authenticate()
        response = self.client.post(
            COMMENTS_URL, {"submission": NIL_UUID, "body": "hi"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("submission", response.data)

    def test_author_can_update_own_comment(self):
        comment = Comment.objects.create(
            submission=self.submission, user=self.user, body="Original"
        )
        self.authenticate(self.user)
        response = self.client.patch(
            comment_detail_url(comment.id), {"body": "Edited"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        comment.refresh_from_db()
        self.assertEqual(comment.body, "Edited")

    def test_non_author_cannot_update_comment(self):
        comment = Comment.objects.create(
            submission=self.submission, user=self.user, body="Original"
        )
        self.authenticate(self.other_user)
        response = self.client.patch(
            comment_detail_url(comment.id), {"body": "Hijacked"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        comment.refresh_from_db()
        self.assertEqual(comment.body, "Original")

    def test_author_can_delete_own_comment(self):
        comment = Comment.objects.create(
            submission=self.submission, user=self.user, body="Original"
        )
        self.authenticate(self.user)
        response = self.client.delete(comment_detail_url(comment.id))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Comment.objects.filter(id=comment.id).exists())

    def test_non_author_cannot_delete_comment(self):
        comment = Comment.objects.create(
            submission=self.submission, user=self.user, body="Original"
        )
        self.authenticate(self.other_user)
        response = self.client.delete(comment_detail_url(comment.id))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Comment.objects.filter(id=comment.id).exists())

    def test_any_authenticated_user_can_read_others_comments(self):
        comment = Comment.objects.create(
            submission=self.submission, user=self.user, body="Visible"
        )
        self.authenticate(self.other_user)
        response = self.client.get(comment_detail_url(comment.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_filter_by_submission(self):
        self.authenticate(self.user)
        Comment.objects.create(
            submission=self.submission, user=self.user, body="On this submission"
        )
        other_feature = Feature.objects.create(name="Elevator")
        other_submission = Submission.objects.create(
            venue=self.venue, feature=other_feature, reporter=self.admin_user
        )
        Comment.objects.create(
            submission=other_submission, user=self.user, body="On other submission"
        )
        response = self.client.get(COMMENTS_URL, {"submission": str(self.submission.id)})
        results = self.results(response)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["body"], "On this submission")


class CommentReplyTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self.submission = Submission.objects.create(
            venue=self.venue, feature=self.feature, reporter=self.admin_user
        )
        self.top_level = Comment.objects.create(
            submission=self.submission, user=self.user, body="Top-level comment"
        )

    def test_reply_created_with_parent(self):
        self.authenticate(self.other_user)
        response = self.client.post(
            COMMENTS_URL,
            {
                "submission": str(self.submission.id),
                "parent": str(self.top_level.id),
                "body": "A reply",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["parent"], self.top_level.id)
        self.assertEqual(
            Comment.objects.get(pk=response.data["id"]).parent_id, self.top_level.id
        )

    def test_reply_to_reply_rejected(self):
        reply = Comment.objects.create(
            submission=self.submission,
            user=self.other_user,
            parent=self.top_level,
            body="First reply",
        )
        self.authenticate(self.user)
        response = self.client.post(
            COMMENTS_URL,
            {
                "submission": str(self.submission.id),
                "parent": str(reply.id),
                "body": "Reply to a reply",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("parent", response.data)

    def test_reply_with_mismatched_submission_rejected(self):
        other_feature = Feature.objects.create(name="Elevator")
        other_submission = Submission.objects.create(
            venue=self.venue, feature=other_feature, reporter=self.admin_user
        )
        self.authenticate(self.other_user)
        response = self.client.post(
            COMMENTS_URL,
            {
                "submission": str(other_submission.id),
                "parent": str(self.top_level.id),
                "body": "Wrong thread",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("parent", response.data)

    def test_reply_with_nonexistent_parent_rejected(self):
        self.authenticate(self.other_user)
        response = self.client.post(
            COMMENTS_URL,
            {"submission": str(self.submission.id), "parent": NIL_UUID, "body": "hi"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("parent", response.data)

    def test_deleting_parent_cascades_to_replies(self):
        reply = Comment.objects.create(
            submission=self.submission,
            user=self.other_user,
            parent=self.top_level,
            body="A reply",
        )
        self.authenticate(self.user)
        response = self.client.delete(comment_detail_url(self.top_level.id))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Comment.objects.filter(id=reply.id).exists())

    def test_filter_by_parent(self):
        reply = Comment.objects.create(
            submission=self.submission,
            user=self.other_user,
            parent=self.top_level,
            body="A reply",
        )
        self.authenticate(self.user)
        response = self.client.get(COMMENTS_URL, {"parent": str(self.top_level.id)})
        results = self.results(response)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], str(reply.id))
