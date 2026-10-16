"""Preferencias personales cifradas; no cambia modelos, filas ni revisión financiera."""

from contextlib import contextmanager
from copy import deepcopy
from functools import lru_cache
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
import time
from uuid import UUID

from django.conf import settings

from apps.audit.services import append_audit_event
from apps.batches.crypto import decrypt_json, encrypt_json
from .worksheet import FIELDS, SheetError, can_edit

COLUMNS = ("#", "QUALITY", *FIELDS, "TOTAL", "ERRORS")
STYLE_KEYS = {"background", "color", "bold", "italic", "underline", "align", "size", "wrap"}
MAX_BYTES = 4 * 1024 * 1024


def empty_document():
    return {"version": 0, "columns": {}, "heights": {}, "cells": {}, "zoom": 100}


def location(sheet, actor):
    owner = sha256(str(actor.pk).encode()).hexdigest()
    return Path(settings.ARNOLD_FILE_ROOT) / "presentation" / owner / f"{UUID(str(sheet.pk))}.bin"


def associated(sheet, actor):
    return f"worksheet-presentation:{sheet.pk}:{actor.pk}"


@lru_cache(maxsize=8)
def _cached_read(path, stamp, size, aad):
    if size > MAX_BYTES + 4096:
        raise SheetError("presentation_limit", "La presentación supera el límite permitido.", 413)
    return decrypt_json(Path(path).read_bytes(), associated_data=aad)


def read_document(sheet, actor):
    path = location(sheet, actor)
    try:
        info = path.stat()
    except FileNotFoundError:
        return empty_document()
    return _cached_read(str(path), info.st_mtime_ns, info.st_size, associated(sheet, actor))


def page_presentation(sheet, actor, row_ids):
    doc = read_document(sheet, actor)
    ids = {str(value) for value in row_ids}
    return {**doc, "heights": {key: value for key, value in doc["heights"].items() if key in ids},
            "cells": {key: value for key, value in doc["cells"].items() if key in ids}}


@contextmanager
def file_lock(path):
    """Bloqueo entre procesos, compatible con Windows y POSIX en disco compartido."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_suffix(".lock"), "a+b") as lock:
        lock.seek(0, os.SEEK_END)
        if lock.tell() == 0:
            lock.write(b"0"); lock.flush()
        deadline = time.monotonic() + 3
        while True:
            try:
                lock.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise SheetError("presentation_busy", "Otro guardado visual está en curso. Reintente.", 409)
                time.sleep(.04)
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == "nt":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)


def valid_style(value):
    if not isinstance(value, dict) or set(value) - STYLE_KEYS:
        raise SheetError("invalid_style", "Formato visual no admitido.")
    for key, item in value.items():
        if key in ("background", "color"):
            valid = item is None or isinstance(item, str) and bool(re.fullmatch(r"#[0-9a-fA-F]{6}", item))
        elif key in ("bold", "italic", "underline", "wrap"):
            valid = isinstance(item, bool)
        elif key == "align":
            valid = item in (None, "left", "center", "right")
        else:
            valid = type(item) is int and 10 <= item <= 24
        if not valid:
            raise SheetError("invalid_style", f"Valor de {key} no permitido.")
    return value


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise SheetError("invalid_size", f"El tamaño debe estar entre {low} y {high}.")
    return value


def validate_operations(sheet, operations):
    if not isinstance(operations, list) or not 1 <= len(operations) <= 100:
        raise SheetError("operation_limit", "Envíe entre 1 y 100 operaciones visuales por lote.")
    ids, cost = set(), 0
    for op in operations:
        if not isinstance(op, dict) or set(op) - {"kind", "rows", "columns", "style", "reset", "value"}:
            raise SheetError("invalid_operation", "Operación visual inválida.")
        kind = op.get("kind")
        if kind not in ("cells", "columns", "width", "height", "zoom", "reset_sizes"):
            raise SheetError("invalid_operation", "Operación visual desconocida.")
        columns = op.get("columns", [])
        rows = op.get("rows", [])
        if not isinstance(columns, list) or len(columns) > len(COLUMNS) or any(column not in COLUMNS for column in columns):
            raise SheetError("invalid_column", "Columna visual no admitida.")
        if not isinstance(rows, list) or len(rows) > 100:
            raise SheetError("row_limit", "Seleccione hasta 100 filas por operación.")
        try:
            ids.update(str(UUID(str(value))) for value in rows)
            if rows:
                op["rows"] = [str(UUID(str(value))) for value in rows]
        except (ValueError, TypeError, AttributeError):
            raise SheetError("invalid_row", "Identificador de fila inválido.")
        if "reset" in op and not isinstance(op["reset"], bool):
            raise SheetError("invalid_operation", "Restauración inválida.")
        if kind in ("cells", "columns"):
            valid_style(op.get("style", {}))
            if not columns or kind == "cells" and not rows:
                raise SheetError("empty_selection", "Seleccione celdas o columnas.")
            cost += len(columns) * max(1, len(rows))
        if kind == "width":
            if not columns:
                raise SheetError("empty_selection", "Seleccione una columna.")
            integer(op.get("value"), 40, 800)
        if kind == "height":
            if not rows:
                raise SheetError("empty_selection", "Seleccione una fila.")
            integer(op.get("value"), 24, 240)
        if kind == "zoom":
            integer(op.get("value"), 70, 150)
    if len(ids) > 100 or cost > 10000:
        raise SheetError("operation_limit", "El lote visual supera el límite de selección.", 413)
    if len(ids) != sheet.rows.filter(pk__in=ids).count():
        raise SheetError("invalid_row", "La selección contiene filas ajenas a la cartera.")


def apply_operations(document, operations):
    """Operaciones idempotentes por lote; ningún valor de cartera se almacena aquí."""
    for op in operations:
        kind = op["kind"]
        columns, rows = op.get("columns", []), op.get("rows", [])
        style = op.get("style", {})
        if kind == "columns":
            for column in columns:
                item = document["columns"].setdefault(column, {})
                if op.get("reset"):
                    item["style"] = {}
                else:
                    item["style"] = {**item.get("style", {}), **style}
                for row in document["cells"].values():
                    if column in row:
                        if op.get("reset"):
                            row.pop(column)
                        else:
                            row[column].pop("reset", None)
                            for key in style:
                                row[column].pop(key, None)
        elif kind == "cells":
            for row_id in rows:
                row = document["cells"].setdefault(str(row_id), {})
                for column in columns:
                    row[column] = {"reset": True} if op.get("reset") else {**row.get(column, {}), **style}
        elif kind == "width":
            for column in columns:
                document["columns"].setdefault(column, {})["width"] = op["value"]
        elif kind == "height":
            for row in rows:
                document["heights"][str(row)] = op["value"]
        elif kind == "zoom":
            document["zoom"] = op["value"]
        elif kind == "reset_sizes":
            document["heights"] = {}
            document["zoom"] = 100
            for column in document["columns"].values():
                column.pop("width", None)
    return document


def effective_style(document, row_id, field):
    cell = document["cells"].get(str(row_id), {}).get(field, {})
    column = {} if cell.get("reset") else document["columns"].get(field, {}).get("style", {})
    return {**column, **{key: value for key, value in cell.items() if key != "reset"}}


def save_presentation(sheet, actor, expected_version, operations):
    if not can_edit(actor) or sheet.batch.status in ("approved", "exported", "rejected"):
        raise SheetError("permission_denied", "No tiene permiso para guardar formato en esta cartera.", 403)
    validate_operations(sheet, operations)
    path = location(sheet, actor)
    with file_lock(path):
        current = read_document(sheet, actor)
        if type(expected_version) is not int or current["version"] != expected_version:
            raise SheetError("presentation_conflict", "El formato cambió en otra pestaña. Actualice el formato y reintente.", 409)
        document = apply_operations(deepcopy(current), operations)
        document["version"] += 1
        if len(json.dumps(document).encode()) > MAX_BYTES:
            raise SheetError("presentation_limit", "Demasiadas celdas con formato. Use formato de columna para rangos masivos.", 413)
        encrypted = encrypt_json(document, associated_data=associated(sheet, actor))
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as target:
                temporary = target.name
                target.write(encrypted); target.flush(); os.fsync(target.fileno())
            os.replace(temporary, path)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
    append_audit_event(actor=actor, action="worksheet.presentation_saved", object_type="Batch", object_id=sheet.pk,
                       metadata={"operations": len(operations), "presentation_version": document["version"]})
    return document["version"]
