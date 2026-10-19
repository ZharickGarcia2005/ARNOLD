"""Partición de presentación, sin modificar clasificaciones ni evidencia histórica."""
from collections import Counter
from functools import lru_cache
import re
from django.conf import settings
from .columns import SHEETS, original_payload, raw_text

ORDER_FIELDS = ("ORDEN_PRELIMINAR", "ORDEN")


def resolve_order(batch, values, raw, source_sheet=""):
    matches = set()
    by_name = {sheet["name"]: code for code, sheet in SHEETS.items() if code != "issues"}
    if batch.sheet_name in by_name: matches.add(by_name[batch.sheet_name])
    if source_sheet in by_name: matches.add(by_name[source_sheet])
    for field in ORDER_FIELDS:
        value = values.get(field, raw_text(raw.get(field, {}))).strip()
        if not value: continue
        code = by_name.get(value)
        if code is None and re.fullmatch(r"\d{1,3}(?:\.0+)?", value): code = str(int(float(value))).zfill(3)
        if code not in SHEETS or code == "issues": return "", f"Orden no reconocida en {field}; no se asignó automáticamente."
        matches.add(code)
    if len(matches) == 1: return matches.pop(), ""
    return "", "La orden es contradictoria." if matches else "No se recibió una orden 030–040 identificable; OP no se interpreta sin confirmación."


@lru_cache(maxsize=8)
def routing_index(batch_id, revision, content_version, database_name):
    # Sólo se cachean UUID, orden y motivo técnico: nunca datos de personas.
    from .models import Worksheet
    from .worksheet import values_of
    sheet = Worksheet.objects.select_related("batch").get(pk=batch_id)
    result = {}
    for row in sheet.rows.select_related("record").iterator(chunk_size=500):
        payload = original_payload(row)
        result[str(row.pk)] = resolve_order(sheet.batch, values_of(row), payload["fields"], payload.get("origin", {}).get("sheet", ""))
    return result


def routes(sheet):
    return routing_index(str(sheet.pk), sheet.revision, sheet.batch.content_version, str(settings.DATABASES["default"]["NAME"]))


def selected_ids(sheet, scope, search="", order=None):
    from .worksheet import filter_rows
    mapping = routes(sheet)
    result = []
    for pk, quality in filter_rows(sheet, "all", search).values_list("pk", "quality"):
        code, error = mapping[str(pk)]
        is_problem = quality != "clean" or bool(error)
        if (scope == "problem") != is_problem: continue
        if scope == "clean" and order and code != order: continue
        result.append(pk)
    return result


def presentation_counts(sheet):
    mapping, count = routes(sheet), Counter()
    for pk, quality in sheet.rows.values_list("pk", "quality"):
        code, error = mapping[str(pk)]
        count["issues" if quality != "clean" or error else code] += 1
    return count


def decorate(payload, route):
    code, error = route
    payload["order"] = code
    payload["presentation_quality"] = "problem" if payload["quality"] != "clean" or error else "clean"
    if error: payload["errors"] = [*payload["errors"], {"field": "ORDEN_PRELIMINAR", "code": "ORDER_MAPPING", "message": error}]
    return payload
