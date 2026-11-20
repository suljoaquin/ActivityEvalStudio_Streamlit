"""Load and persist mapping/preset/template configuration."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .paths import MAPPINGS_DIR, PRESETS_DIR, DOCX_DIR


class ConfigError(ValueError):
    pass


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"Configuration file not found: {path.name}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path.name} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path.name} must contain a JSON object.")
    return data


def load_mapping(mapping_id: str) -> dict:
    for path in MAPPINGS_DIR.glob("*.json"):
        data = _read_json(path)
        if data.get("id") == mapping_id:
            return data
    raise ConfigError(f"Unknown mapping '{mapping_id}'.")


def load_mappings() -> list[dict]:
    out = []
    for path in sorted(MAPPINGS_DIR.glob("*.json")):
        data = _read_json(path)
        if data.get("id"):
            out.append(data)
    return out


def save_mapping(data: dict) -> dict:
    mapping_id = str(data.get("id") or "").strip()
    if not mapping_id or not all(c.isalnum() or c in "-_" for c in mapping_id):
        raise ConfigError("Mapping id must use letters, digits, hyphens, or underscores.")
    path = MAPPINGS_DIR / f"{mapping_id}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return data


def load_preset(preset_id: str) -> dict:
    for path in PRESETS_DIR.glob("*.json"):
        data = _read_json(path)
        if data.get("id") == preset_id:
            return data
    raise ConfigError(f"Unknown preset '{preset_id}'.")


def load_presets() -> list[dict]:
    out = []
    for path in sorted(PRESETS_DIR.glob("*.json")):
        data = _read_json(path)
        if data.get("id"):
            out.append(data)
    return out


def save_preset(data: dict) -> dict:
    preset_id = str(data.get("id") or "").strip()
    if not preset_id or not all(c.isalnum() or c in "-_" for c in preset_id):
        raise ConfigError("Preset id must use letters, digits, hyphens, or underscores.")
    path = PRESETS_DIR / f"{preset_id}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return data


def load_template_manifest() -> dict:
    path = DOCX_DIR / "manifest.json"
    return _read_json(path)


def suggest_preset(filename: str, speaker_count: int) -> dict | None:
    name = (filename or "").lower()
    candidates = []
    for preset in load_presets():
        match = preset.get("match") or {}
        needles = [str(n).lower() for n in match.get("filename_contains", [])]
        count = match.get("speaker_count")
        score = 0
        if needles and not any(n in name for n in needles):
            continue
        if count is not None:
            if int(count) != speaker_count:
                continue
            score += 2
        score += sum(1 for n in needles if n in name)
        candidates.append((score, preset))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def public_preset(preset: dict) -> dict:
    """Preset shape safe to expose to the browser."""
    return {
        "id": preset.get("id"),
        "name": preset.get("name"),
        "metadata": preset.get("metadata", {}),
        "speakers": preset.get("speakers", []),
        "hospitality": preset.get("hospitality", {"mode": "na", "applicable": False}),
        "notes": preset.get("notes", ""),
        "anomaly_notes": preset.get("anomaly_notes", []),
        "activity_mapping": preset.get("activity_mapping"),
        "speaker_mapping": preset.get("speaker_mapping"),
    }
