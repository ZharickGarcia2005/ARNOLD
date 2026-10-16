"""Servidor de prueba visual con datos sintéticos; nunca consulta carteras reales.

Ejecutar desde backend con ../tools/worksheet_ui_fixture.py. Solo escucha 127.0.0.1:8011.
No sustituye la autenticación ni publica una sesión del servidor principal.
"""

from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings.development")
import django
django.setup()
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import RequestFactory
from apps.workflow.presentation import apply_operations, empty_document
from apps.workflow.sheet_exports import typed_value
from openpyxl import Workbook

FIELDS = ["CIU", "CEDULA_RUC", "NOMBRES", "CLAVE", "DIRECCION", "PARROQUIA", "TELEF", "CORREO", "TOTAL_EMISION", "TOTAL_INTERES", "TOTAL_COACTIVA", "TOTAL_RECARGO", "MESES_DEUDA", "FECHA_VENCIMIENTO"]
BATCH = {"id": "00000000-0000-0000-0000-000000000001", "name": "PRUEBA SINTÉTICA · sin datos personales.xlsx", "status": "ready", "status_label": "Listo para revisar", "period": "2026-08-01", "status_url": "/api/v1/batches/00000000-0000-0000-0000-000000000001/"}
VALUES = dict.fromkeys(FIELDS, "")
VALUES.update(CIU="000042", CEDULA_RUC="1710034065", NOMBRES="PERSONA DE PRUEBA A", CLAVE="000123", TOTAL_EMISION="10.00", TOTAL_INTERES="2.00", TOTAL_COACTIVA="3.00", TOTAL_RECARGO="4.00", MESES_DEUDA="52.0")
ROWS = [{"id": f"row-{number}", "source_row": number + 1, "version": 1, "quality": "clean", "errors": [], "total": "19", "values": {**VALUES, "CLAVE": f"{number:06d}", "NOMBRES": f"PERSONA DE PRUEBA {number}"}} for number in range(1, 101)]
REVISION = 1
PRESENTATION = empty_document()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self, content, kind="application/json", status=200, headers=None):
        if isinstance(content, (dict, list)):
            content = json.dumps(content).encode()
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Cache-Control", "no-store")
        for name, value in (headers or {}).items():
            self.send_header(name, str(value))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path.startswith("/static/"):
            asset = (BACKEND / "static" / path.removeprefix("/static/")).resolve()
            if not asset.is_relative_to((BACKEND / "static").resolve()) or not asset.is_file():
                self.respond({}, status=404)
                return
            content = asset.read_bytes()
            if asset.name == "worksheet.css" and "baseline=1" in self.path:
                content = content.split("/* Hoja como primera pantalla".encode())[0]
            self.respond(content, "text/javascript" if asset.suffix == ".js" else "text/css")
        elif path == "/api/v1/batches/":
            self.respond({"batches": [BATCH]})
        elif path == BATCH["status_url"]:
            self.respond({"status": "ready", "run": {"status": "succeeded"}})
        else:
            request = RequestFactory().get("/")
            request.user = get_user_model()(username="Prueba sintética", role="admin", is_superuser=True, is_active=True)
            html = render_to_string("dashboard/worksheet.html", {"max_upload_bytes": 52428800, "asset_version": "fixture"}, request=request)
            if path == "/baseline/":
                html = html.replace("worksheet.css?v=fixture", "worksheet.css?v=fixture&baseline=1")
            self.respond(html.encode(), "text/html;charset=utf-8")

    def do_POST(self):
        global REVISION, PRESENTATION
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
        if self.path.endswith("/presentation/"):
            if "operations" in body:
                if body.get("version") != PRESENTATION["version"]:
                    self.respond({"error": {"code": "presentation_conflict", "message": "Conflicto de formato sintético."}}, status=409)
                    return
                apply_operations(PRESENTATION, body["operations"])
                PRESENTATION["version"] += 1
                self.respond({"version": PRESENTATION["version"]})
            else:
                self.respond({"presentation": PRESENTATION})
        elif self.path.endswith("/download/"):
            if "error-download" in self.headers.get("Referer", ""):
                self.respond({"error": {"message": "Fallo de descarga sintético."}}, status=503)
                return
            book = Workbook(); data = book.active; data.title = "Principal"
            data.append(FIELDS)
            for row in ROWS:
                data.append([typed_value(field, row["values"][field]) for field in FIELDS])
            stream = BytesIO(); book.save(stream); book.close()
            self.respond(stream.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                         headers={"Content-Disposition": 'attachment; filename="fixture-principal.xlsx"',
                                  "X-ARNOLD-Export-Rows": len(ROWS), "X-ARNOLD-Export-Revision": REVISION})
        elif self.path.endswith("/save/"):
            if "error-save" in self.headers.get("Referer", ""):
                self.respond({"error": {"message": "Fallo de guardado sintético."}}, status=503)
                return
            ids = []
            for change in body["changes"]:
                row = next(item for item in ROWS if item["id"] == change["id"])
                row["values"].update(change["values"])
                row["version"] += 1
                ids.append(row["id"])
            REVISION += 1
            self.respond({"applied": ids, "pending": [], "summary": {"revision": REVISION}})
        else:
            rows = deepcopy(ROWS) if body.get("scope") != "problem" else []
            if body.get("search"):
                rows = [row for row in rows if body["search"] in (row["values"]["CLAVE"], row["values"]["CIU"], row["values"]["CEDULA_RUC"])]
            self.respond({"name": BATCH["name"], "fields": FIELDS, "rows": rows, "page": 1, "filtered_total": len(rows), "has_next": False,
                          "summary": {"revision": REVISION, "total": len(ROWS), "clean": len(ROWS), "problem": 0, "duplicates": 0, "pending_approvals": 0},
                          "presentation": PRESENTATION,
                          "capabilities": {"edit": True, "protected": True, "export": True, "format": True},
                          "skipped_rules": {"MONTH-001": "Fixture visual: sin fuente histórica."}})


if __name__ == "__main__":
    print("Fixture sintético de hoja: http://127.0.0.1:8011/", flush=True)
    ThreadingHTTPServer(("127.0.0.1", 8011), Handler).serve_forever()
