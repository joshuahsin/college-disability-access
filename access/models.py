import uuid

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class UserManager(BaseUserManager):
    def create_user(self, username, password=None, **extra_fields):
        if not username:
            raise ValueError("Username is required")
        user = self.model(username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(username, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    `password` (inherited from AbstractBaseUser) stores the hashed password
    and corresponds to the `hashedPassword` field in the spec -- Django never
    stores or accepts a raw password in that field.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(max_length=150, unique=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.username


class Campus(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Venue(models.Model):
    class Category(models.TextChoices):
        DINING = "dining", "Dining"
        ACADEMIC = "academic", "Academic"
        DORM = "dorm", "Dorm"
        LIBRARY = "library", "Library"
        REC = "rec", "Recreation"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campus = models.ForeignKey(Campus, related_name="venues", on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=500, blank=True, default="")
    latitude = models.FloatField(validators=[MinValueValidator(-90.0), MaxValueValidator(90.0)])
    longitude = models.FloatField(validators=[MinValueValidator(-180.0), MaxValueValidator(180.0)])
    category = models.CharField(max_length=20, choices=Category.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["campus", "name"], name="unique_venue_name_per_campus"),
        ]

    def __str__(self):
        return f"{self.name} ({self.campus.name})"


class Feature(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Submission(models.Model):
    """
    One persistent topic per (venue, feature) pair -- not a claim, just the
    fact that "does this venue have this feature" is being tracked. There is
    no assertion to agree or disagree with; `status` is a pure, live tally
    of direct votes (see Confirmation.Vote) for one state or the other.
    `reporter` only records who first flagged this pair as worth tracking --
    it carries no extra weight in the outcome versus anyone else's vote.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED_ACCESSIBLE = "confirmed_accessible", "Confirmed Accessible"
        CONFIRMED_INACCESSIBLE = "confirmed_inaccessible", "Confirmed Inaccessible"
        DISPUTED = "disputed", "Disputed"

    # Below this many total votes, there isn't enough signal to say
    # anything beyond "pending" -- even a unanimous 2-0 stays pending.
    MIN_VOTES_FOR_RESOLUTION = 3
    # A side must hold at least this share of votes to count as resolved.
    # Anything short of it (including a bare majority) reads as `DISPUTED`
    # rather than confidently declaring a winner off a razor-thin split.
    CONFIDENCE_THRESHOLD = 0.65

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    venue = models.ForeignKey(Venue, related_name="submissions", on_delete=models.CASCADE)
    feature = models.ForeignKey(Feature, related_name="submissions", on_delete=models.CASCADE)
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="submissions", on_delete=models.CASCADE
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["venue", "feature"], name="unique_submission_per_venue_feature"),
        ]

    def __str__(self):
        return f"{self.venue_id}/{self.feature_id}"

    @property
    def accessible_count(self):
        # Counts in Python over `.all()` rather than `.filter().count()` so
        # that a prefetch_related("confirmations") upstream (e.g. listing
        # venues with their submissions) is actually reused instead of
        # triggering a fresh query per submission.
        return sum(1 for c in self.confirmations.all() if c.vote == Confirmation.Vote.ACCESSIBLE)

    @property
    def inaccessible_count(self):
        return sum(
            1 for c in self.confirmations.all() if c.vote == Confirmation.Vote.NOT_ACCESSIBLE
        )

    @property
    def total_votes(self):
        return self.accessible_count + self.inaccessible_count

    @property
    def status(self):
        """Live vote tally -- recomputed on every access, nothing stored."""
        total = self.total_votes
        if total < self.MIN_VOTES_FOR_RESOLUTION:
            return self.Status.PENDING
        if self.accessible_count / total >= self.CONFIDENCE_THRESHOLD:
            return self.Status.CONFIRMED_ACCESSIBLE
        if self.inaccessible_count / total >= self.CONFIDENCE_THRESHOLD:
            return self.Status.CONFIRMED_INACCESSIBLE
        return self.Status.DISPUTED


class Confirmation(models.Model):
    class Vote(models.TextChoices):
        ACCESSIBLE = "ACCESSIBLE", "Accessible"
        NOT_ACCESSIBLE = "NOT_ACCESSIBLE", "Not Accessible"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    submission = models.ForeignKey(
        Submission, related_name="confirmations", on_delete=models.CASCADE
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="confirmations", on_delete=models.CASCADE
    )
    vote = models.CharField(max_length=14, choices=Vote.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["submission", "user"], name="unique_confirmation_per_user"),
        ]

    def __str__(self):
        return f"{self.user_id} -> {self.submission_id}: {self.vote}"


class Comment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    submission = models.ForeignKey(Submission, related_name="comments", on_delete=models.CASCADE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="comments", on_delete=models.CASCADE
    )
    # Null for a top-level comment; set for a reply. Replies are capped at
    # one level deep (enforced in CommentSerializer, not here) -- a reply's
    # own `parent` field is always null.
    parent = models.ForeignKey(
        "self", null=True, blank=True, related_name="replies", on_delete=models.CASCADE
    )
    body = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.user_id} on {self.submission_id}: {self.body[:30]}"

    @property
    def like_count(self):
        # Iterate over `.all()` rather than `.filter().count()` so a
        # prefetch_related("reactions") upstream is reused, same reasoning
        # as Submission.accessible_count above.
        return sum(1 for r in self.reactions.all() if r.vote == CommentReaction.Vote.LIKE)

    @property
    def dislike_count(self):
        return sum(1 for r in self.reactions.all() if r.vote == CommentReaction.Vote.DISLIKE)


class CommentReaction(models.Model):
    """
    A like/dislike on a Comment -- purely a transparent, displayed count.
    Never auto-hides or re-sorts a comment; same non-destructive philosophy
    as Submission.status. One vote per user per comment (see Confirmation,
    which this mirrors exactly, including the idempotent-vote upsert
    behavior in CommentReactionSerializer.create()).
    """

    class Vote(models.TextChoices):
        LIKE = "LIKE", "Like"
        DISLIKE = "DISLIKE", "Dislike"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    comment = models.ForeignKey(Comment, related_name="reactions", on_delete=models.CASCADE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="comment_reactions", on_delete=models.CASCADE
    )
    vote = models.CharField(max_length=7, choices=Vote.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["comment", "user"], name="unique_reaction_per_user"),
        ]

    def __str__(self):
        return f"{self.user_id} -> {self.comment_id}: {self.vote}"
