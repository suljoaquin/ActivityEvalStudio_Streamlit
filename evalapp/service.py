"""Application service layer: upload -> analyse -> aggregate -> generate -> history."""
from __future__ import annotations

import json
import os
import re
import shutil
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from .aggregate import aggregate_all
from .config import (
    ConfigError,
    load_mapping,
    load_mappings,
    load_preset,
    load_presets,
    public_preset,
    save_mapping,
    save_preset,
    suggest_preset,
)
from .csvio import CSVError, ParsedCSV, parse_csv_bytes
from .detect import Detection, detect_structure
from .normalization import clean_text, filename_metadata
from .paths import CACHE_DIR, HISTORY_DIR, HOME_ROOT, UPLOAD_DIR, ensure_dirs
from .pdf import convert_docx_to_pdf, pdf_available
from .render import render_activity, render_speaker

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
UPLOAD_ID_RE = re.compile(r"^[0-9a-f]{32}$")


class AppError(ValueError):
    pass


def _safe_filename(text: str, fallback: str = "Activity") -> str:
    text = clean_text(text) or fallback
    text = text.replace("\n", " ")
    text = re.sub(r"[^\w\s.-]", "", text, flags=re.UNICODE)
    text = re.sub(r"\s+", "_", text).strip("._-")
    text = text.replace(".", "_")
    text = re.sub(r"_+", "_", text)
    text = text[:80]
    return text or fallback


def _slug_title(text: str) -> str:
    return _safe_filename(text, "Activity")


def save_upload(data: bytes, filename: str) -> dict:
    ensure_dirs()
    if not data:
        raise AppError("The uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise AppError(f"The CSV is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    upload_id = uuid.uuid4().hex
    folder = UPLOAD_DIR / upload_id
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "source.csv").write_bytes(data)
    meta = {
        "upload_id": upload_id,
        "filename": filename or "responses.csv",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    (folder / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def load_upload(upload_id: str) -> tuple[bytes, str]:
    if not UPLOAD_ID_RE.match(upload_id or ""):
        raise AppError("Invalid upload id.")
    folder = UPLOAD_DIR / upload_id
    if not folder.exists():
        raise AppError("That upload is no longer available. Please upload the CSV again.")
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    return (folder / "source.csv").read_bytes(), meta.get("filename", "responses.csv")


def _mapping_ids(preset: dict | None, activity_mapping_id: str | None, speaker_mapping_id: str | None) -> tuple[str, str]:
    activity_id = activity_mapping_id or (preset or {}).get("activity_mapping") or "pshs_activity_v1"
    speaker_id = speaker_mapping_id or (preset or {}).get("speaker_mapping") or "pshs_speaker_v1"
    return activity_id, speaker_id


def _metadata_for(filename: str, preset: dict | None) -> dict:
    inferred = filename_metadata(filename)
    defaults = {
        "title": inferred.get("title") or "Activity Evaluation",
        "date": inferred.get("date") or "",
        "venue": "",
        "proponent": "",
        "prepared_by": "ADRIAN ERLE B. VEGA",
        "checked_by": "MARJUN I. BALQUIN",
        "signatory_name": "MARJUN I. BALQUIN",
        "signatory_role": "LEAP Coordinator",
    }
    if preset:
        defaults.update(preset.get("metadata", {}))
    return defaults


def _speakers_for(detection: Detection, preset: dict | None) -> list[dict]:
    preset_speakers = list((preset or {}).get("speakers", []))
    out = []
    for idx, block in enumerate(detection.speaker_blocks):
        base = preset_speakers[idx] if idx < len(preset_speakers) else {}
        name = clean_text(base.get("name")) or (block.name_values[0] if block.name_values else f"Speaker {idx + 1}")
        topic = clean_text(base.get("topic"))
        out.append({"index": idx + 1, "name": name, "topic": topic, "block_start": block.start, "block_end": block.end})
    return out


def _hospitality_for(detection: Detection, preset: dict | None, requested: str | None = None) -> str:
    if detection.hospitality_col is None:
        return "omit"
    if requested in {"na", "compute", "omit"}:
        return requested
    preset_mode = ((preset or {}).get("hospitality") or {}).get("mode", "na")
    return preset_mode if preset_mode in {"na", "compute", "omit"} else "na"


def _column_inventory(parsed: ParsedCSV, detection: Detection, activity_mapping: dict, speaker_mapping: dict) -> list[dict]:
    labels: dict[int, tuple[str, str]] = {}
    for spec in activity_mapping.get("items", []):
        if spec["key"] in detection.activity_cols:
            labels[detection.activity_cols[spec["key"]]] = ("activity", spec.get("label") or spec["key"])
    for spec in activity_mapping.get("comments", []):
        if spec["key"] in detection.activity_comments:
            labels[detection.activity_comments[spec["key"]]] = ("activity comment", spec.get("label") or spec["key"])
    for block in detection.speaker_blocks:
        for spec in speaker_mapping.get("topic_items", []) + speaker_mapping.get("resource_items", []):
            if spec["key"] in block.items:
                labels[block.items[spec["key"]]] = (f"speaker {block.index + 1}", spec.get("label") or spec["key"])
        for spec in speaker_mapping.get("comments", []):
            if spec["key"] in block.comments:
                labels[block.comments[spec["key"]]] = (f"speaker {block.index + 1} comment", spec.get("label") or spec["key"])
    out = []
    for idx, header in enumerate(parsed.headers):
        kind, label = labels.get(idx, ("unmapped", ""))
        out.append({"index": idx, "header": header, "kind": kind, "label": label})
    return out


def _validation(parsed, detection, meta, speakers, activity, mapping_ids, preset, anomaly_notes) -> dict:
    checks: list[dict] = []

    def add(status: str, label: str, detail: str = ""):
        checks.append({"status": status, "label": label, "detail": detail})

    if detection.activity_cols:
        add("ok", "Activity form detected", f"{len(detection.activity_cols)} rating questions mapped.")
    else:
        add("error", "Activity form not detected", "No A/B/C activity rating columns matched the mapping.")
    if detection.has_speakers:
        add("ok", f"{detection.speaker_count} speaker block(s) detected", "One report will be generated per speaker.")
    else:
        add("ok", "No speaker blocks detected", "Only the Activity Report will be generated.")
    if detection.hospitality_col is None:
        add("ok", "Hospitality row omitted", "The form has no hotel/accommodation question; the empty row will be removed.")
    else:
        add("ok", "Hospitality question detected", "Keep it as N/A or compute it from the responses using the toggle.")
    if detection.consent_col is not None and activity.excluded:
        add("warn", "Consent exclusions", f"{activity.excluded} response(s) declined consent and were excluded.")
    if not meta.get("title"):
        add("error", "Activity title missing", "Enter the activity title before generating.")
    if not meta.get("date"):
        add("warn", "Activity date missing", "The Date row will be blank.")
    if not meta.get("venue"):
        add("warn", "Venue missing", "The Venue row will be blank.")
    if not meta.get("proponent"):
        add("warn", "Proponent missing", "The Proponent row will be blank.")
    for idx, speaker in enumerate(speakers, start=1):
        if not speaker.get("name"):
            add("error", f"Speaker {idx} name missing", "Each speaker report needs a resource-person name.")
        if not speaker.get("topic"):
            add("warn", f"Speaker {idx} topic missing", "The Topic/s cell will be blank.")
    if detection.unknown_activity_headers:
        add("warn", "Unmapped activity columns", f"{len(detection.unknown_activity_headers)} column(s) will not appear in the report.")
    missing = detection.mapping_status.get("activity_missing", [])
    if missing:
        add("warn", "Incomplete activity mapping", "Missing: " + ", ".join(missing))
    if preset:
        expected = ((preset.get("match") or {}).get("speaker_count"))
        if expected is not None and int(expected) != detection.speaker_count:
            add(
                "warn",
                "Preset speaker count differs",
                f"Preset expects {expected} speaker(s); CSV contains {detection.speaker_count}. Edit the speaker list before generating.",
            )
    statuses = {c["status"] for c in checks}
    ready = "error" not in statuses
    return {
        "ready": ready,
        "checks": checks,
        "respondents": activity.n,
        "speaker_count": detection.speaker_count,
        "sections": {
            "activity": True,
            "speakers": detection.speaker_count,
            "hospitality": activity.hospitality,
        },
        "mapping": mapping_ids,
    }


def _preset_for(preset_id: str | None, filename: str, speaker_count: int) -> dict | None:
    if preset_id in {"__none__", "none"}:
        return None
    if preset_id:
        return load_preset(preset_id)
    return suggest_preset(filename, speaker_count)


def analyze_bytes(
    data: bytes,
    filename: str,
    preset_id: str | None = None,
    activity_mapping_id: str | None = None,
    speaker_mapping_id: str | None = None,
    overrides: dict | None = None,
    hospitality_mode: str | None = None,
) -> dict:
    parsed = parse_csv_bytes(data)
    preset = _preset_for(preset_id, filename, _guess_speaker_count(parsed))
    activity_id, speaker_id = _mapping_ids(preset, activity_mapping_id, speaker_mapping_id)
    activity_mapping = load_mapping(activity_id)
    speaker_mapping = load_mapping(speaker_id)
    detection = detect_structure(parsed, activity_mapping, speaker_mapping, overrides=overrides)

    # Re-suggest now that we know the real block count, unless the caller chose one.
    if not preset_id and preset is None:
        preset = suggest_preset(filename, detection.speaker_count)
        if preset:
            activity_id, speaker_id = _mapping_ids(preset, activity_mapping_id, speaker_mapping_id)
            activity_mapping = load_mapping(activity_id)
            speaker_mapping = load_mapping(speaker_id)
            detection = detect_structure(parsed, activity_mapping, speaker_mapping, overrides=overrides)

    meta = _metadata_for(filename, preset)
    speakers = _speakers_for(detection, preset)
    mode = _hospitality_for(detection, preset, hospitality_mode)
    options = {
        "hospitality": {"mode": mode, "applicable": mode == "compute"},
        "speakers": speakers,
    }
    results = aggregate_all(parsed, detection, activity_mapping, speaker_mapping, options)
    activity = results["activity"]
    speaker_results = results["speakers"]
    anomaly_notes = list((preset or {}).get("anomaly_notes", []))
    mapping_ids = {"activity": activity_id, "speaker": speaker_id}
    validation = _validation(parsed, detection, meta, speakers, activity, mapping_ids, preset, anomaly_notes)

    inventory = _column_inventory(parsed, detection, activity_mapping, speaker_mapping)
    preview_cols = [c for c in inventory if c["kind"] != "unmapped"][:12]
    sample_rows = [[parsed.rows[r][c["index"]] for c in preview_cols] for r in range(min(4, len(parsed.rows)))]

    warnings = []
    warnings.extend(parsed.warnings)
    warnings.extend(detection.warnings)
    warnings.extend(activity.warnings)
    for speaker in speaker_results:
        warnings.extend(speaker.warnings)

    return {
        "filename": filename,
        "csv": {
            "rows": parsed.row_count,
            "columns": len(parsed.headers),
            "encoding": parsed.encoding,
            "headers": parsed.headers,
            "warnings": parsed.warnings,
            "inventory": inventory,
            "preview_columns": preview_cols,
            "preview_rows": sample_rows,
        },
        "detection": detection.as_dict(),
        "metadata": meta,
        "speakers": speakers,
        "preset": public_preset(preset) if preset else None,
        "preset_id": (preset or {}).get("id"),
        "mapping_ids": mapping_ids,
        "mappings": {"activity": activity_mapping, "speaker": speaker_mapping},
        "available_mappings": [{"id": m["id"], "name": m.get("name", m["id"])} for m in load_mappings()],
        "hospitality_mode": mode,
        "validation": validation,
        "stats": {
            "activity": activity.as_dict(),
            "speakers": [s.as_dict() for s in speaker_results],
        },
        "warnings": list(dict.fromkeys(warnings)),
        "anomaly_notes": anomaly_notes,
    }


def _guess_speaker_count(parsed: ParsedCSV) -> int:
    """Cheap count used to choose a preset before full detection."""
    from .normalization import normalize_header

    return sum(1 for h in parsed.headers if "depth of content" in normalize_header(h))


def analyze_upload(upload_id: str, **kwargs) -> dict:
    data, filename = load_upload(upload_id)
    result = analyze_bytes(data, filename, **kwargs)
    result["upload_id"] = upload_id
    result["available_presets"] = [public_preset(p) for p in load_presets()]
    return result


def _sanitize_meta(raw: dict) -> dict:
    allowed = ["title", "date", "venue", "proponent", "prepared_by", "checked_by", "signatory_name", "signatory_role"]
    return {k: clean_text(raw.get(k, "")) for k in allowed}


def _sanitize_speakers(raw: list[dict]) -> list[dict]:
    out = []
    for idx, item in enumerate(raw or []):
        out.append(
            {
                "name": clean_text(item.get("name", "")),
                "topic": clean_text(item.get("topic", "")),
                "index": idx + 1,
            }
        )
    return out


def generate_report(upload_id: str, payload: dict) -> dict:
    ensure_dirs()
    data, filename = load_upload(upload_id)
    parsed = parse_csv_bytes(data)
    preset_id = payload.get("preset_id")
    preset = _preset_for(preset_id, filename, _guess_speaker_count(parsed))
    activity_id = payload.get("activity_mapping_id") or (preset or {}).get("activity_mapping") or "pshs_activity_v1"
    speaker_id = payload.get("speaker_mapping_id") or (preset or {}).get("speaker_mapping") or "pshs_speaker_v1"
    activity_mapping = load_mapping(activity_id)
    speaker_mapping = load_mapping(speaker_id)
    detection = detect_structure(parsed, activity_mapping, speaker_mapping, overrides=payload.get("overrides"))
    if not detection.has_speakers and payload.get("speakers"):
        # The UI may have edited speakers, but the CSV is authoritative.
        payload_speakers = []
    else:
        payload_speakers = _sanitize_speakers(payload.get("speakers") or [])
    if not payload_speakers:
        payload_speakers = _speakers_for(detection, preset)
    if len(payload_speakers) != detection.speaker_count:
        # Pad/truncate to the detected blocks so a stale browser cannot create
        # phantom reports.
        if len(payload_speakers) < detection.speaker_count:
            payload_speakers += [
                {"name": f"Speaker {i + 1}", "topic": "", "index": i + 1}
                for i in range(len(payload_speakers), detection.speaker_count)
            ]
        else:
            payload_speakers = payload_speakers[: detection.speaker_count]

    meta = _sanitize_meta(payload.get("metadata") or _metadata_for(filename, preset))
    mode = _hospitality_for(detection, preset, (payload.get("hospitality") or {}).get("mode"))
    options = {"hospitality": {"mode": mode, "applicable": mode == "compute"}, "speakers": payload_speakers}
    results = aggregate_all(parsed, detection, activity_mapping, speaker_mapping, options)
    activity = results["activity"]
    speakers = results["speakers"]
    if not meta.get("title"):
        raise AppError("The activity title is required.")
    if not detection.activity_cols:
        raise AppError("No activity rating columns were detected; check the mapping.")

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    run_dir = HISTORY_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    title_slug = _slug_title(meta.get("title", "Activity"))
    activity_name = f"{title_slug}_Activity_Report.docx"
    activity_path = run_dir / activity_name
    files = []
    warnings: list[str] = []
    try:
        render_activity(activity, meta, activity_path, activity.hospitality["include"])
        files.append({"name": activity_name, "kind": "activity", "label": "Activity Report", "size": activity_path.stat().st_size})
        for idx, speaker in enumerate(speakers, start=1):
            sp_name = _slug_title(speaker.name or f"Speaker_{idx}")
            name = f"{title_slug}_Speaker_{idx:02d}_{sp_name}.docx"
            path = run_dir / name
            render_speaker(speaker, meta, path)
            files.append(
                {
                    "name": name,
                    "kind": "speaker",
                    "label": f"Speaker {idx}: {speaker.name}",
                    "size": path.stat().st_size,
                }
            )
    except Exception as exc:
        shutil.rmtree(run_dir, ignore_errors=True)
        raise AppError(f"Report generation failed: {exc}") from exc

    pdf_warnings = []
    if payload.get("make_pdf"):
        for item in files:
            src = run_dir / item["name"]
            pdf_name = src.with_suffix(".pdf").name
            pdf_path = run_dir / pdf_name
            ok, detail = convert_docx_to_pdf(src, pdf_path)
            if ok:
                item["pdf"] = pdf_name
            else:
                pdf_warnings.append(f"{item['label']}: {detail}")
    if pdf_warnings:
        warnings.extend(pdf_warnings)

    zip_name = f"{title_slug}_Evaluation_Package.zip"
    zip_path = run_dir / zip_name
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item in files:
            zf.write(run_dir / item["name"], item["name"])
            if item.get("pdf"):
                zf.write(run_dir / item["pdf"], item["pdf"])
        zf.writestr("README.txt", _package_readme(meta, activity, speakers))

    manifest = {
        "id": run_id,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "filename": filename,
        "title": meta.get("title", "Activity Evaluation"),
        "date": meta.get("date", ""),
        "venue": meta.get("venue", ""),
        "proponent": meta.get("proponent", ""),
        "n": activity.n,
        "speaker_count": len(speakers),
        "speakers": [{"name": s.name, "n": s.n} for s in speakers],
        "files": files,
        "zip": zip_name,
        "pdf": bool(payload.get("make_pdf")),
        "warnings": warnings,
        "hospitality": activity.hospitality,
        "mapping": {"activity": activity_id, "speaker": speaker_id},
        "preset_id": (preset or {}).get("id") if preset else None,
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def _package_readme(meta: dict, activity, speakers) -> str:
    lines = [
        meta.get("title", "Activity Evaluation"),
        meta.get("date", ""),
        "",
        "Generated by the PSHS Activity Evaluation Report Generator.",
        f"Activity respondents: {activity.n}",
    ]
    for idx, speaker in enumerate(speakers, start=1):
        lines.append(f"Speaker {idx}: {speaker.name} — respondents: {speaker.n}")
    lines.extend(
        [
            "",
            "Each .docx is built from the committee's Word template; headers, footers, logos, tables, and page settings are preserved.",
            "PDFs, when included, are generated with LibreOffice and may paginate slightly differently from Microsoft Word.",
        ]
    )
    return "\n".join(lines) + "\n"


def list_history(limit: int = 50) -> list[dict]:
    ensure_dirs()
    runs = []
    for folder in HISTORY_DIR.iterdir():
        manifest_path = folder / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        runs.append(manifest)
    runs.sort(key=lambda m: m.get("created_at", ""), reverse=True)
    return runs[:limit]


def get_run(run_id: str) -> dict:
    if not re.match(r"^[0-9]{8}-[0-9]{6}-[0-9a-f]{6}$", run_id or ""):
        raise AppError("Invalid report id.")
    folder = HISTORY_DIR / run_id
    manifest = folder / "manifest.json"
    if not manifest.exists():
        raise AppError("That report package does not exist.")
    return json.loads(manifest.read_text(encoding="utf-8"))


def run_file_path(run_id: str, filename: str) -> Path:
    manifest = get_run(run_id)
    allowed = {f["name"] for f in manifest.get("files", [])}
    allowed.add(manifest.get("zip", ""))
    for item in manifest.get("files", []):
        if item.get("pdf"):
            allowed.add(item["pdf"])
    if filename not in allowed:
        raise AppError("File not found in this report package.")
    path = HISTORY_DIR / run_id / filename
    if not path.exists():
        raise AppError("File not found in this report package.")
    return path


def retry_pdfs(run_id: str) -> dict:
    manifest = get_run(run_id)
    folder = HISTORY_DIR / run_id
    warnings = []
    for item in manifest.get("files", []):
        if item.get("pdf"):
            continue
        src = folder / item["name"]
        pdf_name = src.with_suffix(".pdf").name
        ok, detail = convert_docx_to_pdf(src, folder / pdf_name)
        if ok:
            item["pdf"] = pdf_name
        else:
            warnings.append(f"{item['label']}: {detail}")
    manifest["pdf"] = any(f.get("pdf") for f in manifest.get("files", []))
    manifest["warnings"] = warnings
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    # Rebuild the zip so it contains the new PDFs.
    zip_path = folder / manifest["zip"]
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item in manifest.get("files", []):
            zf.write(folder / item["name"], item["name"])
            if item.get("pdf"):
                zf.write(folder / item["pdf"], item["pdf"])
    return manifest


def bootstrap() -> dict:
    return {
        "presets": [public_preset(p) for p in load_presets()],
        "mappings": [{"id": m["id"], "name": m.get("name", m["id"])} for m in load_mappings()],
        "history": list_history(),
        "pdf_available": pdf_available(),
    }


def persist_mapping(data: dict) -> dict:
    return save_mapping(data)


def persist_preset(data: dict) -> dict:
    return save_preset(data)


DEMO_SAMPLES = {
    "leap": {
        "path": "samples/leap_with_speakers.csv",
        "filename": "2026_09_30 LeAP Capability Training (Responses).csv",
        "preset_id": "leap_2026_09_30",
    },
    "gfps": {
        "path": "samples/gfps_no_speakers.csv",
        "filename": "2026_10_28-29 PSHS-SRC GFPS Deepening Session (Responses).csv",
        "preset_id": "gfps_2026_10_28",
    },
}


def analyze_demo(sample: str) -> dict:
    spec = DEMO_SAMPLES.get(sample)
    if not spec:
        raise AppError("Unknown demo sample.")
    path = HOME_ROOT / spec["path"]
    if not path.exists():
        raise AppError("The demo CSV is not available.")
    meta = save_upload(path.read_bytes(), spec["filename"])
    result = analyze_upload(meta["upload_id"], preset_id=spec["preset_id"])
    result["demo"] = sample
    return result

