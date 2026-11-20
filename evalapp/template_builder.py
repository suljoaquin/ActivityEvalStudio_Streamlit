"""Compile the supplied finished reports into docxtpl templates.

The source files are the user's real, fully-formatted reports.  This script only
replaces the report values with Jinja tags and converts the example comment
paragraphs into paragraph loops.  Every other package part (styles, theme,
headers, footers, images, table geometry, section properties, numbering) is left
untouched.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.shared import RGBColor
from docx.text.paragraph import Paragraph

from .paths import APP_ROOT, DOCX_DIR, TEMPLATES_CONFIG_DIR, ensure_dirs, seed_home


def _load_template_config(kind: str) -> dict:
    path = TEMPLATES_CONFIG_DIR / f"{kind}.json"
    if not path.exists():
        raise FileNotFoundError(f"Template profile not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _row_map(section: dict) -> list[tuple[int, str]]:
    return [(int(row), key) for row, key in section.get("rows", {}).items()]


def _tag_key(key: str) -> str:
    return key.replace(".", "_")


def _delete(element) -> None:
    parent = element.getparent()
    if parent is not None:
        parent.remove(element)


def _delete_paragraph(p: Paragraph) -> None:
    _delete(p._p)


def _set_paragraph_text(p: Paragraph, text: str) -> None:
    """Replace paragraph text while preserving the first run's formatting."""
    runs = list(p.runs)
    if not runs:
        p.add_run(text)
        return
    runs[0].text = text
    for run in runs[1:]:
        _delete(run._r)


def _set_cell(cell, text: str) -> None:
    paragraphs = list(cell.paragraphs)
    if not paragraphs:
        cell.text = text
        return
    _set_paragraph_text(paragraphs[0], text)
    for p in paragraphs[1:]:
        _delete_paragraph(p)


def _find_table(doc, first_text: str, second_text: str | None = None):
    for table in doc.tables:
        rows = table.rows
        if not rows or not rows[0].cells:
            continue
        first = rows[0].cells[0].text.strip()
        if first != first_text:
            continue
        if second_text is None:
            return table
        if len(rows[0].cells) > 1 and second_text in rows[0].cells[1].text:
            return table
    raise RuntimeError(f"Could not find table starting with {first_text!r}.")


def _find_paragraph(doc, predicate, start: int = 0, stop: int | None = None) -> tuple[int, Paragraph]:
    paragraphs = doc.paragraphs
    end = len(paragraphs) if stop is None else min(stop, len(paragraphs))
    for i in range(start, end):
        if predicate(paragraphs[i]):
            return i, paragraphs[i]
    raise RuntimeError("Could not find required paragraph anchor.")


def _strip_para_ids(element) -> None:
    for attr in list(element.attrib):
        if attr.endswith("}paraId") or attr.endswith("}textId"):
            del element.attrib[attr]


def _clone_after(cursor: Paragraph, prototype: Paragraph) -> Paragraph:
    new_el = copy.deepcopy(prototype._p)
    _strip_para_ids(new_el)
    cursor._p.addnext(new_el)
    return Paragraph(new_el, cursor._parent)


def _insert_tags_after(anchor: Paragraph, prototype: Paragraph, texts: list[str]) -> Paragraph:
    cursor = anchor
    for text in texts:
        new_p = _clone_after(cursor, prototype)
        _set_paragraph_text(new_p, text)
        cursor = new_p
    return cursor


def _insert_sequence_after(anchor: Paragraph, items: list[tuple[Paragraph, str]]) -> Paragraph:
    cursor = anchor
    for prototype, text in items:
        new_p = _clone_after(cursor, prototype)
        _set_paragraph_text(new_p, text)
        cursor = new_p
    return cursor


def _remove_between(doc, start: Paragraph, stop: Paragraph) -> None:
    """Remove all body paragraphs strictly between start and stop."""
    body = doc.element.body
    started = False
    to_remove = []
    for child in list(body.iterchildren()):
        if child is start._p:
            started = True
            continue
        if child is stop._p:
            break
        if started:
            to_remove.append(child)
    for child in to_remove:
        if child.tag == qn("w:p") or child.tag == qn("w:tbl"):
            _delete(child)


def _blank_between(start: Paragraph, stop: Paragraph) -> list:
    """Return deep copies of blank body paragraphs strictly between anchors."""
    out = []
    started = False
    for child in list(start._p.getparent().iterchildren()):
        if child is start._p:
            started = True
            continue
        if child is stop._p:
            break
        if started and child.tag == qn("w:p"):
            text = "".join(child.itertext()).strip()
            if not text:
                out.append(copy.deepcopy(child))
    return out


def _tag_prepared_checked(doc, first_name_contains: str, second_name_contains: str) -> None:
    """Replace the two signature names on the 'Prepared by / Checked by' line."""
    for p in doc.paragraphs:
        if first_name_contains not in p.text or second_name_contains not in p.text:
            continue
        runs = list(p.runs)
        if not runs:
            continue
        # First name: keep the underlined first-run formatting.
        runs[0].text = "{{ prepared_by }}"
        for run in runs[1:]:
            if second_name_contains in run.text:
                prefix = run.text.split(second_name_contains, 1)[0]
                run.text = prefix + "{{ checked_by }}"
                break
            # Word sometimes splits a name into "ADRIAN ERLE B. " + "VEGA".
            if any(ch.isalpha() for ch in run.text):
                run.text = ""
        return


def _keep_signature_block_together(doc, first_name_contains: str) -> None:
    """Prevent the signature block splitting between the names and role lines."""
    paragraphs = doc.paragraphs
    prep = next((i for i, p in enumerate(paragraphs) if p.text.strip().startswith("Prepared by:")), None)
    if prep is None:
        return
    names = next((i for i in range(prep + 1, len(paragraphs)) if first_name_contains in paragraphs[i].text), None)
    if names is None:
        return
    role = next(
        (
            i
            for i in range(names + 1, len(paragraphs))
            if "Committee Chairperson" in paragraphs[i].text or "Customer Satisfaction Com." in paragraphs[i].text
        ),
        None,
    )
    if role is None:
        return
    for i in range(prep, role):
        paragraphs[i].paragraph_format.keep_with_next = True
    paragraphs[role].paragraph_format.keep_with_next = False


def _comment_block(anchor: Paragraph, prototype: Paragraph, variable: str, fallback_text: str | None = None, fallback_proto: Paragraph | None = None) -> None:
    texts = [
        "{%p if " + variable + "_has_comments %}",
        "{%p for c in " + variable + "_comments %}",
        "{{ c }}",
        "{%p endfor %}",
        "{%p endif %}",
    ]
    if fallback_text is not None:
        texts += [
            "{%p if not " + variable + "_has_comments %}",
            fallback_text,
            "{%p endif %}",
        ]
    _insert_tags_after(anchor, prototype, texts)
    # The fallback paragraph is cloned from the comment prototype; make it
    # visually distinct without changing the template's font or size.
    if fallback_text is not None and fallback_proto is None:
        # locate the paragraph we just inserted by its text
        for p in anchor._parent.paragraphs:
            if p.text == fallback_text and p._p.getprevious() is not None:
                for r in p.runs:
                    r.italic = True
                break


def _build_activity(source: Path, target: Path, cfg: dict) -> None:
    doc = Document(str(source))

    meta_cfg = cfg["meta"]
    meta = _find_table(doc, meta_cfg["table_first_cell"])
    for row_idx, key in enumerate(meta_cfg.get("rows", [])):
        _set_cell(meta.rows[row_idx].cells[int(meta_cfg.get("value_col", 1))], "{{ meta_" + key + " }}")

    summary = _find_table(doc, cfg["summary"]["table_first_cell"])
    summary_values = {
        "overall": "{{ activity_overall }} ({{ activity_overall_label }})",
        "n": "{{ activity_n }}",
    }
    for key, position in cfg["summary"].get("cells", {}).items():
        _set_cell(summary.rows[int(position["row"])].cells[int(position["col"])], summary_values[key])

    criteria_cfg = cfg["criteria"]
    criteria = _find_table(doc, criteria_cfg["table_first_cell"])
    for row_idx, key in _row_map(criteria_cfg):
        tag = _tag_key(key)
        _set_cell(criteria.rows[row_idx].cells[int(criteria_cfg.get("mean_col", 1))], "{{ activity_" + tag + "_mean }}")
        _set_cell(criteria.rows[row_idx].cells[int(criteria_cfg.get("label_col", 2))], "{{ activity_" + tag + "_label }}")

    # Part II comments.
    comments_cfg = cfg["comments"]
    part2_idx, part2_heading = _find_paragraph(
        doc, lambda p: p.text.strip().startswith(comments_cfg["part2"]["heading_prefix"])
    )
    part3_idx, part3_heading = _find_paragraph(
        doc,
        lambda p: p.text.strip().startswith(comments_cfg["part2"]["next_heading_prefix"]),
        part2_idx + 1,
    )
    if part3_idx <= part2_idx + 1:
        raise RuntimeError("Part II has no comment prototype paragraph.")
    part2_proto = copy.deepcopy(doc.paragraphs[part2_idx + 1])
    part2_heading.paragraph_format.keep_with_next = True
    _remove_between(doc, part2_heading, part3_heading)
    _comment_block(part2_heading, part2_proto, "activity_part2", comments_cfg["part2"].get("fallback", "No comments were provided."))

    # Part III comments / fallback sentence.
    prep_prefix = cfg["signature"]["prepared_prefix"]
    prep_idx, prep_heading = _find_paragraph(doc, lambda p: p.text.strip().startswith(prep_prefix), part3_idx + 1)
    if prep_idx <= part3_idx + 1:
        raise RuntimeError("Part III has no fallback sentence paragraph.")
    part3_heading.paragraph_format.keep_with_next = True
    blank_protos = _blank_between(part3_heading, prep_heading)
    part3_sentence = copy.deepcopy(doc.paragraphs[part3_idx + 1])
    # Comment paragraphs in Part III are italic 11 pt in the GFPS sample.
    part3_proto = copy.deepcopy(part2_proto)
    for r in part3_proto.runs:
        r.italic = True
        r.bold = False
        r.font.color.rgb = RGBColor(0, 0, 0)
    _remove_between(doc, part3_heading, prep_heading)
    sequence = [
        (part3_proto, "{%p if activity_part3_has_comments %}"),
        (part3_proto, "{%p for c in activity_part3_comments %}"),
        (part3_proto, "{{ c }}"),
        (part3_proto, "{%p endfor %}"),
        (part3_proto, "{%p endif %}"),
        (part3_proto, "{%p if not activity_part3_has_comments %}"),
        (part3_sentence, comments_cfg["part3"].get("fallback_tag", "{{ activity_part3_none_sentence }}")),
        (part3_proto, "{%p endif %}"),
    ]
    # Keep the original blank spacing before "Prepared by".
    cursor = _insert_sequence_after(part3_heading, sequence)
    for blank in blank_protos:
        new_p = copy.deepcopy(blank)
        _strip_para_ids(new_p)
        cursor._p.addnext(new_p)
        cursor = Paragraph(new_p, part3_heading._parent)

    # Bottom signatory.
    sig_cfg = cfg["signature"]
    name_paras = [p for p in doc.paragraphs if p.text.strip() == sig_cfg["second_name_contains"]]
    if not name_paras:
        raise RuntimeError("Could not find the bottom signatory name.")
    _set_paragraph_text(name_paras[-1], "{{ signatory_name }}")
    role_paras = [p for p in doc.paragraphs if p.text.strip() == sig_cfg["role_text"]]
    if role_paras:
        _set_paragraph_text(role_paras[-1], "{{ signatory_role }}")

    _keep_signature_block_together(doc, sig_cfg["first_name_contains"])
    _tag_prepared_checked(doc, sig_cfg["first_name_contains"], sig_cfg["second_name_contains"])
    doc.save(str(target))


def _build_speaker(source: Path, target: Path, cfg: dict) -> None:
    doc = Document(str(source))

    meta_cfg = cfg["meta"]
    meta = _find_table(doc, meta_cfg["table_first_cell"])
    for row_idx, key in enumerate(meta_cfg.get("rows", [])):
        _set_cell(meta.rows[row_idx].cells[int(meta_cfg.get("value_col", 1))], "{{ meta_" + key + " }}")

    info = _find_table(doc, cfg["info"]["table_first_cell"])
    info_values = {"topic": "{{ speaker_topic }}", "name": "{{ speaker_name }}"}
    for key, position in cfg["info"].get("cells", {}).items():
        _set_cell(info.rows[int(position["row"])].cells[int(position["col"])], info_values[key])

    summary = _find_table(doc, cfg["summary"]["table_first_cell"])
    summary_values = {
        "topic": "{{ speaker_topic_overall }} ({{ speaker_topic_overall_label }})",
        "resource": "{{ speaker_resource_overall }} ({{ speaker_resource_overall_label }})",
    }
    for key, position in cfg["summary"].get("cells", {}).items():
        _set_cell(summary.rows[int(position["row"])].cells[int(position["col"])], summary_values[key])

    respondent_cfg = cfg["respondents"]
    respondent = _find_table(doc, respondent_cfg["table_first_cell"])
    _set_cell(respondent.rows[int(respondent_cfg.get("row", 0))].cells[int(respondent_cfg.get("col", 1))], "{{ speaker_n }}")

    for section_name in ("topic", "resource"):
        section_cfg = cfg[section_name]
        table = _find_table(doc, section_cfg["table_first_cell"])
        for row_idx, key in _row_map(section_cfg):
            tag = _tag_key(key)
            _set_cell(table.rows[row_idx].cells[int(section_cfg.get("mean_col", 1))], "{{ speaker_" + tag + "_mean }}")
            _set_cell(table.rows[row_idx].cells[int(section_cfg.get("label_col", 2))], "{{ speaker_" + tag + "_label }}")

    comments_cfg = cfg["comments"]
    q1_idx, q1_heading = _find_paragraph(doc, lambda p: comments_cfg["q1"] in p.text)
    q2_idx, q2_heading = _find_paragraph(doc, lambda p: comments_cfg["q2"] in p.text, q1_idx + 1)
    q3_idx, q3_heading = _find_paragraph(doc, lambda p: comments_cfg["q3"] in p.text.lower(), q2_idx + 1)
    prep_idx, prep_heading = _find_paragraph(
        doc, lambda p: p.text.strip().startswith(comments_cfg["prepared_prefix"]), q3_idx + 1
    )
    q1_heading.paragraph_format.keep_with_next = True
    q2_heading.paragraph_format.keep_with_next = True
    q3_heading.paragraph_format.keep_with_next = True

    # Comment prototypes are the first example paragraph of each section.
    if q1_idx + 1 >= q2_idx or q2_idx + 1 >= q3_idx or q3_idx + 1 >= prep_idx:
        raise RuntimeError("Speaker comment sections are missing prototype paragraphs.")
    q1_proto = copy.deepcopy(doc.paragraphs[q1_idx + 1])
    q2_proto = copy.deepcopy(doc.paragraphs[q2_idx + 1])
    # Q3 may have a separate italic "(Unedited comments)" line before comments.
    description_text = comments_cfg.get("description_text", "(unedited comments)")
    q3_desc = doc.paragraphs[q3_idx + 1]
    if q3_desc.text.strip().lower() == description_text.lower():
        q3_proto_idx = q3_idx + 2
    else:
        q3_proto_idx = q3_idx + 1
    if q3_proto_idx >= prep_idx:
        raise RuntimeError("Speaker Q3 has no comment prototype paragraph.")
    q3_proto = copy.deepcopy(doc.paragraphs[q3_proto_idx])

    _remove_between(doc, q1_heading, q2_heading)
    _comment_block(q1_heading, q1_proto, "speaker_q1", "No comments were provided.")

    _remove_between(doc, q2_heading, q3_heading)
    _comment_block(q2_heading, q2_proto, "speaker_q2", "No comments were provided.")

    q3_anchor = q3_desc if q3_desc.text.strip().lower() == description_text.lower() else q3_heading
    blank_protos = _blank_between(q3_anchor, prep_heading)
    _remove_between(doc, q3_anchor, prep_heading)
    cursor = _insert_tags_after(
        q3_anchor,
        q3_proto,
        [
            "{%p if speaker_q3_has_comments %}",
            "{%p for c in speaker_q3_comments %}",
            "{{ c }}",
            "{%p endfor %}",
            "{%p endif %}",
            "{%p if not speaker_q3_has_comments %}",
            "No comments were provided.",
            "{%p endif %}",
        ],
    )
    for blank in blank_protos:
        new_p = copy.deepcopy(blank)
        _strip_para_ids(new_p)
        cursor._p.addnext(new_p)
        cursor = Paragraph(new_p, q3_anchor._parent)

    # Remove the accidental leading spaces in the Q3 heading, keeping the bold
    # "3. What other topic..." run formatting.
    if q3_heading.runs:
        if q3_heading.runs[0].text.strip() == "" and q3_heading.runs[0].text:
            q3_heading.runs[0].text = ""
        if len(q3_heading.runs) > 1:
            q3_heading.runs[1].text = q3_heading.runs[1].text.lstrip()

    sig_cfg = cfg["signature"]
    name_paras = [p for p in doc.paragraphs if p.text.strip() == sig_cfg["second_name_contains"]]
    if not name_paras:
        raise RuntimeError("Could not find the bottom signatory name.")
    _set_paragraph_text(name_paras[-1], "{{ signatory_name }}")
    role_paras = [p for p in doc.paragraphs if p.text.strip() == sig_cfg["role_text"]]
    if role_paras:
        _set_paragraph_text(role_paras[-1], "{{ signatory_role }}")

    _keep_signature_block_together(doc, sig_cfg["first_name_contains"])
    _tag_prepared_checked(doc, sig_cfg["first_name_contains"], sig_cfg["second_name_contains"])
    doc.save(str(target))


def build_templates(force: bool = False) -> dict:
    seed_home()
    ensure_dirs()
    activity_cfg = _load_template_config("activity_report")
    speaker_cfg = _load_template_config("speaker_report")
    source_activity = APP_ROOT / activity_cfg["source"]
    source_speaker = APP_ROOT / speaker_cfg["source"]
    if not source_activity.exists() or not source_speaker.exists():
        raise FileNotFoundError("Source .docx templates are missing from docx_templates/source.")
    activity_out = APP_ROOT / activity_cfg["compiled"]
    speaker_out = APP_ROOT / speaker_cfg["compiled"]
    activity_cfg_path = TEMPLATES_CONFIG_DIR / "activity_report.json"
    speaker_cfg_path = TEMPLATES_CONFIG_DIR / "speaker_report.json"

    if force or not activity_out.exists() or max(source_activity.stat().st_mtime, activity_cfg_path.stat().st_mtime) > activity_out.stat().st_mtime:
        _build_activity(source_activity, activity_out, activity_cfg)
    if force or not speaker_out.exists() or max(source_speaker.stat().st_mtime, speaker_cfg_path.stat().st_mtime) > speaker_out.stat().st_mtime:
        _build_speaker(source_speaker, speaker_out, speaker_cfg)

    manifest = {}
    for cfg, source, output in (
        (activity_cfg, source_activity, activity_out),
        (speaker_cfg, source_speaker, speaker_out),
    ):
        manifest[cfg["id"]] = {
            "id": cfg["id"],
            "name": cfg.get("name", cfg["id"]),
            "kind": cfg.get("kind", ""),
            "source": str(source.relative_to(APP_ROOT)),
            "compiled": str(output.relative_to(APP_ROOT)),
            "template": "docxtpl",
        }
    (DOCX_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile the source reports into docxtpl templates.")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    manifest = build_templates(force=args.force)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
