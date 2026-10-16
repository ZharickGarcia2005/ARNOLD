import os
from .base import *  # noqa: F401,F403

DEBUG = False

if SECRET_KEY == "development-only-key-change-before-production":
    raise RuntimeError("ARNOLD_SECRET_KEY es obligatoria en producción.")

if not os.getenv("POSTGRES_HOST") or not os.getenv("POSTGRES_PASSWORD"):
    raise RuntimeError("PostgreSQL es obligatorio en producción.")

if not os.getenv("ARNOLD_DATA_ENCRYPTION_KEY") or not os.getenv("ARNOLD_HMAC_KEY"):
    raise RuntimeError("Las claves de cifrado y búsqueda son obligatorias en producción.")

ARNOLD_REQUIRE_ANTIVIRUS = True
if not ARNOLD_ANTIVIRUS_COMMAND:
    raise RuntimeError("ARNOLD_ANTIVIRUS_COMMAND es obligatorio en producción.")

