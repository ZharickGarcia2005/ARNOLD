"""Análisis nuevo, sólo XML y estadísticas: nunca ejecuta contenido del XLSX."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import posixpath
import re
from zipfile import ZipFile
from defusedxml import ElementTree as ET

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
HEADER_LABELS = set("NO TP EXP PREDIO_MUNICIPAL CONTRIBUYENTE CEDULA OP OC DIGIT CLAVE CIU DIRECCION PARROQUIA PARROQ ZONA SECTOR MZ PREDIO ID_PLAN TELEFONO CORREO TITULO TITULOS TITULOS_VENCIDOS TITULOS_VENC EMISION EMI_LETRA INTERES INT_LETRA SUBTOTAL SUBTOTAL_EN_LETRA RECARGO RECARGO_EN_LETRA TOTAL TOTAL_EN_LETRA DIGITADOR FECHA HORA NOVEDAD NOMBRE_DE_ARCHIVO_Y_NUMERO ORDEN_COACTIVA_ANTERIOR CLAVE_NUEV BARRIO NOMBRES".split())


def analyze(path):
    digest = sha256(path.read_bytes()).hexdigest()
    with ZipFile(path) as archive:
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            with archive.open("xl/sharedStrings.xml") as stream:
                for _, node in ET.iterparse(stream, events=("end",)):
                    if node.tag == NS + "si":
                        strings.append("".join(t.text or "" for t in node.iter(NS + "t")))
                        node.clear()
        rels = {n.get("Id"): n.get("Target") for n in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))}
        styles = ET.fromstring(archive.read("xl/styles.xml"))
        result = {"version": "current-reference-1", "sha256": digest, "sheets": []}
        for meta in ET.fromstring(archive.read("xl/workbook.xml")).find(NS + "sheets"):
            part = rels[meta.get(RID)]
            part = part.lstrip("/") if part.startswith("/") else posixpath.normpath("xl/" + part)
            item = {"name": meta.get("name"), "visibility": meta.get("state", "visible"), "headers": [], "columns": [],
                    "populated_rows": 0, "errors": Counter(), "formulas": Counter(), "types": Counter(), "header_styles": {}, "panes": [], "filters": []}
            identifiers = {key: {"nonempty": 0, "distinct": set(), "lengths": Counter(), "patterns": Counter()} for key in ("CLAVE", "TITULO", "TITULOS", "TITULOS VENCIDOS", "TITULOS VENC.")}
            with archive.open(part) as stream:
                for _, node in ET.iterparse(stream, events=("end",)):
                    tag = node.tag.removeprefix(NS)
                    if tag == "row":
                        data = {}
                        for cell in node.findall(NS + "c"):
                            col = re.sub(r"\d", "", cell.get("r", ""))
                            value_node, formula = cell.find(NS + "v"), cell.find(NS + "f")
                            value = value_node.text if value_node is not None else "".join(t.text or "" for t in cell.iter(NS + "t"))
                            kind = cell.get("t", "n")
                            if kind == "s" and value:
                                value = strings[int(value)]
                            if value or formula is not None:
                                data[col] = value
                                item["types"][kind] += 1
                                if kind == "e": item["errors"][value] += 1
                                if formula is not None: item["formulas"][col] += 1
                            if node.get("r") == "1":
                                normalized = re.sub(r"[^A-Z0-9]+", "_", (value or "").upper()).strip("_")
                                item["headers"].append({"column": col, "label": value if normalized in HEADER_LABELS else "" if not value else "<sin encabezado reconocido>", "style": int(cell.get("s", 0))})
                        if data: item["populated_rows"] += 1
                        if node.get("r") != "1":
                            for header in item["headers"]:
                                key = (header["label"] or "").strip().upper()
                                value = data.get(header["column"], "")
                                if key in identifiers and value:
                                    stats = identifiers[key]; stats["nonempty"] += 1
                                    stats["distinct"].add(value); stats["lengths"][len(value)] += 1
                                    pattern = "entero" if re.fullmatch(r"\d+", value) else "decimal" if re.fullmatch(r"\d+\.\d+", value) else "lista" if re.search(r"[,;\n]", value) else "otro"
                                    stats["patterns"][pattern] += 1
                        node.clear()
                    elif tag == "col": item["columns"].append(dict(node.attrib))
                    elif tag == "pane": item["panes"].append(dict(node.attrib))
                    elif tag == "autoFilter": item["filters"].append(node.get("ref"))
            item["identifiers"] = {key: {"nonempty": v["nonempty"], "distinct": len(v["distinct"]), "lengths": v["lengths"], "patterns": v["patterns"]} for key, v in identifiers.items() if v["nonempty"]}
            for header in item["headers"]:
                xf = styles.find(NS + "cellXfs")[header["style"]]
                font = styles.find(NS + "fonts")[int(xf.get("fontId", 0))]
                fill = styles.find(NS + "fills")[int(xf.get("fillId", 0))]
                alignment = xf.find(NS + "alignment")
                item["header_styles"][str(header["style"])] = {"font": ET.tostring(font, encoding="unicode"), "fill": ET.tostring(fill, encoding="unicode"), "alignment": dict(alignment.attrib) if alignment is not None else {}, "numFmtId": xf.get("numFmtId")}
            result["sheets"].append(item)
        result["external_parts"] = sum(n.startswith("xl/externalLinks/") and n.endswith(".xml") for n in archive.namelist())
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("source", type=Path); parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = analyze(args.source)
    # Sólo encabezados verificados por el desarrollador deben pasar al manifiesto
    # público. Primero se inspecciona aquí, en un directorio privado/ignorado.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"sha256": result["sha256"], "sheets": [{k: s[k] for k in ("name", "visibility", "populated_rows", "errors", "identifiers")} for s in result["sheets"]]}, ensure_ascii=False))
