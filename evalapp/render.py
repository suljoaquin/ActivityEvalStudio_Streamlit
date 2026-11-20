"""Render Activity and Speaker reports from the compiled docxtpl templates."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Iterable
from xml.sax.saxutils import escape as xml_escape

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docxtpl import DocxTemplate, RichText

from .aggregate import ActivityResult, SpeakerResult
from .paths import COMPILED_DIR, ensure_dirs
from .normalization import clean_text


class RenderError(RuntimeError):
    pass


def rich_lines(text: str) -> RichText:
    """Retained for callers that need styled rich text; speaker topics use
    docxtpl's native newline-to-<w:br/> conversion."""
    rt = RichText()
    lines = clean_text(text).split("\n")
    for i, line in enumerate(lines):
        if i:
            rt.xml += "<w:r><w:br/></w:r>"
        rt.add(line)
    return rt


def _comment_context(prefix: str, lines: list[str]) -> dict:
    return {
        f"{prefix}_has_comments": bool(lines),
        f"{prefix}_comments": lines,
    }


def _activity_context(activity: ActivityResult, meta: dict) -> dict:
    ctx = {
        "meta_title": meta.get("title", ""),
        "meta_date": meta.get("date", ""),
        "meta_venue": meta.get("venue", ""),
        "meta_proponent": meta.get("proponent", ""),
        "prepared_by": meta.get("prepared_by", ""),
        "checked_by": meta.get("checked_by", ""),
        "signatory_name": meta.get("signatory_name", ""),
        "signatory_role": meta.get("signatory_role", ""),
        "activity_overall": activity.overall_display.split(" (")[0],
        "activity_overall_label": activity.overall_label,
        "activity_n": str(activity.n),
    }
    for key, item in activity.items.items():
        tag = key.replace(".", "_")
        if key == "management.hospitality" and activity.hospitality.get("mode") != "compute":
            ctx[f"activity_{tag}_mean"] = "N/A"
            ctx[f"activity_{tag}_label"] = "N/A"
        else:
            ctx[f"activity_{tag}_mean"] = item.mean_display
            ctx[f"activity_{tag}_label"] = item.interpretation
    part2 = activity.comments.get("part2")
    part3 = activity.comments.get("part3")
    ctx.update(_comment_context("activity_part2", part2.lines if part2 else []))
    ctx.update(_comment_context("activity_part3", part3.lines if part3 else []))
    if part3 and part3.lines:
        sentence = ""
    else:
        sentence = meta.get("part3_none_sentence") or activity.part3_sentence
    ctx["activity_part3_none_sentence"] = sentence
    return ctx


def _speaker_context(speaker: SpeakerResult, meta: dict) -> dict:
    ctx = {
        "meta_title": meta.get("title", ""),
        "meta_date": meta.get("date", ""),
        "meta_venue": meta.get("venue", ""),
        "meta_proponent": meta.get("proponent", ""),
        "prepared_by": meta.get("prepared_by", ""),
        "checked_by": meta.get("checked_by", ""),
        "signatory_name": meta.get("signatory_name", ""),
        "signatory_role": meta.get("signatory_role", ""),
        "speaker_name": speaker.name,
        "speaker_topic": speaker.topic,
        "speaker_n": str(speaker.n),
        "speaker_topic_overall": speaker.topic_display.split(" (")[0],
        "speaker_topic_overall_label": speaker.topic_label,
        "speaker_resource_overall": speaker.resource_display.split(" (")[0],
        "speaker_resource_overall_label": speaker.resource_label,
    }
    for key, item in speaker.topic_items.items():
        tag = key.replace(".", "_")
        ctx[f"speaker_{tag}_mean"] = item.mean_display
        ctx[f"speaker_{tag}_label"] = item.interpretation
    for key, item in speaker.resource_items.items():
        tag = key.replace(".", "_")
        ctx[f"speaker_{tag}_mean"] = item.mean_display
        ctx[f"speaker_{tag}_label"] = item.interpretation
    for key in ("q1", "q2", "q3"):
        group = speaker.comments.get(key)
        ctx.update(_comment_context(f"speaker_{key}", group.lines if group else []))
    return ctx


def _remove_hotel_row(doc) -> bool:
    for table in doc.tables:
        for row in list(table.rows):
            cells = row.cells
            if cells and "hotel accommodation" in cells[0].text.strip().lower():
                tr = row._tr
                parent = tr.getparent()
                if parent is not None:
                    parent.remove(tr)
                    return True
    return False


def _set_update_fields(doc) -> None:
    settings = doc.settings.element
    for existing in settings.findall(qn("w:updateFields")):
        existing.set(qn("w:val"), "true")
        return
    element = OxmlElement("w:updateFields")
    element.set(qn("w:val"), "true")
    settings.append(element)


def _assert_no_tags(path: Path) -> None:
    doc = Document(str(path))
    texts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                texts.extend(p.text for p in cell.paragraphs)
    leftovers = [t for t in texts if "{{" in t or "{%" in t]
    if leftovers:
        raise RenderError(f"Unrendered template tags remain in {path.name}: {leftovers[:3]}")
    # A cheap structural sanity check: every table has at least one cell.
    if any(not table.rows or not table.rows[0].cells for table in doc.tables):
        raise RenderError(f"Malformed table in generated report {path.name}.")


def _escape_context(value):
    """Escape plain values for insertion into document.xml; keep RichText raw."""
    if isinstance(value, RichText):
        return value
    if isinstance(value, str):
        return xml_escape(value)
    if isinstance(value, list):
        return [_escape_context(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_escape_context(v) for v in value)
    if isinstance(value, dict):
        return {k: _escape_context(v) for k, v in value.items()}
    return value


def render_activity(activity: ActivityResult, meta: dict, output_path: Path, include_hospitality: bool) -> Path:
    ensure_dirs()
    template = COMPILED_DIR / "activity_report.docx"
    if not template.exists():
        raise RenderError("Compiled activity template is missing. Run `python -m evalapp.template_builder --force`.")
    doc = DocxTemplate(str(template))
    # docxtpl's autoescape escapes RichText's raw XML as well, which nests
    # <w:r> inside <w:t>. Escape plain strings ourselves instead.
    doc.render(_escape_context(_activity_context(activity, meta)), autoescape=False)
    doc.save(str(output_path))

    # Word-level conditional row removal. This avoids empty rows and keeps the
    # rest of the table exactly as designed.
    if not include_hospitality:
        document = Document(str(output_path))
        removed = _remove_hotel_row(document)
        if not removed:
            raise RenderError("Could not remove the hospitality row from the activity report.")
        _set_update_fields(document)
        document.core_properties.title = meta.get("title", "Activity Evaluation Report")
        document.save(str(output_path))
    else:
        document = Document(str(output_path))
        _set_update_fields(document)
        document.core_properties.title = meta.get("title", "Activity Evaluation Report")
        document.save(str(output_path))

    _assert_no_tags(output_path)
    return output_path


def render_speaker(speaker: SpeakerResult, meta: dict, output_path: Path) -> Path:
    ensure_dirs()
    template = COMPILED_DIR / "speaker_report.docx"
    if not template.exists():
        raise RenderError("Compiled speaker template is missing. Run `python -m evalapp.template_builder --force`.")
    doc = DocxTemplate(str(template))
    doc.render(_escape_context(_speaker_context(speaker, meta)), autoescape=False)
    doc.save(str(output_path))
    document = Document(str(output_path))
    _set_update_fields(document)
    document.core_properties.title = f"Speaker Evaluation - {speaker.name}"
    document.save(str(output_path))
    _assert_no_tags(output_path)
    return output_path
