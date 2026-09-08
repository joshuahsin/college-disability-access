from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Campus, Comment, Confirmation, Feature, Submission, Venue

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


class FeatureSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feature
        fields = ["id", "name", "description", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class SubmissionSerializer(serializers.ModelSerializer):
    reporter = UserSerializer(read_only=True)
    confirm_count = serializers.IntegerField(read_only=True)
    dispute_count = serializers.IntegerField(read_only=True)
    dispute_rate = serializers.FloatField(read_only=True)
    status = serializers.ChoiceField(choices=Submission.Status.choices, read_only=True)

    class Meta:
        model = Submission
        fields = [
            "id",
            "venue",
            "feature",
            "reporter",
            "claim",
            "status",
            "confirm_count",
            "dispute_count",
            "dispute_rate",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "reporter", "created_at", "updated_at"]

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

    class Meta:
        model = Comment
        fields = ["id", "submission", "user", "body", "created_at", "updated_at"]
        read_only_fields = ["id", "user", "created_at", "updated_at"]

    def validate_body(self, value):
        stripped = value.strip()
        if not stripped:
            raise serializers.ValidationError("Comment body cannot be empty.")
        return stripped

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)
