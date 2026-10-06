from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from access.models import Campus, Comment, CommentReaction, Confirmation, Feature, Submission, Venue

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Seed the database with demo users, campuses, venues, features, "
        "submissions, confirmations, and comments. Safe to re-run."
    )

    def handle(self, *args, **options):
        with transaction.atomic():
            users = self._seed_users()
            campuses = self._seed_campuses()
            venues = self._seed_venues(campuses)
            features = self._seed_features()
            submissions = self._seed_submissions(users, venues, features)
            self._seed_confirmations(users, submissions)
            comments = self._seed_comments(users, submissions)
            self._seed_comment_reactions(users, comments)

        self.stdout.write(self.style.SUCCESS("Seed complete."))
        self.stdout.write(
            f"  {User.objects.count()} users, {Campus.objects.count()} campuses, "
            f"{Venue.objects.count()} venues, {Feature.objects.count()} features, "
            f"{Submission.objects.count()} submissions, "
            f"{Confirmation.objects.count()} confirmations, "
            f"{Comment.objects.count()} comments, "
            f"{CommentReaction.objects.count()} comment reactions"
        )

    # ---- users -----------------------------------------------------

    def _seed_users(self):
        self.stdout.write("Seeding users...")
        # (username, password, is_staff, is_superuser)
        specs = [
            ("admin", "AdminPass123!", True, True),
            ("alice", "AlicePass123!", False, False),
            ("bob", "BobPass123!", False, False),
            ("carol", "CarolPass123!", False, False),
            ("dave", "DavePass123!", False, False),
        ]
        users = {}
        for username, password, is_staff, is_superuser in specs:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"is_staff": is_staff, "is_superuser": is_superuser},
            )
            if created:
                user.set_password(password)
                user.save(update_fields=["password"])
                self.stdout.write(f"  created user: {username}")
            users[username] = user
        return users

    # ---- campuses ----------------------------------------------------

    def _seed_campuses(self):
        self.stdout.write("Seeding campuses...")
        campuses = {}
        for name in ["UC Irvine", "UC Los Angeles"]:
            campus, created = Campus.objects.get_or_create(name=name)
            if created:
                self.stdout.write(f"  created campus: {name}")
            campuses[name] = campus
        return campuses

    # ---- venues ------------------------------------------------------

    def _seed_venues(self, campuses):
        self.stdout.write("Seeding venues...")
        # (campus, name, address, latitude, longitude, category)
        specs = [
            ("UC Irvine", "Langson Library", "391 Library Rd, Irvine, CA",
             33.6403, -117.8420, Venue.Category.LIBRARY),
            ("UC Irvine", "Anteatery", "608 E Peltason Dr, Irvine, CA",
             33.6461, -117.8427, Venue.Category.DINING),
            ("UC Irvine", "Middle Earth Housing", "260 Middle Earth, Irvine, CA",
             33.6472, -117.8420, Venue.Category.DORM),
            ("UC Irvine", "Anteater Recreation Center", "680 California Ave, Irvine, CA",
             33.6435, -117.8330, Venue.Category.REC),
            ("UC Irvine", "Donald Bren Hall", "6210 Donald Bren Hall, Irvine, CA",
             33.6416, -117.8425, Venue.Category.ACADEMIC),
            ("UC Los Angeles", "Powell Library", "10740 Dickson Plaza, Los Angeles, CA",
             34.0722, -118.4421, Venue.Category.LIBRARY),
            ("UC Los Angeles", "De Neve Dining", "451 Charles E Young Dr W, Los Angeles, CA",
             34.0708, -118.4508, Venue.Category.DINING),
            ("UC Los Angeles", "Sproul Hall", "550 De Neve Dr, Los Angeles, CA",
             34.0715, -118.4512, Venue.Category.DORM),
            ("UC Los Angeles", "John Wooden Center", "221 Westwood Plaza, Los Angeles, CA",
             34.0700, -118.4472, Venue.Category.REC),
            ("UC Los Angeles", "Royce Hall", "10745 Dickson Plaza, Los Angeles, CA",
             34.0733, -118.4422, Venue.Category.ACADEMIC),
        ]
        venues = {}
        for campus_name, name, address, lat, lng, category in specs:
            venue, created = Venue.objects.get_or_create(
                campus=campuses[campus_name],
                name=name,
                defaults={
                    "address": address,
                    "latitude": lat,
                    "longitude": lng,
                    "category": category,
                },
            )
            if created:
                self.stdout.write(f"  created venue: {name} ({campus_name})")
            venues[(campus_name, name)] = venue
        return venues

    # ---- features ------------------------------------------------------

    def _seed_features(self):
        self.stdout.write("Seeding features...")
        specs = [
            ("Ramp", "Wheelchair-accessible ramp entrance."),
            ("Elevator", "Elevator providing access between floors."),
            ("Braille Signage", "Braille signage for wayfinding and room identification."),
            ("Accessible Restroom", "Restroom with an accessible stall and fixtures."),
        ]
        features = {}
        for name, description in specs:
            feature, created = Feature.objects.get_or_create(
                name=name, defaults={"description": description}
            )
            if created:
                self.stdout.write(f"  created feature: {name}")
            features[name] = feature
        return features

    # ---- submissions ---------------------------------------------------

    def _get_or_create_submission(self, venue, feature, reporter):
        """
        A Submission is a topic, not a claim -- unique per (venue, feature),
        so get_or_create on that pair is naturally idempotent. `reporter`
        just records who first flagged it as worth tracking.
        """
        submission, created = Submission.objects.get_or_create(
            venue=venue, feature=feature, defaults={"reporter": reporter}
        )
        if created:
            self.stdout.write(
                f"  created submission: {venue.name}/{feature.name} "
                f"(flagged by {reporter.username})"
            )
        return submission

    def _seed_submissions(self, users, venues, features):
        self.stdout.write("Seeding submissions...")
        alice, bob, carol, dave = users["alice"], users["bob"], users["carol"], users["dave"]
        uci = "UC Irvine"
        ucla = "UC Los Angeles"

        submissions = {}

        # Langson Library is the single-venue demo: all four Submission
        # statuses show up across its four features, so opening this one
        # venue is enough to see the full range at a glance.
        submissions["langson_ramp"] = self._get_or_create_submission(
            venues[(uci, "Langson Library")], features["Ramp"], bob
        )
        submissions["langson_elevator"] = self._get_or_create_submission(
            venues[(uci, "Langson Library")], features["Elevator"], alice
        )
        submissions["langson_braille"] = self._get_or_create_submission(
            venues[(uci, "Langson Library")], features["Braille Signage"], carol
        )
        submissions["langson_restroom"] = self._get_or_create_submission(
            venues[(uci, "Langson Library")], features["Accessible Restroom"], dave
        )

        # Boundary not-accessible (66.7%): resolves CONFIRMED_INACCESSIBLE.
        submissions["anteatery_restroom"] = self._get_or_create_submission(
            venues[(uci, "Anteatery")], features["Accessible Restroom"], carol
        )

        # Only 2 votes cast: stays PENDING regardless of split.
        submissions["middleearth_elevator"] = self._get_or_create_submission(
            venues[(uci, "Middle Earth Housing")], features["Elevator"], dave
        )

        # Zero votes: baseline PENDING case, plus comments.
        submissions["brenhall_braille"] = self._get_or_create_submission(
            venues[(uci, "Donald Bren Hall")], features["Braille Signage"], alice
        )

        # Comment thread, no votes yet.
        submissions["arc_ramp"] = self._get_or_create_submission(
            venues[(uci, "Anteater Recreation Center")], features["Ramp"], bob
        )

        # Even split (2-2): resolves DISPUTED, not a coin-flip winner.
        submissions["powell_elevator"] = self._get_or_create_submission(
            venues[(ucla, "Powell Library")], features["Elevator"], alice
        )

        # Unanimous not-accessible votes: resolves CONFIRMED_INACCESSIBLE.
        submissions["deneve_restroom"] = self._get_or_create_submission(
            venues[(ucla, "De Neve Dining")], features["Accessible Restroom"], carol
        )

        # Zero votes, zero comments: plain baseline.
        submissions["sproul_braille"] = self._get_or_create_submission(
            venues[(ucla, "Sproul Hall")], features["Braille Signage"], dave
        )

        # Comment thread, no votes yet.
        submissions["wooden_ramp"] = self._get_or_create_submission(
            venues[(ucla, "John Wooden Center")], features["Ramp"], bob
        )

        # Boundary accessible (66.7%): resolves CONFIRMED_ACCESSIBLE.
        submissions["royce_elevator"] = self._get_or_create_submission(
            venues[(ucla, "Royce Hall")], features["Elevator"], alice
        )

        # Bare majority (60%) short of the 65% bar: resolves DISPUTED.
        submissions["anteatery_ramp"] = self._get_or_create_submission(
            venues[(uci, "Anteatery")], features["Ramp"], carol
        )

        # Rounds out per-feature coverage: without these, Accessible
        # Restroom never resolves CONFIRMED_ACCESSIBLE anywhere, and Braille
        # Signage never resolves CONFIRMED_INACCESSIBLE anywhere.
        submissions["wooden_restroom"] = self._get_or_create_submission(
            venues[(ucla, "John Wooden Center")], features["Accessible Restroom"], carol
        )
        submissions["powell_braille"] = self._get_or_create_submission(
            venues[(ucla, "Powell Library")], features["Braille Signage"], dave
        )

        return submissions

    # ---- confirmations -----------------------------------------------

    def _cast_vote(self, submission, user, vote):
        _, created = Confirmation.objects.get_or_create(
            submission=submission, user=user, defaults={"vote": vote}
        )
        if created:
            self.stdout.write(f"  {user.username} voted {vote} on {submission.feature.name}")

    def _seed_confirmations(self, users, submissions):
        """
        Vote tallies here are chosen to demonstrate every Submission.status
        value under the current rules (MIN_VOTES_FOR_RESOLUTION=3,
        CONFIDENCE_THRESHOLD=0.65 -- see access/models.py):
          - PENDING: 0 votes, or some votes but below the 3-vote floor
          - CONFIRMED_ACCESSIBLE / CONFIRMED_INACCESSIBLE: one side clears
            65% confidence, both at the exact boundary (2-1 = 66.7%) and
            decisively (3-0, 3-1)
          - DISPUTED: enough votes exist but neither side clears 65%,
            both as an even split and as a bare-majority miss (3-2 = 60%)
        The Langson Library submissions specifically are set up so all four
        statuses appear across its four features in one place.
        """
        self.stdout.write("Seeding confirmations...")
        alice, bob, carol, dave, admin = (
            users["alice"], users["bob"], users["carol"], users["dave"], users["admin"],
        )

        # Langson Library / Ramp: unanimous 3-0 accessible ->
        # CONFIRMED_ACCESSIBLE.
        self._cast_vote(submissions["langson_ramp"], carol, Confirmation.Vote.ACCESSIBLE)
        self._cast_vote(submissions["langson_ramp"], dave, Confirmation.Vote.ACCESSIBLE)
        self._cast_vote(submissions["langson_ramp"], admin, Confirmation.Vote.ACCESSIBLE)

        # Langson Library / Elevator: unanimous 3-0 not-accessible ->
        # CONFIRMED_INACCESSIBLE.
        self._cast_vote(submissions["langson_elevator"], bob, Confirmation.Vote.NOT_ACCESSIBLE)
        self._cast_vote(submissions["langson_elevator"], carol, Confirmation.Vote.NOT_ACCESSIBLE)
        self._cast_vote(submissions["langson_elevator"], dave, Confirmation.Vote.NOT_ACCESSIBLE)

        # Langson Library / Braille Signage: even 2-2 split -> DISPUTED.
        self._cast_vote(submissions["langson_braille"], alice, Confirmation.Vote.ACCESSIBLE)
        self._cast_vote(submissions["langson_braille"], bob, Confirmation.Vote.ACCESSIBLE)
        self._cast_vote(submissions["langson_braille"], dave, Confirmation.Vote.NOT_ACCESSIBLE)
        self._cast_vote(submissions["langson_braille"], admin, Confirmation.Vote.NOT_ACCESSIBLE)

        # Langson Library / Accessible Restroom: zero votes -> PENDING.
        # (intentionally no votes cast)

        # 2-1 not-accessible (66.7%) -> right at the confidence boundary ->
        # CONFIRMED_INACCESSIBLE.
        self._cast_vote(submissions["anteatery_restroom"], alice, Confirmation.Vote.NOT_ACCESSIBLE)
        self._cast_vote(submissions["anteatery_restroom"], bob, Confirmation.Vote.NOT_ACCESSIBLE)
        self._cast_vote(submissions["anteatery_restroom"], dave, Confirmation.Vote.ACCESSIBLE)

        # Only 2 total votes -> below the 3-vote floor -> PENDING, even
        # though it's not unanimous either.
        self._cast_vote(submissions["middleearth_elevator"], alice, Confirmation.Vote.ACCESSIBLE)
        self._cast_vote(submissions["middleearth_elevator"], bob, Confirmation.Vote.NOT_ACCESSIBLE)

        # 2-2 even split -> neither side clears 65% -> DISPUTED.
        self._cast_vote(submissions["powell_elevator"], bob, Confirmation.Vote.ACCESSIBLE)
        self._cast_vote(submissions["powell_elevator"], carol, Confirmation.Vote.ACCESSIBLE)
        self._cast_vote(submissions["powell_elevator"], dave, Confirmation.Vote.NOT_ACCESSIBLE)
        self._cast_vote(submissions["powell_elevator"], admin, Confirmation.Vote.NOT_ACCESSIBLE)

        # Unanimous 3-0 not-accessible -> CONFIRMED_INACCESSIBLE.
        self._cast_vote(submissions["deneve_restroom"], alice, Confirmation.Vote.NOT_ACCESSIBLE)
        self._cast_vote(submissions["deneve_restroom"], bob, Confirmation.Vote.NOT_ACCESSIBLE)
        self._cast_vote(submissions["deneve_restroom"], dave, Confirmation.Vote.NOT_ACCESSIBLE)

        # 3-1 not-accessible (75%) -> decisively past the boundary,
        # contrasts with anteatery_restroom's narrower 66.7% case ->
        # CONFIRMED_INACCESSIBLE.
        self._cast_vote(submissions["wooden_ramp"], alice, Confirmation.Vote.NOT_ACCESSIBLE)
        self._cast_vote(submissions["wooden_ramp"], carol, Confirmation.Vote.NOT_ACCESSIBLE)
        self._cast_vote(submissions["wooden_ramp"], dave, Confirmation.Vote.NOT_ACCESSIBLE)
        self._cast_vote(submissions["wooden_ramp"], admin, Confirmation.Vote.ACCESSIBLE)

        # 2-1 accessible (66.7%) -> accessible-side mirror of
        # anteatery_restroom's boundary case -> CONFIRMED_ACCESSIBLE.
        self._cast_vote(submissions["royce_elevator"], carol, Confirmation.Vote.ACCESSIBLE)
        self._cast_vote(submissions["royce_elevator"], bob, Confirmation.Vote.ACCESSIBLE)
        self._cast_vote(submissions["royce_elevator"], dave, Confirmation.Vote.NOT_ACCESSIBLE)

        # 3-2 accessible (60%) -- a real majority, but short of the 65%
        # confidence bar -> stays DISPUTED rather than confidently
        # resolving off a razor-thin margin.
        self._cast_vote(submissions["anteatery_ramp"], alice, Confirmation.Vote.ACCESSIBLE)
        self._cast_vote(submissions["anteatery_ramp"], bob, Confirmation.Vote.ACCESSIBLE)
        self._cast_vote(submissions["anteatery_ramp"], carol, Confirmation.Vote.ACCESSIBLE)
        self._cast_vote(submissions["anteatery_ramp"], dave, Confirmation.Vote.NOT_ACCESSIBLE)
        self._cast_vote(submissions["anteatery_ramp"], admin, Confirmation.Vote.NOT_ACCESSIBLE)

        # Unanimous 3-0 accessible -> CONFIRMED_ACCESSIBLE (Accessible
        # Restroom's only resolved-accessible example).
        self._cast_vote(submissions["wooden_restroom"], alice, Confirmation.Vote.ACCESSIBLE)
        self._cast_vote(submissions["wooden_restroom"], bob, Confirmation.Vote.ACCESSIBLE)
        self._cast_vote(submissions["wooden_restroom"], dave, Confirmation.Vote.ACCESSIBLE)

        # 3-1 not-accessible (75%) -> CONFIRMED_INACCESSIBLE (Braille
        # Signage's only resolved-inaccessible example).
        self._cast_vote(submissions["powell_braille"], alice, Confirmation.Vote.ACCESSIBLE)
        self._cast_vote(submissions["powell_braille"], bob, Confirmation.Vote.NOT_ACCESSIBLE)
        self._cast_vote(submissions["powell_braille"], carol, Confirmation.Vote.NOT_ACCESSIBLE)
        self._cast_vote(submissions["powell_braille"], admin, Confirmation.Vote.NOT_ACCESSIBLE)

    # ---- comments ------------------------------------------------------

    def _add_comment(self, submission, user, body, parent=None):
        comment, created = Comment.objects.get_or_create(
            submission=submission, user=user, body=body, parent=parent
        )
        if created:
            kind = "replied on" if parent else "commented on"
            self.stdout.write(f"  {user.username} {kind} {submission.feature.name}")
        return comment

    def _seed_comments(self, users, submissions):
        self.stdout.write("Seeding comments...")
        alice, bob, carol, dave = users["alice"], users["bob"], users["carol"], users["dave"]

        comments = {}

        comments["brenhall_braille_bob"] = self._add_comment(
            submissions["brenhall_braille"], bob,
            "Can confirm, saw braille signage near room 4011.",
        )
        self._add_comment(
            submissions["brenhall_braille"], carol,
            "Anyone know if it's on every floor?",
        )

        self._add_comment(
            submissions["arc_ramp"], alice,
            "Used this entrance today, ramp is in great condition.",
        )
        self._add_comment(
            submissions["arc_ramp"], dave,
            "Is there a ramp on the pool side too?",
        )

        wooden_ramp_top_comment = self._add_comment(
            submissions["wooden_ramp"], alice,
            "Ramp near the west entrance works well.",
        )
        comments["wooden_ramp_alice"] = wooden_ramp_top_comment
        self._add_comment(
            submissions["wooden_ramp"], carol,
            "Thanks for reporting this!",
            parent=wooden_ramp_top_comment,
        )

        self._add_comment(
            submissions["langson_restroom"], alice,
            "Has anyone checked this restroom recently?",
        )

        return comments

    # ---- comment reactions -----------------------------------------------

    def _react(self, comment, user, vote):
        _, created = CommentReaction.objects.get_or_create(
            comment=comment, user=user, defaults={"vote": vote}
        )
        if created:
            self.stdout.write(f"  {user.username} {vote.lower()}d a comment")

    def _seed_comment_reactions(self, users, comments):
        self.stdout.write("Seeding comment reactions...")
        alice, bob, carol, dave = users["alice"], users["bob"], users["carol"], users["dave"]

        # Mixed reaction: 2 likes, 1 dislike.
        self._react(comments["wooden_ramp_alice"], bob, CommentReaction.Vote.LIKE)
        self._react(comments["wooden_ramp_alice"], carol, CommentReaction.Vote.LIKE)
        self._react(comments["wooden_ramp_alice"], dave, CommentReaction.Vote.DISLIKE)

        # Unanimous likes.
        self._react(comments["brenhall_braille_bob"], alice, CommentReaction.Vote.LIKE)
        self._react(comments["brenhall_braille_bob"], dave, CommentReaction.Vote.LIKE)
