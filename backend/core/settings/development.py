import os

from .base import *  # noqa: F401,F403

DEBUG = True
ARNOLD_LOCAL_QUEUE = os.getenv("ARNOLD_LOCAL_QUEUE", "1") == "1"
SECRET_KEY = "arnold-development-only-key-with-more-than-fifty-characters-2026"

SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

