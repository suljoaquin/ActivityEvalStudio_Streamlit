"""Inspect the structure of a .docx for report-template analysis (read-only)."""
from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn


def color_hex(font):
    try:
        if font.color and font.color.rgb:
            return str(font.color.rgb)
    except Exception:
        pass
    return None


def run_info(run):
    f = run.font
    return {
        "text": run.text,
        "bold": f.bold,
        "italic": f.italic,
        "underline": f.underline,
        "font": f.name,
        "size_pt": f.size.pt if f.size else None,
        "color": color_hex(f),
    }


def para_info(p):
    pf = p.paragraph_format
    info = {
        "type": "paragraph",
        "text": p.text,
        "style": p.style.name if p.style is not None else None,
        "alignment": p.alignment.name if isinstance(p.alignment, WD_ALIGN_PARAGRAPH) else (str(p.alignment) if p.alignment is not None else None),
        "space_before_pt": pf.space_before.pt if pf.space_before is not None else None,
        "space_after_pt": pf.space_after.pt if pf.space_after is not None else None,
        "line_spacing": pf.line_spacing,
        "left_indent_in": pf.left_indent.inches if pf.left_indent is not None else None,
        "first_line_indent_in": pf.first_line_indent.inches if pf.first_line_indent is not None else None,
        "keep_with_next": pf.keep_with_next,
        "page_break_before": pf.page_break_before,
    }
    # explicit page/section breaks inside runs
    brs = []
    for br in p._p.iter(qn("w:br")):
        brs.append(br.get(qn("w:type")) or "textWrapping")
    if brs:
        info["breaks"] = brs
    if p._p.find(qn("w:pPr")) is not None:
        if p._p.pPr.find(qn("w:sectPr")) is not None:
            info["has_section_break"] = True
    # numbering
    numPr = p._p.pPr.numPr if p._p.pPr is not None else None
    if numPr is not None:
        info["numbering"] = {
            "numId": numPr.numId.val if numPr.numId is not None else None,
            "ilvl": numPr.ilvl.val if numPr.ilvl is not None else None,
        }
    info["runs"] = [run_info(r) for r in p.runs]
    return info


def cell_info(cell):
    tcPr = cell._tc.tcPr
    shading = None
    if tcPr is not None and tcPr.find(qn("w:shd")) is not None:
        shading = tcPr.find(qn("w:shd")).get(qn("w:fill"))
    return {
        "text": cell.text,
        "width_in": cell.width.inches if cell.width is not None else None,
        "shading": shading,
        "paragraphs": [para_info(p) for p in cell.paragraphs],
        "tables": len(cell.tables),
    }


def table_info(t):
    tblPr = t._tbl.tblPr
    style = t.style.name if t.style is not None else None
    borders = {}
    if tblPr is not None:
        b = tblPr.find(qn("w:tblBorders"))
        if b is not None:
            for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
                el = b.find(qn(f"w:{edge}"))
                if el is not None:
                    borders[edge] = {
                        "val": el.get(qn("w:val")),
                        "sz": el.get(qn("w:sz")),
                        "color": el.get(qn("w:color")),
                    }
    grid = []
    if tblPr is not None:
        for gc in tblPr.findall(qn("w:tblGrid")):
            pass
    tblGrid = t._tbl.find(qn("w:tblGrid"))
    if tblGrid is not None:
        grid = [int(c.get(qn("w:w"))) if c.get(qn("w:w")) else None for c in tblGrid.findall(qn("w:gridCol"))]
    return {
        "type": "table",
        "style": style,
        "rows": len(t.rows),
        "cols": len(t.columns),
        "width_in": t.autofit,
        "grid_cols_twips": grid,
        "alignment": str(t.alignment) if t.alignment is not None else None,
        "borders": borders,
        "cell_margins": None,
        "cells": [[cell_info(c) for c in row.cells] for row in t.rows],
    }


def block_items(parent):
    items = []
    for child in parent.element.body.iterchildren():
        if child.tag == qn("w:p"):
            from docx.text.paragraph import Paragraph
            items.append(para_info(Paragraph(child, parent)))
        elif child.tag == qn("w:tbl"):
            from docx.table import Table
            items.append(table_info(Table(child, parent)))
    return items


def section_info(s, idx):
    return {
        "index": idx,
        "start_type": s.start_type.name if s.start_type is not None else None,
        "page_width_in": s.page_width.inches,
        "page_height_in": s.page_height.inches,
        "orientation": s.orientation.name if s.orientation else None,
        "left_margin_in": s.left_margin.inches,
        "right_margin_in": s.right_margin.inches,
        "top_margin_in": s.top_margin.inches,
        "bottom_margin_in": s.bottom_margin.inches,
        "header_distance_in": s.header_distance.inches,
        "footer_distance_in": s.footer_distance.inches,
        "different_first_page": s.different_first_page_header_footer,
        "header_is_linked": s.header.is_linked_to_previous,
        "footer_is_linked": s.footer.is_linked_to_previous,
        "header_text": [p.text for p in s.header.paragraphs],
        "footer_text": [p.text for p in s.footer.paragraphs],
        "first_header_text": [p.text for p in s.first_page_header.paragraphs],
        "first_footer_text": [p.text for p in s.first_page_footer.paragraphs],
        "header_tables": len(s.header.tables),
        "footer_tables": len(s.footer.tables),
    }


def package_parts(path):
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
    groups = {"charts": [], "embeddings": [], "media": [], "headers": [], "footers": [], "other": []}
    for n in names:
        if n.startswith("word/charts/"):
            groups["charts"].append(n)
        elif n.startswith("word/embeddings/"):
            groups["embeddings"].append(n)
        elif n.startswith("word/media/"):
            groups["media"].append(n)
        elif n.startswith("word/header"):
            groups["headers"].append(n)
        elif n.startswith("word/footer"):
            groups["footers"].append(n)
    return groups


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--json-out")
    ap.add_argument("--blocks", action="store_true", help="include body blocks")
    args = ap.parse_args()

    path = Path(args.path)
    doc = Document(str(path))
    data = {
        "path": str(path),
        "core": {
            "title": doc.core_properties.title,
            "subject": doc.core_properties.subject,
            "author": doc.core_properties.author,
        },
        "sections": [section_info(s, i) for i, s in enumerate(doc.sections)],
        "styles_used": sorted({p.style.name for p in doc.paragraphs if p.style is not None}),
        "inline_shapes": [
            {"width_in": sh.width.inches, "height_in": sh.height.inches, "type": sh.type}
            for sh in doc.inline_shapes
        ],
        "tables": [table_info(t) for t in doc.tables],
        "parts": package_parts(path),
    }
    if args.blocks:
        data["blocks"] = block_items(doc)

    text = json.dumps(data, indent=2, ensure_ascii=False)
    if args.json_out:
        Path(args.json_out).write_text(text, encoding="utf-8")
        print(f"Wrote {args.json_out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
