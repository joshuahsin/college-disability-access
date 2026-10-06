from rest_framework import status

from access.models import Comment, CommentReaction, Submission

from .base import NIL_UUID, BaseAPITestCase

COMMENT_REACTIONS_URL = "/api/comment-reactions/"


def comment_reaction_detail_url(reaction_id):
    return f"{COMMENT_REACTIONS_URL}{reaction_id}/"


class CommentReactionViewSetTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self.submission = Submission.objects.create(
            venue=self.venue, feature=self.feature, reporter=self.admin_user
        )
        self.comment = Comment.objects.create(
            submission=self.submission, user=self.admin_user, body="Original comment"
        )

    def test_anonymous_cannot_react(self):
        response = self.client.post(
            COMMENT_REACTIONS_URL,
            {"comment": str(self.comment.id), "vote": "LIKE"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_first_reaction_creates_and_returns_201(self):
        self.authenticate()
        response = self.client.post(
            COMMENT_REACTIONS_URL,
            {"comment": str(self.comment.id), "vote": "LIKE"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            CommentReaction.objects.filter(comment=self.comment, user=self.user).count(), 1
        )

    def test_recasting_same_reaction_is_noop_and_returns_200(self):
        self.authenticate()
        self.client.post(
            COMMENT_REACTIONS_URL,
            {"comment": str(self.comment.id), "vote": "LIKE"},
            format="json",
        )
        response = self.client.post(
            COMMENT_REACTIONS_URL,
            {"comment": str(self.comment.id), "vote": "LIKE"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            CommentReaction.objects.filter(comment=self.comment, user=self.user).count(), 1
        )

    def test_switching_reaction_updates_in_place_and_returns_200(self):
        self.authenticate()
        self.client.post(
            COMMENT_REACTIONS_URL,
            {"comment": str(self.comment.id), "vote": "LIKE"},
            format="json",
        )
        response = self.client.post(
            COMMENT_REACTIONS_URL,
            {"comment": str(self.comment.id), "vote": "DISLIKE"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        reactions = CommentReaction.objects.filter(comment=self.comment, user=self.user)
        self.assertEqual(reactions.count(), 1)
        self.assertEqual(reactions.first().vote, CommentReaction.Vote.DISLIKE)

    def test_different_users_can_each_react_independently(self):
        self.authenticate(self.user)
        self.client.post(
            COMMENT_REACTIONS_URL,
            {"comment": str(self.comment.id), "vote": "LIKE"},
            format="json",
        )
        self.authenticate(self.other_user)
        response = self.client.post(
            COMMENT_REACTIONS_URL,
            {"comment": str(self.comment.id), "vote": "DISLIKE"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(CommentReaction.objects.filter(comment=self.comment).count(), 2)

    def test_invalid_vote_choice_rejected(self):
        self.authenticate()
        response = self.client.post(
            COMMENT_REACTIONS_URL,
            {"comment": str(self.comment.id), "vote": "LOVE"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("vote", response.data)

    def test_missing_vote_rejected(self):
        self.authenticate()
        response = self.client.post(
            COMMENT_REACTIONS_URL, {"comment": str(self.comment.id)}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("vote", response.data)

    def test_react_on_nonexistent_comment_rejected(self):
        self.authenticate()
        response = self.client.post(
            COMMENT_REACTIONS_URL, {"comment": NIL_UUID, "vote": "LIKE"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("comment", response.data)

    def test_filter_by_comment(self):
        self.authenticate(self.user)
        self.client.post(
            COMMENT_REACTIONS_URL,
            {"comment": str(self.comment.id), "vote": "LIKE"},
            format="json",
        )
        other_comment = Comment.objects.create(
            submission=self.submission, user=self.admin_user, body="Another comment"
        )
        self.authenticate(self.other_user)
        self.client.post(
            COMMENT_REACTIONS_URL,
            {"comment": str(other_comment.id), "vote": "DISLIKE"},
            format="json",
        )

        response = self.client.get(COMMENT_REACTIONS_URL, {"comment": str(self.comment.id)})
        results = self.results(response)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["comment"], self.comment.id)

    def test_like_and_dislike_counts_on_comment(self):
        self.authenticate(self.user)
        self.client.post(
            COMMENT_REACTIONS_URL,
            {"comment": str(self.comment.id), "vote": "LIKE"},
            format="json",
        )
        self.authenticate(self.other_user)
        self.client.post(
            COMMENT_REACTIONS_URL,
            {"comment": str(self.comment.id), "vote": "LIKE"},
            format="json",
        )
        self.authenticate(self.admin_user)
        self.client.post(
            COMMENT_REACTIONS_URL,
            {"comment": str(self.comment.id), "vote": "DISLIKE"},
            format="json",
        )

        response = self.client.get(f"/api/comments/{self.comment.id}/")
        self.assertEqual(response.data["like_count"], 2)
        self.assertEqual(response.data["dislike_count"], 1)

    def test_non_owner_cannot_patch_someone_elses_reaction(self):
        reaction = CommentReaction.objects.create(
            comment=self.comment, user=self.user, vote=CommentReaction.Vote.LIKE
        )
        self.authenticate(self.other_user)
        response = self.client.patch(
            comment_reaction_detail_url(reaction.id), {"vote": "DISLIKE"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        reaction.refresh_from_db()
        self.assertEqual(reaction.vote, CommentReaction.Vote.LIKE)

    def test_non_owner_cannot_delete_someone_elses_reaction(self):
        reaction = CommentReaction.objects.create(
            comment=self.comment, user=self.user, vote=CommentReaction.Vote.LIKE
        )
        self.authenticate(self.other_user)
        response = self.client.delete(comment_reaction_detail_url(reaction.id))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(CommentReaction.objects.filter(id=reaction.id).exists())

    def test_owner_can_patch_own_reaction(self):
        reaction = CommentReaction.objects.create(
            comment=self.comment, user=self.user, vote=CommentReaction.Vote.LIKE
        )
        self.authenticate(self.user)
        response = self.client.patch(
            comment_reaction_detail_url(reaction.id), {"vote": "DISLIKE"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        reaction.refresh_from_db()
        self.assertEqual(reaction.vote, CommentReaction.Vote.DISLIKE)


def comment_reaction_nested_url(comment_id):
    return f"/api/comments/{comment_id}/reaction/"


class CommentReactionNestedPatchTests(BaseAPITestCase):
    """
    PATCH /api/comments/<comment_id>/reaction/ -- the alternative to the
    standalone /api/comment-reactions/ endpoint that identifies the target
    by (comment, request.user) instead of the reaction's own id.
    """

    def setUp(self):
        super().setUp()
        self.submission = Submission.objects.create(
            venue=self.venue, feature=self.feature, reporter=self.admin_user
        )
        self.comment = Comment.objects.create(
            submission=self.submission, user=self.admin_user, body="Original comment"
        )

    def test_anonymous_rejected(self):
        response = self.client.patch(
            comment_reaction_nested_url(self.comment.id), {"vote": "LIKE"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_first_reaction_creates_and_returns_201(self):
        self.authenticate(self.user)
        response = self.client.patch(
            comment_reaction_nested_url(self.comment.id), {"vote": "LIKE"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            CommentReaction.objects.filter(comment=self.comment, user=self.user).count(), 1
        )

    def test_recasting_same_reaction_is_noop_and_returns_200(self):
        self.authenticate(self.user)
        self.client.patch(
            comment_reaction_nested_url(self.comment.id), {"vote": "LIKE"}, format="json"
        )
        response = self.client.patch(
            comment_reaction_nested_url(self.comment.id), {"vote": "LIKE"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            CommentReaction.objects.filter(comment=self.comment, user=self.user).count(), 1
        )

    def test_switching_reaction_updates_in_place_and_returns_200(self):
        self.authenticate(self.user)
        self.client.patch(
            comment_reaction_nested_url(self.comment.id), {"vote": "LIKE"}, format="json"
        )
        response = self.client.patch(
            comment_reaction_nested_url(self.comment.id), {"vote": "DISLIKE"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        reactions = CommentReaction.objects.filter(comment=self.comment, user=self.user)
        self.assertEqual(reactions.count(), 1)
        self.assertEqual(reactions.first().vote, CommentReaction.Vote.DISLIKE)

    def test_can_react_to_someone_elses_comment(self):
        # The comment belongs to admin_user; self.user is neither its
        # author nor staff. Reacting must still work -- liking/disliking
        # other people's comments is the entire point of the feature. This
        # is exactly the case that would break if the action used
        # get_object() and inherited CommentViewSet's IsAuthorOrReadOnly
        # check meant for editing the comment itself.
        self.authenticate(self.user)
        response = self.client.patch(
            comment_reaction_nested_url(self.comment.id), {"vote": "LIKE"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_reaction_on_nonexistent_comment_returns_404(self):
        self.authenticate(self.user)
        response = self.client.patch(
            comment_reaction_nested_url(NIL_UUID), {"vote": "LIKE"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_invalid_vote_rejected(self):
        self.authenticate(self.user)
        response = self.client.patch(
            comment_reaction_nested_url(self.comment.id), {"vote": "LOVE"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("vote", response.data)

    def test_missing_vote_rejected(self):
        self.authenticate(self.user)
        response = self.client.patch(comment_reaction_nested_url(self.comment.id), {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("vote", response.data)

    def test_response_does_not_require_comment_field_in_request(self):
        # The request body only needs `vote` -- `comment` comes from the
        # URL, `user` from the token. Confirm the response still reports
        # the correct comment/user despite neither being in the request.
        self.authenticate(self.user)
        response = self.client.patch(
            comment_reaction_nested_url(self.comment.id), {"vote": "LIKE"}, format="json"
        )
        self.assertEqual(response.data["comment"], self.comment.id)
        self.assertEqual(response.data["user"]["username"], self.user.username)
