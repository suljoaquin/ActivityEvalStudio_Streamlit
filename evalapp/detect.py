"""Detect activity/speaker/hospitality structure from CSV headers."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .csvio import ParsedCSV
from .normalization import clean_text, normalize_answer, normalize_header


@dataclass
class SpeakerBlock:
    index: int
    start: int
    end: int
    items: dict[str, int] = field(default_factory=dict)
    comments: dict[str, int] = field(default_factory=dict)
    name_col: int | None = None
    name_values: list[str] = field(default_factory=list)
    headers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "index": self.index,
            "start": self.start,
            "end": self.end,
            "items": self.items,
            "comments": self.comments,
            "name_col": self.name_col,
            "name_values": self.name_values,
            "headers": self.headers,
            "warnings": self.warnings,
        }


@dataclass
class Detection:
    parsed: ParsedCSV
    activity_cols: dict[str, int]
    activity_comments: dict[str, int]
    speaker_blocks: list[SpeakerBlock]
    consent_col: int | None
    ignored_cols: list[int]
    activity_end: int
    hospitality_col: int | None
    warnings: list[str] = field(default_factory=list)
    unknown_activity_headers: list[str] = field(default_factory=list)
    mapping_status: dict = field(default_factory=dict)

    @property
    def has_speakers(self) -> bool:
        return bool(self.speaker_blocks)

    @property
    def speaker_count(self) -> int:
        return len(self.speaker_blocks)

    def as_dict(self) -> dict:
        return {
            "activity_columns": self.activity_cols,
            "activity_comments": self.activity_comments,
            "speaker_blocks": [b.as_dict() for b in self.speaker_blocks],
            "speaker_count": self.speaker_count,
            "has_speakers": self.has_speakers,
            "consent_column": self.consent_col,
            "ignored_columns": self.ignored_cols,
            "activity_end": self.activity_end,
            "hospitality_column": self.hospitality_col,
            "warnings": self.warnings,
            "unknown_activity_headers": self.unknown_activity_headers,
            "mapping_status": self.mapping_status,
        }


def _contains(norm: str, patterns: Iterable[str]) -> bool:
    return any(normalize_header(p) in norm for p in patterns)


def _find_cols(headers: list[str], specs: list[dict], start: int, end: int, used: set[int]) -> tuple[dict[str, int], list[str]]:
    mapping: dict[str, int] = {}
    missing: list[str] = []
    for spec in specs:
        key = str(spec.get("key") or "")
        patterns = spec.get("patterns") or []
        found = None
        for idx in range(start, end):
            if idx in used:
                continue
            norm = normalize_header(headers[idx])
            if _contains(norm, patterns):
                found = idx
                break
        if found is None:
            missing.append(key)
        else:
            mapping[key] = found
            used.add(found)
    return mapping, missing


def _consent_yes(value: str) -> bool:
    text = normalize_answer(value)
    if not text:
        return True
    return text not in {"no", "false", "decline", "declined", "i do not consent", "do not consent"}


def _speaker_name_col(headers: list[str], start: int, end: int, patterns: Iterable[str]) -> int | None:
    for idx in range(start, end):
        norm = normalize_header(headers[idx])
        if norm in {"resource person", "speaker", "name of resource person"}:
            return idx
        if _contains(norm, patterns):
            return idx
    return None


def detect_structure(
    parsed: ParsedCSV,
    activity_mapping: dict,
    speaker_mapping: dict,
    overrides: dict | None = None,
) -> Detection:
    overrides = overrides or {}
    headers = parsed.headers
    norms = [normalize_header(h) for h in headers]
    warnings: list[str] = []

    # Consent is usually immediately after timestamp/email.
    consent_col = overrides.get("consent_col")
    if consent_col is None:
        for i, norm in enumerate(norms):
            if _contains(norm, activity_mapping.get("consent_patterns", ["consent"])):
                consent_col = i
                break
    if consent_col is not None:
        consent_col = int(consent_col)

    ignored_cols = []
    for i, norm in enumerate(norms):
        if _contains(norm, activity_mapping.get("ignore_patterns", [])):
            ignored_cols.append(i)

    # A speaker block always contains the topic depth question. Repeated
    # identical blocks (Google Forms repeats the whole page) delimit speakers.
    depth_indices = [i for i, norm in enumerate(norms) if "depth of content" in norm]
    if not depth_indices:
        # Fallback for a form that starts the speaker page at "Attainment".
        attainment = [i for i, norm in enumerate(norms) if "attainment of topic objectives" in norm]
        if attainment:
            depth_indices = [max(0, attainment[0] - 3)]

    if overrides.get("speaker_blocks"):
        block_ranges = []
        for raw in overrides["speaker_blocks"]:
            if not isinstance(raw, dict) or "start" not in raw:
                continue
            start = int(raw["start"])
            end = int(raw.get("end", start + 15))
            if 0 <= start <= end < len(headers):
                block_ranges.append((start, end))
    else:
        block_ranges = []
        for n, start in enumerate(depth_indices):
            end = depth_indices[n + 1] - 1 if n + 1 < len(depth_indices) else len(headers) - 1
            block_ranges.append((start, end))

    activity_end = int(overrides.get("activity_end", block_ranges[0][0] if block_ranges else len(headers)))
    activity_end = max(0, min(activity_end, len(headers)))

    used_activity: set[int] = set(ignored_cols)
    if consent_col is not None:
        used_activity.add(consent_col)
    activity_items = activity_mapping.get("items", [])
    activity_cols, missing_activity_all = _find_cols(
        headers, activity_items, 0, activity_end, used_activity
    )
    optional_keys = {str(item.get("key")) for item in activity_items if item.get("optional")}
    missing_activity = [key for key in missing_activity_all if key not in optional_keys]
    activity_comments, missing_comments = _find_cols(
        headers, activity_mapping.get("comments", []), 0, activity_end, used_activity
    )
    if missing_activity:
        warnings.append("Activity mapping did not find: " + ", ".join(missing_activity) + ".")
    if missing_comments:
        warnings.append("Activity comment mapping did not find: " + ", ".join(missing_comments) + ".")

    unknown_activity_headers = []
    for idx in range(activity_end):
        if idx in used_activity:
            continue
        if not clean_text(headers[idx]):
            continue
        unknown_activity_headers.append(headers[idx])
    if unknown_activity_headers:
        warnings.append(f"{len(unknown_activity_headers)} activity column(s) are not mapped; they will appear in the preview but not in the report.")

    hospitality_col = activity_cols.get("management.hospitality")
    if overrides.get("hospitality_col") is not None:
        try:
            hospitality_col = int(overrides["hospitality_col"])
        except (TypeError, ValueError):
            pass

    blocks: list[SpeakerBlock] = []
    for n, (start, end) in enumerate(block_ranges):
        used: set[int] = set()
        items, missing_items = _find_cols(
            headers, speaker_mapping.get("topic_items", []) + speaker_mapping.get("resource_items", []), start, end + 1, used
        )
        comments, missing_sp_comments = _find_cols(
            headers, speaker_mapping.get("comments", []), start, end + 1, used
        )
        name_col = _speaker_name_col(headers, start, end + 1, speaker_mapping.get("speaker_name_patterns", []))
        name_values = []
        if name_col is not None:
            seen = set()
            for row in parsed.rows:
                value = clean_text(row[name_col]) if name_col < len(row) else ""
                if value and normalize_answer(value) not in seen:
                    seen.add(normalize_answer(value))
                    name_values.append(value)
        block = SpeakerBlock(
            index=n,
            start=start,
            end=end,
            items=items,
            comments=comments,
            name_col=name_col,
            name_values=name_values,
            headers=headers[start : end + 1],
            warnings=[],
        )
        if missing_items:
            block.warnings.append("Speaker mapping did not find: " + ", ".join(missing_items) + ".")
            warnings.append(f"Speaker {n + 1}: mapping did not find " + ", ".join(missing_items) + ".")
        if missing_sp_comments:
            block.warnings.append("Speaker comment mapping did not find: " + ", ".join(missing_sp_comments) + ".")
        if not items:
            warnings.append(f"Speaker block {n + 1} has no recognised rating questions.")
        blocks.append(block)

    # Consent scope is reported for transparency.
    consent_excluded = 0
    if consent_col is not None:
        consent_excluded = sum(
            1 for row in parsed.rows if not _consent_yes(row[consent_col] if consent_col < len(row) else "")
        )
    if consent_excluded:
        warnings.append(f"{consent_excluded} response(s) declined consent and will be excluded from all calculations.")

    return Detection(
        parsed=parsed,
        activity_cols=activity_cols,
        activity_comments=activity_comments,
        speaker_blocks=blocks,
        consent_col=consent_col,
        ignored_cols=ignored_cols,
        activity_end=activity_end,
        hospitality_col=hospitality_col,
        warnings=warnings,
        unknown_activity_headers=unknown_activity_headers,
        mapping_status={
            "activity_missing": missing_activity,
            "activity_comments_missing": missing_comments,
            "speaker_blocks": len(blocks),
        },
    )


def participating_rows(detection: Detection, columns: Iterable[int]) -> list[int]:
    """Rows that consented and supplied at least one non-empty cell in columns."""
    out = []
    cols = [c for c in columns if c is not None]
    for row_idx, row in enumerate(detection.parsed.rows):
        if detection.consent_col is not None:
            value = row[detection.consent_col] if detection.consent_col < len(row) else ""
            if not _consent_yes(value):
                continue
        if any(clean_text(row[c]) for c in cols if c < len(row)):
            out.append(row_idx)
    return out
