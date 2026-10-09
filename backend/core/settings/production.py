import os
from .base import *  # noqa: F401,F403

DEBUG = False

if SECRET_KEY == "development-only-key-change-before-production":
    raise RuntimeError("ARNOLD_SECRET_KEY es obligatoria en producción.")

if not os.getenv("POSTGRES_HOST") or not os.getenv("POSTGRES_PASSWORD"):
    raise RuntimeError("PostgreSQL es obligatorio en producción.")

