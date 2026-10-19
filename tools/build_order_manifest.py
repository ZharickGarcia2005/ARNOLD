"""Extrae sólo presentación de las 12 hojas operativas del libro autorizado.

Sin datos de personas, evaluación de fórmulas ni dependencias de hojas auxiliares.
"""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import posixpath
from zipfile import ZipFile
from defusedxml import ElementTree as ET

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
NAMES = ("030-SAN CARLOS (LISTA)", "031-(24 DE MAYO) LISTA", "032-SAN CRISTOBAL(LISTA)", "033-GUAYACAN(LISTA)",
         "034-GUAYACAN(LISTA)", "035-NICOLAS ALTA(LISTA)", "036-RUTA DEL RIO(LISTA)", "037-VIVA ALFARO(LISTA)",
         "038- VENUS", "039-VENUS", "040-VENUS", "INCONSISTENCIAS")


def column_index(address):
    result = 0
    for char in address:
        if not char.isalpha(): break
        result = result * 26 + ord(char.upper()) - 64
    return result


def build(path):
    if not path.name.endswith(" (1).xlsx"):
        raise ValueError("Únicamente se acepta la referencia con (1).")
    with ZipFile(path) as archive:
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            strings = ["".join(t.text or "" for t in item.iter(NS + "t")) for item in root]
        links = {item.get("Id"): item.get("Target") for item in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))}
        metas = {item.get("name"): item for item in ET.fromstring(archive.read("xl/workbook.xml")).find(NS + "sheets")}
        styles = ET.fromstring(archive.read("xl/styles.xml"))
        num_formats = styles.find(NS + "numFmts")
        formats = {int(item.get("numFmtId")): item.get("formatCode") for item in num_formats} if num_formats is not None else {}
        def fill_color(style_id):
            xf = styles.find(NS + "cellXfs")[style_id]
            fill = styles.find(NS + "fills")[int(xf.get("fillId", 0))]
            node = fill.find(f"{NS}patternFill/{NS}fgColor")
            rgb = node.get("rgb", "") if node is not None else ""
            return "#" + rgb[-6:] if len(rgb) in (6, 8) and rgb[-6:] not in ("FFFFFF", "000000") else None
        result = {"version": "order-book-2026.10.19.1", "sha256": sha256(path.read_bytes()).hexdigest(), "sheets": []}
        for name in NAMES:
            target = links[metas[name].get(RID)]
            target = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
            tree = ET.fromstring(archive.read(target))
            rows = tree.find(NS + "sheetData"); first = rows.find(NS + "row")
            if first.get("r") != "1": raise ValueError(f"Cabecera no confirmada: {name}")
            headers = {}
            for cell in first:
                value = cell.find(NS + "v"); value = value.text if value is not None else ""
                if cell.get("t") == "s": value = strings[int(value)]
                if cell.get("t") == "inlineStr": value = "".join(t.text or "" for t in cell.iter(NS + "t"))
                headers[column_index(cell.get("r"))] = value
            last = max(index for index, text in headers.items() if text)
            dimension_node = tree.find(NS + "cols")
            dimensions = list(dimension_node) if dimension_node is not None else []
            columns = []
            sample_styles = {column_index(cell.get("r")): int(cell.get("s", 0)) for row in list(rows)[1:3] for cell in row}
            for index in range(1, last + 1):
                dim = next((d for d in reversed(dimensions) if int(d.get("min")) <= index <= int(d.get("max"))), None)
                style = styles.find(NS + "cellXfs")[sample_styles.get(index, 0)]
                num_id = int(style.get("numFmtId", 0))
                columns.append({"position": index, "label": headers.get(index, ""),
                                "hidden": dim is not None and dim.get("hidden") == "1",
                                "outline": int(dim.get("outlineLevel", 0)) if dim is not None else 0,
                                "width": float(dim.get("width", 13)) if dim is not None else 13,
                                "source_number_format": formats.get(num_id, {0:"General", 14:"mm-dd-yy", 22:"m/d/yy h:mm"}.get(num_id, "General"))})
            header_colors = Counter(filter(None, (fill_color(int(cell.get("s", 0))) for cell in first)))
            source_fill = header_colors.most_common(1)[0][0] if header_colors else "#D9E2F3"
            # El usuario solicita encabezado gris azulado en todas las pestañas.
            # Se conserva el color observado como metadato, y se usa el de 030
            # como estilo común, sin alterar la organización de cada orden.
            display_fill = result["sheets"][0]["header_fill"] if result["sheets"] else source_fill
            result["sheets"].append({"id": name[:3] if name != "INCONSISTENCIAS" else "issues", "name": name,
                                     "columns": columns, "source_header_fill": source_fill, "header_fill": display_fill, "stripe_fill": "#DEEAF6",
                                     "border_color": "#B8C9DB"})
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("source", type=Path); parser.add_argument("output", type=Path)
    args = parser.parse_args(); document = build(args.source)
    args.output.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    for sheet in document["sheets"]:
        print(sheet["name"], [(c["position"], c["label"], c["hidden"]) for c in sheet["columns"]])
