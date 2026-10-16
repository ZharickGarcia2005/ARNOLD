import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

DEBUG = False
SECRET_KEY = os.getenv("ARNOLD_SECRET_KEY", "development-only-key-change-before-production")

ALLOWED_HOSTS = [value.strip() for value in os.getenv(
    "ARNOLD_ALLOWED_HOSTS", "localhost,127.0.0.1"
).split(",") if value.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.accounts",
    "apps.batches",
    "apps.validation",
    "apps.workflow",
    "apps.audit",
    "apps.dashboard",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "core.urls"
WSGI_APPLICATION = "core.wsgi.application"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {
        "context_processors": [
            "django.template.context_processors.request",
            "django.contrib.auth.context_processors.auth",
            "django.contrib.messages.context_processors.messages",
        ],
    },
}]

if os.getenv("POSTGRES_HOST"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB", "arnold"),
            "USER": os.getenv("POSTGRES_USER", "arnold_app"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
            "HOST": os.getenv("POSTGRES_HOST", "db"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": 60,
            "OPTIONS": {"sslmode": os.getenv("POSTGRES_SSLMODE", "prefer")},
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_USER_MODEL = "accounts.User"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es-ec"
TIME_ZONE = "America/Guayaquil"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
ARNOLD_MAX_UPLOAD_BYTES = int(os.getenv("ARNOLD_MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))
DATA_UPLOAD_MAX_MEMORY_SIZE = ARNOLD_MAX_UPLOAD_BYTES + 1024 * 1024
FILE_UPLOAD_PERMISSIONS = 0o600
ARNOLD_FILE_ROOT = Path(os.getenv("ARNOLD_FILE_ROOT", BASE_DIR / "private-files"))
ARNOLD_XLSX_MAX_ENTRIES = int(os.getenv("ARNOLD_XLSX_MAX_ENTRIES", "10000"))
ARNOLD_XLSX_MAX_UNCOMPRESSED_BYTES = int(
    os.getenv("ARNOLD_XLSX_MAX_UNCOMPRESSED_BYTES", str(250 * 1024 * 1024))
)
ARNOLD_XLSX_MAX_COMPRESSION_RATIO = int(os.getenv("ARNOLD_XLSX_MAX_COMPRESSION_RATIO", "200"))
ARNOLD_XLSX_MAX_ROWS = int(os.getenv("ARNOLD_XLSX_MAX_ROWS", "100000"))
ARNOLD_XLSX_MAX_COLUMNS = int(os.getenv("ARNOLD_XLSX_MAX_COLUMNS", "100"))
ARNOLD_XLSX_MAX_CELLS = int(os.getenv("ARNOLD_XLSX_MAX_CELLS", "2000000"))
ARNOLD_ANTIVIRUS_COMMAND = os.getenv("ARNOLD_ANTIVIRUS_COMMAND", "").strip()
ARNOLD_REQUIRE_ANTIVIRUS = False
ARNOLD_VALIDATION_LEASE_SECONDS = int(os.getenv("ARNOLD_VALIDATION_LEASE_SECONDS", "10800"))

CELERY_BROKER_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_SOFT_TIME_LIMIT = 7_000
CELERY_TASK_TIME_LIMIT = 7_200
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": 14_400}

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
