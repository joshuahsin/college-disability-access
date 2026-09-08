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
    claim = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.venue_id}/{self.feature_id}: {self.claim}"

    @property
    def confirm_count(self):
        return self.confirmations.filter(vote=Confirmation.Vote.CONFIRM).count()

    @property
    def dispute_count(self):
        return self.confirmations.filter(vote=Confirmation.Vote.DISPUTE).count()

    @property
    def total_votes(self):
        return self.confirm_count + self.dispute_count

    @property
    def dispute_rate(self):
        total = self.total_votes
        if total == 0:
            return 0.0
        return self.dispute_count / total

    @property
    def status(self):
        """
        Live, non-destructive vote-tally status. `claim` itself is never
        mutated -- this is always recomputed from the current vote tally,
        so it's fully reversible as more votes come in.
        """
        total = self.total_votes
        if total < self.MIN_VOTES_FOR_RESOLUTION:
            return self.Status.PENDING
        confirm_share = self.confirm_count / total
        dispute_share = self.dispute_count / total
        if confirm_share >= self.CONFIDENCE_THRESHOLD:
            return self.Status.CONFIRMED_ACCESSIBLE if self.claim else self.Status.CONFIRMED_INACCESSIBLE
        if dispute_share >= self.CONFIDENCE_THRESHOLD:
            return self.Status.CONFIRMED_INACCESSIBLE if self.claim else self.Status.CONFIRMED_ACCESSIBLE
        return self.Status.DISPUTED


class Confirmation(models.Model):
    class Vote(models.TextChoices):
        CONFIRM = "CONFIRM", "Confirm"
        DISPUTE = "DISPUTE", "Dispute"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    submission = models.ForeignKey(
        Submission, related_name="confirmations", on_delete=models.CASCADE
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="confirmations", on_delete=models.CASCADE
    )
    vote = models.CharField(max_length=10, choices=Vote.choices)
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
    body = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.user_id} on {self.submission_id}: {self.body[:30]}"
