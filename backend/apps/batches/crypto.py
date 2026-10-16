"""Cryptographic helpers for ARNOLD's sensitive persisted data.

Production deployments must provide a 32-byte, base64-encoded
``ARNOLD_DATA_ENCRYPTION_KEY`` and an ``ARNOLD_HMAC_KEY`` containing at
least 32 bytes of secret material.  Development may derive domain-separated
keys from Django's ``SECRET_KEY`` so a local checkout remains usable; that
fallback is deliberately noisy and must never be relied upon in production.

Ciphertexts use a small versioned envelope so future formats can be rejected
or migrated explicitly instead of being interpreted ambiguously.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import threading
import uuid
import warnings
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings


_ENVELOPE_PREFIX = b"ARNOLD-AESGCM\x01"
_NONCE_SIZE = 12
_DATA_KEY_CONTEXT = b"arnold:development:data-encryption:v1\x00"
_HMAC_KEY_CONTEXT = b"arnold:development:blind-index:v1\x00"
_AAD_CONTEXT = b"arnold:json:v1\x00"
_BLIND_INDEX_CONTEXT = b"arnold:blind-index:v1\x00"

_warning_lock = threading.Lock()
_warned_fallbacks: set[str] = set()


class CryptoConfigurationError(RuntimeError):
    """Raised when required cryptographic key material is missing or invalid."""


class EncryptionError(ValueError):
    """Raised when a value cannot be serialized or encrypted."""


class DecryptionError(ValueError):
    """Raised when a ciphertext is malformed, altered, or cannot be decoded."""


def _configured_value(name: str) -> str | bytes | None:
    """Read a key from Django settings, falling back to the environment."""

    value = getattr(settings, name, None)
    if value in (None, "", b""):
        value = os.getenv(name)
    return value


def _development_key(context: bytes, setting_name: str) -> bytes:
    if not settings.DEBUG:
        raise CryptoConfigurationError(
            f"{setting_name} es obligatorio cuando DEBUG=False."
        )

    with _warning_lock:
        if setting_name not in _warned_fallbacks:
            warnings.warn(
                f"{setting_name} no está configurada; ARNOLD derivará una clave "
                "temporal de SECRET_KEY porque DEBUG=True. No use esta "
                "configuración con datos reales ni en producción.",
                RuntimeWarning,
                stacklevel=3,
            )
            _warned_fallbacks.add(setting_name)

    secret = str(settings.SECRET_KEY).encode("utf-8")
    return hashlib.sha256(context + secret).digest()


def _data_encryption_key() -> bytes:
    encoded = _configured_value("ARNOLD_DATA_ENCRYPTION_KEY")
    if encoded in (None, "", b""):
        return _development_key(
            _DATA_KEY_CONTEXT,
            "ARNOLD_DATA_ENCRYPTION_KEY",
        )

    if isinstance(encoded, str):
        try:
            encoded = encoded.strip().encode("ascii", errors="strict")
        except UnicodeEncodeError as exc:
            raise CryptoConfigurationError(
                "ARNOLD_DATA_ENCRYPTION_KEY debe contener solo caracteres base64."
            ) from exc
    elif isinstance(encoded, bytes):
        encoded = encoded.strip()
    else:
        raise CryptoConfigurationError(
            "ARNOLD_DATA_ENCRYPTION_KEY debe ser texto base64."
        )

    try:
        decoded = base64.b64decode(encoded, altchars=b"-_", validate=True)
    except (binascii.Error, ValueError) as exc:
        raise CryptoConfigurationError(
            "ARNOLD_DATA_ENCRYPTION_KEY debe ser base64 válido."
        ) from exc

    if len(decoded) != 32:
        raise CryptoConfigurationError(
            "ARNOLD_DATA_ENCRYPTION_KEY debe decodificar exactamente a 32 bytes."
        )
    return decoded


def _hmac_key() -> bytes:
    configured = _configured_value("ARNOLD_HMAC_KEY")
    if configured in (None, "", b""):
        return _development_key(_HMAC_KEY_CONTEXT, "ARNOLD_HMAC_KEY")

    if isinstance(configured, str):
        key = configured.encode("utf-8")
    elif isinstance(configured, bytes):
        key = configured
    else:
        raise CryptoConfigurationError("ARNOLD_HMAC_KEY debe ser texto o bytes.")

    if len(key) < 32:
        raise CryptoConfigurationError(
            "ARNOLD_HMAC_KEY debe contener al menos 32 bytes de secreto."
        )
    return key


def _associated_data(value: str | bytes | None) -> bytes:
    if value is None:
        supplied = b""
    elif isinstance(value, str):
        supplied = value.encode("utf-8")
    elif isinstance(value, bytes):
        supplied = value
    else:
        raise TypeError("associated_data debe ser str, bytes o None.")
    return _AAD_CONTEXT + supplied


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, (Decimal, uuid.UUID)):
        return str(value)
    raise TypeError(
        f"El tipo {type(value).__name__} no se puede serializar como JSON seguro."
    )


def encrypt_json(
    value: Any,
    *,
    associated_data: str | bytes | None = None,
) -> bytes:
    """Serialize ``value`` deterministically and encrypt it with AES-256-GCM.

    ``associated_data`` is authenticated but not stored in the envelope.  The
    caller should use a stable record identity and provide the same value to
    :func:`decrypt_json`.
    """

    try:
        plaintext = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=_json_default,
        ).encode("utf-8")
        nonce = os.urandom(_NONCE_SIZE)
        ciphertext = AESGCM(_data_encryption_key()).encrypt(
            nonce,
            plaintext,
            _associated_data(associated_data),
        )
    except CryptoConfigurationError:
        raise
    except (TypeError, ValueError) as exc:
        raise EncryptionError(f"No se pudo cifrar el valor JSON: {exc}") from exc

    return _ENVELOPE_PREFIX + nonce + ciphertext


def decrypt_json(
    encrypted: bytes | bytearray | memoryview,
    *,
    associated_data: str | bytes | None = None,
) -> Any:
    """Authenticate, decrypt, and deserialize an ARNOLD JSON envelope."""

    if not isinstance(encrypted, (bytes, bytearray, memoryview)):
        raise DecryptionError("El contenido cifrado debe ser binario.")

    envelope = bytes(encrypted)
    minimum_size = len(_ENVELOPE_PREFIX) + _NONCE_SIZE + 16
    if len(envelope) < minimum_size or not envelope.startswith(_ENVELOPE_PREFIX):
        raise DecryptionError("El contenido cifrado tiene un formato no reconocido.")

    nonce_start = len(_ENVELOPE_PREFIX)
    nonce_end = nonce_start + _NONCE_SIZE
    nonce = envelope[nonce_start:nonce_end]
    ciphertext = envelope[nonce_end:]

    try:
        plaintext = AESGCM(_data_encryption_key()).decrypt(
            nonce,
            ciphertext,
            _associated_data(associated_data),
        )
    except CryptoConfigurationError:
        raise
    except InvalidTag as exc:
        raise DecryptionError(
            "No se pudo autenticar el contenido cifrado; la clave, los datos "
            "asociados o el contenido no coinciden."
        ) from exc
    except (TypeError, ValueError) as exc:
        raise DecryptionError(f"No se pudo descifrar el contenido: {exc}") from exc

    try:
        return json.loads(plaintext.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DecryptionError(
            "El contenido descifrado no contiene JSON válido."
        ) from exc


def blind_index(value: str | bytes) -> str:
    """Return a deterministic HMAC-SHA256 index without exposing ``value``.

    Normalization belongs to the caller so identifiers with meaningful leading
    zeroes are never modified implicitly.
    """

    if isinstance(value, str):
        payload = value.encode("utf-8")
    elif isinstance(value, bytes):
        payload = value
    else:
        raise TypeError("blind_index solo acepta str o bytes.")

    return hmac.new(
        _hmac_key(),
        _BLIND_INDEX_CONTEXT + payload,
        hashlib.sha256,
    ).hexdigest()


__all__ = [
    "CryptoConfigurationError",
    "DecryptionError",
    "EncryptionError",
    "blind_index",
    "decrypt_json",
    "encrypt_json",
]
