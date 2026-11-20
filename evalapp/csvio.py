"""CSV parsing that tolerates Google Forms exports, duplicate headers, and ragged rows."""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Iterable

from .normalization import clean_text


class CSVError(ValueError):
    """A user-fixable CSV problem."""


@dataclass
class ParsedCSV:
    headers: list[str]
    rows: list[list[str]]
    warnings: list[str] = field(default_factory=list)
    encoding: str = "utf-8-sig"

    @property
    def row_count(self) -> int:
        return len(self.rows)

    def get(self, row: list[str], index: int) -> str:
        if index is None or index < 0 or index >= len(row):
            return ""
        return row[index]


def _decode(data: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise CSVError("The uploaded file is not valid UTF-8 or Windows-1252 text.")


def parse_csv_bytes(data: bytes) -> ParsedCSV:
    if not data:
        raise CSVError("The uploaded CSV is empty.")
    text, encoding = _decode(data)
    if not text.strip():
        raise CSVError("The uploaded CSV is empty.")
    try:
        reader = csv.reader(io.StringIO(text, newline=""))
        raw_rows = list(reader)
    except csv.Error as exc:
        raise CSVError(f"Could not parse the CSV: {exc}") from exc

    # Google exports occasionally contain a blank first row.
    raw_rows = [r for r in raw_rows if any(clean_text(c) for c in r)]
    if len(raw_rows) < 2:
        raise CSVError("The CSV needs a header row and at least one response row.")

    headers = [clean_text(h).replace("\ufeff", "") for h in raw_rows[0]]
    if not any(headers):
        raise CSVError("The CSV header row is empty.")

    width = len(headers)
    rows: list[list[str]] = []
    warnings: list[str] = []
    for line_no, raw in enumerate(raw_rows[1:], start=2):
        if len(raw) == width:
            row = raw
        elif len(raw) < width:
            row = raw + [""] * (width - len(raw))
            if any(clean_text(c) for c in raw):
                warnings.append(f"Row {line_no} has {len(raw)} of {width} columns; missing cells were treated as blank.")
        else:
            row = raw[:width]
            warnings.append(f"Row {line_no} has {len(raw)} columns (expected {width}); extra cells were ignored.")
        rows.append([clean_text(c) for c in row])

    if not rows:
        raise CSVError("The CSV has no response rows.")
    if len(headers) != len(set(headers)):
        repeated = sorted({h for h in headers if headers.count(h) > 1})
        warnings.append(
            f"{len(repeated)} question label(s) repeat across speaker blocks; columns are matched by position and block, not only by header name."
        )
    return ParsedCSV(headers=headers, rows=rows, warnings=warnings, encoding=encoding)
