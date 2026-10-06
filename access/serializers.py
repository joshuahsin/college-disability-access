from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Campus, Comment, CommentReaction, Confirmation, Feature, Submission, Venue

User = get_user_model()


class UserRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ["id", "username", "password", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def create(self, validated_data):
        return User.objects.create_user(
            username=validated_data["username"], password=validated_data["password"]
        )


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "created_at", "updated_at"]
        read_only_fields = fields


class CampusSerializer(serializers.ModelSerializer):
    class Meta:
        model = Campus
        fields = ["id", "name", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class VenueSerializer(serializers.ModelSerializer):
    status_summary = serializers.SerializerMethodField()

    class Meta:
        model = Venue
        fields = [
            "id",
            "campus",
            "name",
            "address",
            "latitude",
            "longitude",
            "category",
            "status_summary",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
        validators = [
            serializers.UniqueTogetherValidator(
                queryset=Venue.objects.all(),
                fields=["campus", "name"],
                message="A venue with this name already exists on this campus.",
            )
        ]

    def get_status_summary(self, venue):
        """
        How many of this venue's Submission topics currently fall into each
        live status. Relies on the view's prefetch of submissions (and
        their confirmations) to stay cheap across a list of venues.
        """
        counts = dict.fromkeys(Submission.Status.values, 0)
        for submission in venue.submissions.all():
            counts[submission.status] += 1
        return counts

    def create(self, validated_data):
        """
        A new venue isn't useful until it has something to vote/comment on
        for every existing feature, so seed a Submission topic per existing
        feature, attributed to the staff user who added the venue.
        """
        venue = super().create(validated_data)
        reporter = self.context["request"].user
        for feature in Feature.objects.all():
            Submission.objects.create(venue=venue, feature=feature, reporter=reporter)
        return venue


class FeatureSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feature
        fields = ["id", "name", "description", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def create(self, validated_data):
        """
        Symmetric to VenueSerializer.create(): a new feature isn't useful
        until every existing venue has a Submission topic for it.
        """
        feature = super().create(validated_data)
        reporter = self.context["request"].user
        for venue in Venue.objects.all():
            Submission.objects.create(venue=venue, feature=feature, reporter=reporter)
        return feature


class SubmissionSerializer(serializers.ModelSerializer):
    reporter = UserSerializer(read_only=True)
    accessible_count = serializers.IntegerField(read_only=True)
    inaccessible_count = serializers.IntegerField(read_only=True)
    status = serializers.ChoiceField(choices=Submission.Status.choices, read_only=True)

    class Meta:
        model = Submission
        fields = [
            "id",
            "venue",
            "feature",
            "reporter",
            "status",
            "accessible_count",
            "inaccessible_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "reporter", "created_at", "updated_at"]
        validators = [
            serializers.UniqueTogetherValidator(
                queryset=Submission.objects.all(),
                fields=["venue", "feature"],
                message="A submission for this venue/feature pair already exists.",
            )
        ]

    def create(self, validated_data):
        validated_data["reporter"] = self.context["request"].user
        return super().create(validated_data)


class ConfirmationSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = Confirmation
        fields = ["id", "submission", "user", "vote", "created_at", "updated_at"]
        read_only_fields = ["id", "user", "created_at", "updated_at"]

    def create(self, validated_data):
        """
        Casting a vote is idempotent per (submission, user): re-casting the
        same vote is a no-op, casting the opposite vote switches it in
        place, and a first-time vote creates a new row. This keeps the
        (submission, user) unique constraint satisfied without ever
        rejecting a repeat click from the same user.
        """
        request = self.context["request"]
        submission = validated_data["submission"]
        vote = validated_data["vote"]
        existing = Confirmation.objects.filter(submission=submission, user=request.user).first()
        if existing is not None:
            if existing.vote != vote:
                existing.vote = vote
                existing.save(update_fields=["vote", "updated_at"])
            return existing
        return Confirmation.objects.create(submission=submission, user=request.user, vote=vote)


class CommentSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    like_count = serializers.IntegerField(read_only=True)
    dislike_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Comment
        fields = [
            "id",
            "submission",
            "user",
            "parent",
            "body",
            "like_count",
            "dislike_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "user", "created_at", "updated_at"]

    def validate_body(self, value):
        stripped = value.strip()
        if not stripped:
            raise serializers.ValidationError("Comment body cannot be empty.")
        return stripped

    def validate(self, attrs):
        parent = attrs.get("parent")
        if parent is not None:
            if parent.parent_id is not None:
                raise serializers.ValidationError(
                    {"parent": "Cannot reply to a reply -- replies are limited to one level deep."}
                )
            submission = attrs.get("submission", getattr(self.instance, "submission", None))
            if submission is not None and parent.submission_id != submission.id:
                raise serializers.ValidationError(
                    {"parent": "Parent comment must belong to the same submission."}
                )
        return attrs

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)


class CommentReactionSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = CommentReaction
        fields = ["id", "comment", "user", "vote", "created_at", "updated_at"]
        read_only_fields = ["id", "user", "created_at", "updated_at"]

    def create(self, validated_data):
        """
        Same idempotent-vote upsert as ConfirmationSerializer: re-casting
        the same reaction is a no-op, switching (like <-> dislike) updates
        the existing row in place, and a first-time reaction creates one.
        """
        request = self.context["request"]
        comment = validated_data["comment"]
        vote = validated_data["vote"]
        existing = CommentReaction.objects.filter(comment=comment, user=request.user).first()
        if existing is not None:
            if existing.vote != vote:
                existing.vote = vote
                existing.save(update_fields=["vote", "updated_at"])
            return existing
        return CommentReaction.objects.create(comment=comment, user=request.user, vote=vote)
