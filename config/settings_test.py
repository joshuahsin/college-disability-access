"""
Settings for running the test suite without a live PostgreSQL server.
Usage: python manage.py test --settings=config.settings_test
"""
from .settings import *  # noqa: F401,F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Skip PBKDF2's deliberately-slow hashing so create_user() is fast across
# the many users each test creates.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
