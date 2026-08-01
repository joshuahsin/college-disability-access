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
    def is_disputed(self):
        """True once disputes hold a strict majority of votes cast so far."""
        return self.dispute_count > self.confirm_count

    @property
    def effective_claim(self):
        """
        Live, non-destructive majority-vote view of `claim`. Starts equal to
        the reporter's original claim at 0 votes, flips once disputes take
        a strict majority, and flips back if confirms regain it. `claim`
        itself is never mutated -- this is always recomputed from the
        current vote tally, so it's fully reversible and the original
        report stays intact for audit purposes.
        """
        return (not self.claim) if self.is_disputed else self.claim


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
