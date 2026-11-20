"""Text normalisation, numeric coercion, rating labels, and formatting."""
from __future__ import annotations

import math
import re
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Sequence

_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]")
_NUMBER_RE = re.compile(r"(?<!\d)(\d+(?:\.\d+)?)(?!\d)")
_CONTROL_RE = re.compile(r"[\u200b\u200c\u200d\ufeff]")

NOISE = {
    "n a",
    "na",
    "none",
    "nil",
    "no comment",
    "no comments",
    ".",
    "-",
    "--",
    "n a none",
}


def clean_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_RE.sub("", text)
    text = text.replace("\u00a0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines).strip()


def normalize_header(value: object) -> str:
    text = clean_text(value).lower()
    text = text.replace("&", " and ")
    text = _PUNCT_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def normalize_answer(value: object) -> str:
    return normalize_header(value)


def is_noise(value: object, noise: Iterable[str] | None = None) -> bool:
    text = normalize_answer(value)
    if not text:
        return True
    return text in set(noise or NOISE)


def round_half_up(value: float | int | Decimal | None, ndigits: int = 2) -> float | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    quant = Decimal("1").scaleb(-ndigits)
    return float(Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP))


def format_mean(value: float | None) -> str:
    rounded = round_half_up(value, 2)
    return "N/A" if rounded is None else f"{rounded:.2f}"


def format_percent(value: float | None) -> str:
    rounded = round_half_up(value, 1)
    return "N/A" if rounded is None else f"{rounded:.1f}%"


def mean_or_none(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def precise_mean(values: Sequence[float], ndigits: int | None = None) -> float | None:
    """Decimal mean (avoids binary drift at .005 boundaries such as 4.815)."""
    if not values:
        return None
    total = sum((Decimal(str(v)) for v in values), Decimal("0"))
    avg = total / Decimal(len(values))
    if ndigits is not None:
        avg = avg.quantize(Decimal("1").scaleb(-ndigits), rounding=ROUND_HALF_UP)
    return float(avg)


def score_label(mean: float | None, legend: Sequence[dict]) -> str:
    """Return the legend label for a displayed (2-dp) mean."""
    rounded = round_half_up(mean, 2)
    if rounded is None:
        return "N/A"
    for band in legend:
        lo = float(band.get("min", 0))
        hi = float(band.get("max", 99))
        if lo <= rounded <= hi:
            return str(band.get("label", ""))
    # Boundary tolerance: use nearest band if the legend has a rounding gap.
    return str(min(legend, key=lambda b: abs(rounded - float(b.get("min", 0))))["label"]) if legend else ""


def coerce_score(value: object, minimum: int, maximum: int, noise: Iterable[str] | None = None) -> tuple[float | None, str]:
    """Return (score, state). state is one of blank/noise/ok/invalid/out_of_range."""
    text = clean_text(value)
    if not text:
        return None, "blank"
    if is_noise(text, noise):
        return None, "noise"
    # Split first line; Google Forms rating answers are normally a bare number.
    candidate = text.split("\n", 1)[0].strip()
    match = _NUMBER_RE.search(candidate)
    if not match:
        return None, "invalid"
    number = float(match.group(1))
    if number < minimum or number > maximum:
        return None, "out_of_range"
    return number, "ok"


def split_comment_lines(text: str) -> list[str]:
    return [clean_text(line) for line in clean_text(text).split("\n") if clean_text(line)]


def filename_metadata(filename: str) -> dict:
    """Best-effort title/date from a Google Forms export file name."""
    stem = re.sub(r"\.csv$", "", filename or "", flags=re.I)
    clean = re.sub(r"\s*\(Responses\).*$", "", stem, flags=re.I)
    clean = re.sub(r"\s*-\s*Form Responses.*$", "", clean, flags=re.I)
    clean = clean.strip(" -_")

    detected_date = ""
    date_range = None
    m = re.search(r"(20\d{2})[_-](\d{1,2})[_-](\d{1,2})(?:\s*[-–]\s*(\d{1,2}))?", clean)
    if m:
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        end_day = int(m.group(4)) if m.group(4) else None
        try:
            start = date(year, month, day)
            if end_day and end_day != day:
                end = date(year, month, end_day)
                if start.month == end.month:
                    date_range = f"{start.strftime('%B')} {start.day} – {end.day}, {year}"
                else:
                    date_range = f"{start.strftime('%B')} {start.day} – {end.strftime('%B')} {end.day}, {year}"
            else:
                detected_date = f"{start.strftime('%B')} {start.day}, {year}"
        except ValueError:
            pass
        clean = (clean[: m.start()] + " " + clean[m.end() :]).strip(" -_")
    elif "timestamp" not in clean.lower():
        # Use the first timestamp if a file name has no date.
        pass

    title = re.sub(r"[_]+", " ", clean)
    title = _WS_RE.sub(" ", title).strip(" -_")
    title = re.sub(r"\s*\(1\)$", "", title)
    return {"title": title, "date": date_range or detected_date}


def humanize_key(key: str) -> str:
    return key.replace(".", " / ").replace("_", " ").title()


def parse_timestamp(value: str) -> datetime | None:
    text = clean_text(value)
    if not text:
        return None
    for fmt in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None
