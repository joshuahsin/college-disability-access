from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from rest_framework import generics, mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Campus, Comment, CommentReaction, Confirmation, Feature, Submission, Venue
from .permissions import IsAuthenticatedOrReadOnly, IsAuthorOrReadOnly, IsStaffOrReadOnly
from .serializers import (
    CampusSerializer,
    CommentReactionSerializer,
    CommentSerializer,
    ConfirmationSerializer,
    FeatureSerializer,
    SubmissionSerializer,
    UserRegisterSerializer,
    VenueSerializer,
)


class RegisterView(generics.CreateAPIView):
    serializer_class = UserRegisterSerializer
    permission_classes = [permissions.AllowAny]


class CampusViewSet(viewsets.ModelViewSet):
    queryset = Campus.objects.all()
    serializer_class = CampusSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]


class VenueViewSet(viewsets.ModelViewSet):
    serializer_class = VenueSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        """
        `status_summary` on the serializer needs every submission's live
        `status`, which itself needs that submission's votes -- prefetch
        both levels here so listing N venues costs 3 queries total (venues,
        submissions, confirmations) instead of 1 + 2N.
        """
        queryset = Venue.objects.select_related("campus").prefetch_related(
            Prefetch(
                "submissions",
                queryset=Submission.objects.prefetch_related("confirmations"),
            )
        )
        campus_id = self.request.query_params.get("campus")
        category = self.request.query_params.get("category")
        if campus_id:
            queryset = queryset.filter(campus_id=campus_id)
        if category:
            queryset = queryset.filter(category=category)
        return queryset


class FeatureViewSet(viewsets.ModelViewSet):
    """
    Only staff can create/update/delete features -- Feature is a shared,
    curated vocabulary (Ramp, Elevator, ...), not something every user
    should be able to freely add to and risk near-duplicate sprawl in.
    """

    queryset = Feature.objects.all()
    serializer_class = FeatureSerializer
    permission_classes = [IsStaffOrReadOnly]


class SubmissionViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    No update support: a Submission has no field left worth editing once
    created (venue/feature shouldn't be reassigned after the fact, and
    there's no claim to revise -- `status` is a live vote tally, not
    something anyone sets directly). Only staff can create/delete;
    any authenticated user can read (required to vote/comment on it) via
    Confirmation/Comment, which remain open to all authenticated users.
    """

    serializer_class = SubmissionSerializer
    permission_classes = [permissions.IsAuthenticated, IsStaffOrReadOnly]

    def get_queryset(self):
        queryset = Submission.objects.select_related("venue", "feature", "reporter").all()
        venue_id = self.request.query_params.get("venue")
        feature_id = self.request.query_params.get("feature")
        if venue_id:
            queryset = queryset.filter(venue_id=venue_id)
        if feature_id:
            queryset = queryset.filter(feature_id=feature_id)
        return queryset


class ConfirmationViewSet(viewsets.ModelViewSet):
    serializer_class = ConfirmationSerializer
    permission_classes = [permissions.IsAuthenticated, IsAuthorOrReadOnly]

    def get_queryset(self):
        queryset = Confirmation.objects.select_related("submission", "user").all()
        submission_id = self.request.query_params.get("submission")
        if submission_id:
            queryset = queryset.filter(submission_id=submission_id)
        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        already_voted = Confirmation.objects.filter(
            submission=serializer.validated_data["submission"], user=request.user
        ).exists()
        instance = serializer.save()
        response_status = status.HTTP_200_OK if already_voted else status.HTTP_201_CREATED
        return Response(self.get_serializer(instance).data, status=response_status)


class CommentViewSet(viewsets.ModelViewSet):
    serializer_class = CommentSerializer
    permission_classes = [permissions.IsAuthenticated, IsAuthorOrReadOnly]

    def get_queryset(self):
        queryset = Comment.objects.select_related(
            "submission", "user", "parent"
        ).prefetch_related("reactions")
        submission_id = self.request.query_params.get("submission")
        if submission_id:
            queryset = queryset.filter(submission_id=submission_id)
        parent_id = self.request.query_params.get("parent")
        if parent_id:
            queryset = queryset.filter(parent_id=parent_id)
        return queryset

    @action(detail=True, methods=["patch"], url_path="reaction")
    def reaction(self, request, pk=None):
        """
        PATCH /api/comments/<comment_id>/reaction/ -- upsert "my reaction"
        to this comment, identified by (comment, request.user) rather than
        the CommentReaction's own id, so the client never needs to look one
        up first. Body is just {"vote": "LIKE"|"DISLIKE"} -- no comment or
        user field, same trust boundary as everywhere else in this API.

        Deliberately fetches via get_queryset() instead of get_object():
        get_object() would run this view's own IsAuthorOrReadOnly check,
        which guards editing the *comment* and would wrongly require the
        requester to be the comment's author -- reacting to someone else's
        comment is the whole point.
        """
        comment = get_object_or_404(self.get_queryset(), pk=pk)
        serializer = CommentReactionSerializer(
            data={**request.data, "comment": str(comment.id)},
            context=self.get_serializer_context(),
        )
        serializer.is_valid(raise_exception=True)
        already_reacted = CommentReaction.objects.filter(
            comment=comment, user=request.user
        ).exists()
        instance = serializer.save()
        response_status = status.HTTP_200_OK if already_reacted else status.HTTP_201_CREATED
        return Response(
            CommentReactionSerializer(instance, context=self.get_serializer_context()).data,
            status=response_status,
        )


class CommentReactionViewSet(viewsets.ModelViewSet):
    serializer_class = CommentReactionSerializer
    permission_classes = [permissions.IsAuthenticated, IsAuthorOrReadOnly]

    def get_queryset(self):
        queryset = CommentReaction.objects.select_related("comment", "user").all()
        comment_id = self.request.query_params.get("comment")
        if comment_id:
            queryset = queryset.filter(comment_id=comment_id)
        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        already_reacted = CommentReaction.objects.filter(
            comment=serializer.validated_data["comment"], user=request.user
        ).exists()
        instance = serializer.save()
        response_status = status.HTTP_200_OK if already_reacted else status.HTTP_201_CREATED
        return Response(self.get_serializer(instance).data, status=response_status)
