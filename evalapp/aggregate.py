"""Aggregation engine: frequencies, means, interpretation labels, and comments."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

from .csvio import ParsedCSV
from .detect import Detection, SpeakerBlock
from .normalization import (
    clean_text,
    coerce_score,
    format_mean,
    format_percent,
    is_noise,
    mean_or_none,
    normalize_answer,
    precise_mean,
    round_half_up,
    score_label,
    split_comment_lines,
)


@dataclass
class ItemStats:
    key: str
    label: str
    n: int
    mean: float | None
    mean_display: str
    interpretation: str
    frequencies: list[dict]
    blank: int = 0
    noise: int = 0
    invalid: int = 0
    out_of_range: int = 0
    issues: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "n": self.n,
            "mean": self.mean,
            "mean_display": self.mean_display,
            "interpretation": self.interpretation,
            "frequencies": self.frequencies,
            "blank": self.blank,
            "noise": self.noise,
            "invalid": self.invalid,
            "out_of_range": self.out_of_range,
            "issues": self.issues,
        }


@dataclass
class CommentGroup:
    key: str
    label: str
    column: int | None
    comments: list[str] = field(default_factory=list)
    filtered_out: int = 0
    limit: int | None = None

    @property
    def count(self) -> int:
        return len(self.comments)

    @property
    def lines(self) -> list[str]:
        out: list[str] = []
        for number, comment in enumerate(self.comments, start=1):
            split = split_comment_lines(comment)
            if not split:
                continue
            out.append(f"{number}. {split[0]}")
            out.extend(split[1:])
        return out

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "column": self.column,
            "count": self.count,
            "filtered_out": self.filtered_out,
            "limit": self.limit,
            "comments": self.comments,
            "lines": self.lines,
        }


@dataclass
class ActivityResult:
    n: int
    items: dict[str, ItemStats]
    overall: float | None
    overall_label: str
    comments: dict[str, CommentGroup]
    hospitality: dict
    rows_used: list[int]
    excluded: int
    part3_sentence: str = "No comments were provided."
    warnings: list[str] = field(default_factory=list)

    @property
    def overall_display(self) -> str:
        if self.overall is None:
            return "N/A"
        return f"{format_mean(self.overall)} ({self.overall_label})"

    def as_dict(self) -> dict:
        return {
            "n": self.n,
            "overall": self.overall,
            "overall_display": self.overall_display,
            "overall_label": self.overall_label,
            "items": {k: v.as_dict() for k, v in self.items.items()},
            "item_order": list(self.items),
            "comments": {k: v.as_dict() for k, v in self.comments.items()},
            "hospitality": self.hospitality,
            "rows_used": [r + 2 for r in self.rows_used],
            "excluded": self.excluded,
            "part3_sentence": self.part3_sentence,
            "warnings": self.warnings,
        }


@dataclass
class SpeakerResult:
    index: int
    name: str
    topic: str
    n: int
    topic_items: dict[str, ItemStats]
    resource_items: dict[str, ItemStats]
    topic_overall: float | None
    topic_label: str
    resource_overall: float | None
    resource_label: str
    comments: dict[str, CommentGroup]
    rows_used: list[int]
    warnings: list[str] = field(default_factory=list)

    @property
    def topic_display(self) -> str:
        if self.topic_overall is None:
            return "N/A"
        return f"{format_mean(self.topic_overall)} ({self.topic_label})"

    @property
    def resource_display(self) -> str:
        if self.resource_overall is None:
            return "N/A"
        return f"{format_mean(self.resource_overall)} ({self.resource_label})"

    def as_dict(self) -> dict:
        return {
            "index": self.index,
            "name": self.name,
            "topic": self.topic,
            "n": self.n,
            "topic_overall": self.topic_overall,
            "topic_display": self.topic_display,
            "topic_label": self.topic_label,
            "resource_overall": self.resource_overall,
            "resource_display": self.resource_display,
            "resource_label": self.resource_label,
            "topic_items": {k: v.as_dict() for k, v in self.topic_items.items()},
            "resource_items": {k: v.as_dict() for k, v in self.resource_items.items()},
            "comments": {k: v.as_dict() for k, v in self.comments.items()},
            "rows_used": [r + 2 for r in self.rows_used],
            "warnings": self.warnings,
        }


def _consented(detection: Detection, row_idx: int) -> bool:
    if detection.consent_col is None:
        return True
    row = detection.parsed.rows[row_idx]
    value = row[detection.consent_col] if detection.consent_col < len(row) else ""
    text = normalize_answer(value)
    if not text:
        return True
    return text not in {"no", "false", "decline", "declined", "i do not consent", "do not consent"}


def _valid_score_rows(
    parsed: ParsedCSV,
    detection: Detection,
    columns: Iterable[int],
    scale_min: int,
    scale_max: int,
    noise: Iterable[str],
    row_subset: set[int] | None = None,
) -> list[int]:
    cols = [c for c in columns if c is not None]
    rows = []
    for idx, row in enumerate(parsed.rows):
        if row_subset is not None and idx not in row_subset:
            continue
        if not _consented(detection, idx):
            continue
        for col in cols:
            if col >= len(row):
                continue
            value, state = coerce_score(row[col], scale_min, scale_max, noise)
            if state == "ok":
                rows.append(idx)
                break
    return rows


def _stats(
    parsed: ParsedCSV,
    detection: Detection,
    key: str,
    label: str,
    column: int | None,
    rows: Sequence[int],
    scale_min: int,
    scale_max: int,
    legend: Sequence[dict],
    noise: Iterable[str],
) -> ItemStats:
    counts = {i: 0 for i in range(scale_min, scale_max + 1)}
    values: list[float] = []
    blank = noise_count = invalid = out_of_range = 0
    issues: list[str] = []
    for idx in rows:
        row = parsed.rows[idx]
        raw = row[column] if column is not None and column < len(row) else ""
        value, state = coerce_score(raw, scale_min, scale_max, noise)
        if state == "ok":
            values.append(float(value))
            counts[int(round(value))] = counts.get(int(round(value)), 0) + 1
        elif state == "blank":
            blank += 1
        elif state == "noise":
            noise_count += 1
        elif state == "out_of_range":
            out_of_range += 1
            if len(issues) < 8:
                issues.append(f"Row {idx + 2}: '{clean_text(raw)}' is outside {scale_min}–{scale_max}.")
        else:
            invalid += 1
            if len(issues) < 8:
                issues.append(f"Row {idx + 2}: '{clean_text(raw)}' is not a rating.")
    n = len(values)
    mean = mean_or_none(values)
    freqs = [
        {
            "score": score,
            "count": counts[score],
            "percent": round_half_up((counts[score] / n * 100) if n else 0, 1),
        }
        for score in range(scale_min, scale_max + 1)
    ]
    interpretation = score_label(mean, legend)
    return ItemStats(
        key=key,
        label=label,
        n=n,
        mean=mean,
        mean_display=format_mean(mean),
        interpretation=interpretation,
        frequencies=freqs,
        blank=blank,
        noise=noise_count,
        invalid=invalid,
        out_of_range=out_of_range,
        issues=issues,
    )


def _comments(
    parsed: ParsedCSV,
    detection: Detection,
    key: str,
    label: str,
    column: int | None,
    limit: int | None,
    noise: Iterable[str],
    row_subset: set[int] | None = None,
) -> CommentGroup:
    group = CommentGroup(key=key, label=label, column=column, limit=limit)
    if column is None:
        return group
    raw_comments = []
    for idx, row in enumerate(parsed.rows):
        if row_subset is not None and idx not in row_subset:
            continue
        if not _consented(detection, idx):
            continue
        text = clean_text(row[column]) if column < len(row) else ""
        if not text:
            continue
        if is_noise(text, noise):
            group.filtered_out += 1
            continue
        raw_comments.append(text)
    if limit is not None and limit >= 0:
        raw_comments = raw_comments[:limit]
    group.comments = raw_comments
    return group


def aggregate_activity(
    parsed: ParsedCSV,
    detection: Detection,
    mapping: dict,
    hospitality_mode: str = "na",
) -> ActivityResult:
    scale = mapping.get("scale", {"min": 1, "max": 5})
    scale_min, scale_max = int(scale.get("min", 1)), int(scale.get("max", 5))
    legend = mapping.get("legend", [])
    noise = mapping.get("noise", [])
    specs = {item["key"]: item for item in mapping.get("items", [])}
    rating_cols = list(detection.activity_cols.values())
    rows_used = _valid_score_rows(parsed, detection, rating_cols, scale_min, scale_max, noise)
    warnings: list[str] = []

    items: dict[str, ItemStats] = {}
    for spec in mapping.get("items", []):
        key = spec["key"]
        col = detection.activity_cols.get(key)
        label = spec.get("label") or key
        if col is None:
            items[key] = ItemStats(
                key=key,
                label=label,
                n=0,
                mean=None,
                mean_display="N/A",
                interpretation="N/A",
                frequencies=[
                    {"score": score, "count": 0, "percent": 0.0}
                    for score in range(scale_min, scale_max + 1)
                ],
                blank=len(rows_used),
            )
            continue
        stats = _stats(parsed, detection, key, label, col, rows_used, scale_min, scale_max, legend, noise)
        items[key] = stats
        if stats.invalid or stats.out_of_range:
            warnings.append(f"{label}: {stats.invalid + stats.out_of_range} non-rating value(s) were ignored.")
        if stats.n == 0:
            warnings.append(f"{label}: no valid ratings found.")

    overall_keys = [k for k in mapping.get("overall_keys", []) if k in items and items[k].mean is not None]
    overall = precise_mean([items[k].mean for k in overall_keys]) if overall_keys else None
    if mapping.get("overall_method") == "mean_of_rounded_item_means":
        overall = precise_mean([round_half_up(items[k].mean, 2) for k in overall_keys]) if overall_keys else None
    overall_label = score_label(overall, legend)

    comments: dict[str, CommentGroup] = {}
    limits = mapping.get("limits", {})
    for spec in mapping.get("comments", []):
        key = spec["key"]
        col = detection.activity_comments.get(key)
        comments[key] = _comments(
            parsed, detection, key, spec.get("label", key), col, limits.get(key), noise
        )

    hospitality_item = items.get("management.hospitality")
    has_hospitality_question = detection.hospitality_col is not None
    mode = (hospitality_mode or "na").lower()
    include = has_hospitality_question and mode != "omit"
    if include and hospitality_item is not None and mode == "compute":
        display = hospitality_item.mean_display
        label = hospitality_item.interpretation
    else:
        display = "N/A"
        label = "N/A"
    hospitality = {
        "has_question": has_hospitality_question,
        "include": bool(include),
        "mode": mode,
        "mean": hospitality_item.mean if include and mode == "compute" else None,
        "mean_display": display,
        "interpretation": label,
        "n": hospitality_item.n if hospitality_item else 0,
    }

    excluded = 0
    if detection.consent_col is not None:
        excluded = sum(1 for i in range(len(parsed.rows)) if not _consented(detection, i))
    if not rows_used:
        warnings.append("No activity ratings were found. The report will contain N/A values.")
    if not detection.has_speakers:
        warnings.append("No speaker question blocks detected; only an Activity Report will be generated.")

    part3_sentence = "No comments were provided."
    part3_group = comments.get("part3")
    if part3_group and part3_group.count == 0:
        col = part3_group.column
        raw_values = []
        if col is not None:
            for idx, row in enumerate(parsed.rows):
                if not _consented(detection, idx) or col >= len(row):
                    continue
                value = clean_text(row[col])
                if value:
                    raw_values.append(normalize_answer(value))
        if raw_values and all(v in {"none", "none so far", "n a", "na", "."} for v in raw_values):
            part3_sentence = "Every respondent answered “None.”"
        elif raw_values:
            part3_sentence = "No substantive comments were provided."

    return ActivityResult(
        n=len(rows_used),
        items=items,
        overall=overall,
        overall_label=overall_label,
        comments=comments,
        hospitality=hospitality,
        rows_used=rows_used,
        excluded=excluded,
        part3_sentence=part3_sentence,
        warnings=warnings,
    )


def speaker_specs(detection: Detection, provided: Sequence[dict] | None) -> list[dict]:
    """Build one logical speaker per block, or one per distinct name-column value."""
    provided = list(provided or [])
    specs: list[dict] = []
    used_provided: set[int] = set()
    for block in detection.speaker_blocks:
        if block.name_col is not None and len(block.name_values) > 1:
            # Group respondents by the speaker-name column.
            for name in block.name_values:
                match_idx = next(
                    (i for i, p in enumerate(provided) if normalize_answer(p.get("name")) == normalize_answer(name)),
                    None,
                )
                topic = ""
                if match_idx is not None:
                    topic = clean_text(provided[match_idx].get("topic"))
                    used_provided.add(match_idx)
                row_subset = {
                    idx
                    for idx, row in enumerate(detection.parsed.rows)
                    if block.name_col < len(row) and normalize_answer(row[block.name_col]) == normalize_answer(name)
                }
                specs.append({"block": block, "name": name, "topic": topic, "row_subset": row_subset})
        else:
            match_idx = None
            for i, p in enumerate(provided):
                if i in used_provided:
                    continue
                if block.name_values and normalize_answer(p.get("name")) == normalize_answer(block.name_values[0]):
                    match_idx = i
                    break
            if match_idx is None:
                match_idx = next((i for i in range(len(provided)) if i not in used_provided), None)
            name = ""
            topic = ""
            if match_idx is not None:
                name = clean_text(provided[match_idx].get("name"))
                topic = clean_text(provided[match_idx].get("topic"))
                used_provided.add(match_idx)
            if not name and block.name_values:
                name = block.name_values[0]
            if not name:
                name = f"Speaker {block.index + 1}"
            specs.append({"block": block, "name": name, "topic": topic, "row_subset": None})
    return specs


def aggregate_speaker(
    parsed: ParsedCSV,
    detection: Detection,
    spec: dict,
    mapping: dict,
) -> SpeakerResult:
    block: SpeakerBlock = spec["block"]
    row_subset: set[int] | None = spec.get("row_subset")
    topic_scale = mapping.get("topic_scale", {"min": 1, "max": 3})
    resource_scale = mapping.get("resource_scale", {"min": 1, "max": 5})
    topic_min, topic_max = int(topic_scale["min"]), int(topic_scale["max"])
    res_min, res_max = int(resource_scale["min"]), int(resource_scale["max"])
    topic_legend = mapping.get("topic_legend", [])
    resource_legend = mapping.get("resource_legend", [])
    noise = mapping.get("noise", [])
    specs = {item["key"]: item for item in mapping.get("topic_items", []) + mapping.get("resource_items", [])}

    rating_cols = list(block.items.values())
    rows_used = _valid_score_rows(
        parsed, detection, rating_cols, min(topic_min, res_min), max(topic_max, res_max), noise, row_subset
    )
    # The scale bounds differ per item; recompute membership using either scale.
    rows_used = []
    for idx, row in enumerate(parsed.rows):
        if row_subset is not None and idx not in row_subset:
            continue
        if not _consented(detection, idx):
            continue
        found = False
        for key, col in block.items.items():
            if col >= len(row):
                continue
            smin, smax = (topic_min, topic_max) if key.startswith("topic.") else (res_min, res_max)
            _, state = coerce_score(row[col], smin, smax, noise)
            if state == "ok":
                found = True
                break
        if found:
            rows_used.append(idx)

    topic_items: dict[str, ItemStats] = {}
    resource_items: dict[str, ItemStats] = {}
    warnings: list[str] = []
    for key, col in block.items.items():
        spec_item = specs.get(key, {})
        label = spec_item.get("label") or key
        if key.startswith("topic."):
            stats = _stats(parsed, detection, key, label, col, rows_used, topic_min, topic_max, topic_legend, noise)
            topic_items[key] = stats
        else:
            stats = _stats(parsed, detection, key, label, col, rows_used, res_min, res_max, resource_legend, noise)
            resource_items[key] = stats
        if stats.invalid or stats.out_of_range:
            warnings.append(f"{spec.get('name') or block.index + 1} / {label}: {stats.invalid + stats.out_of_range} non-rating value(s) ignored.")
    topic_values = [s.mean for s in topic_items.values() if s.mean is not None]
    resource_values = [s.mean for s in resource_items.values() if s.mean is not None]
    if mapping.get("overall_method") == "mean_of_rounded_item_means":
        topic_values = [round_half_up(v, 2) for v in topic_values]
        resource_values = [round_half_up(v, 2) for v in resource_values]
    topic_overall = precise_mean(topic_values)
    resource_overall = precise_mean(resource_values)
    topic_label = score_label(topic_overall, topic_legend)
    resource_label = score_label(resource_overall, resource_legend)

    comments: dict[str, CommentGroup] = {}
    limits = mapping.get("limits", {})
    provided_comments = {c["key"]: c for c in mapping.get("comments", [])}
    for key in ("q1", "q2", "q3"):
        spec_c = provided_comments.get(key, {"key": key, "label": key})
        col = block.comments.get(key)
        comments[key] = _comments(
            parsed, detection, key, spec_c.get("label", key), col, limits.get(key), noise, row_subset
        )

    if not rows_used:
        warnings.append("No valid speaker ratings found in this block.")
    return SpeakerResult(
        index=block.index,
        name=spec.get("name") or f"Speaker {block.index + 1}",
        topic=spec.get("topic") or "",
        n=len(rows_used),
        topic_items=topic_items,
        resource_items=resource_items,
        topic_overall=topic_overall,
        topic_label=topic_label,
        resource_overall=resource_overall,
        resource_label=resource_label,
        comments=comments,
        rows_used=rows_used,
        warnings=warnings,
    )


def aggregate_all(parsed: ParsedCSV, detection: Detection, activity_mapping: dict, speaker_mapping: dict, options: dict | None = None) -> dict:
    options = options or {}
    hospitality_mode = (options.get("hospitality") or {}).get("mode", "na")
    activity = aggregate_activity(parsed, detection, activity_mapping, hospitality_mode)
    specs = speaker_specs(detection, options.get("speakers"))
    speakers = [aggregate_speaker(parsed, detection, spec, speaker_mapping) for spec in specs]
    return {"activity": activity, "speakers": speakers}
