from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Campus, Comment, Confirmation, Feature, Submission, Venue
from .permissions import IsAuthenticatedOrReadOnly, IsAuthorOrReadOnly
from .serializers import (
    CampusSerializer,
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
        queryset = Venue.objects.select_related("campus").all()
        campus_id = self.request.query_params.get("campus")
        category = self.request.query_params.get("category")
        if campus_id:
            queryset = queryset.filter(campus_id=campus_id)
        if category:
            queryset = queryset.filter(category=category)
        return queryset


class FeatureViewSet(viewsets.ModelViewSet):
    queryset = Feature.objects.all()
    serializer_class = FeatureSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]


class SubmissionViewSet(viewsets.ModelViewSet):
    serializer_class = SubmissionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = Submission.objects.select_related("venue", "feature", "reporter").all()
        venue_id = self.request.query_params.get("venue")
        feature_id = self.request.query_params.get("feature")
        if venue_id:
            queryset = queryset.filter(venue_id=venue_id)
        if feature_id:
            queryset = queryset.filter(feature_id=feature_id)
        return queryset

    @action(detail=False, methods=["get"])
    def latest(self, request):
        """
        Returns the most recent submission for a given venue + feature pair,
        the "displayed by default" submission per the product rules. Both
        query params are required.
        """
        venue_id = request.query_params.get("venue")
        feature_id = request.query_params.get("feature")
        if not venue_id or not feature_id:
            return Response(
                {"detail": "Both `venue` and `feature` query params are required."},
                status=400,
            )
        submission = (
            Submission.objects.filter(venue_id=venue_id, feature_id=feature_id)
            .select_related("venue", "feature", "reporter")
            .first()
        )
        if submission is None:
            return Response(
                {"detail": "No submission found for this venue/feature."}, status=404
            )
        return Response(self.get_serializer(submission).data)


class ConfirmationViewSet(viewsets.ModelViewSet):
    serializer_class = ConfirmationSerializer
    permission_classes = [permissions.IsAuthenticated]

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
        queryset = Comment.objects.select_related("submission", "user").all()
        submission_id = self.request.query_params.get("submission")
        if submission_id:
            queryset = queryset.filter(submission_id=submission_id)
        return queryset
