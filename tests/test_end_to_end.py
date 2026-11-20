from __future__ import annotations

import io
import re
from pathlib import Path

import pytest
from docx import Document
from docx.oxml.ns import qn

import evalapp.service as service
from app import app

APP_ROOT = Path(__file__).resolve().parent.parent
SAMPLES = APP_ROOT / "samples"
SOURCES = APP_ROOT / "docx_templates" / "source"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    uploads = tmp_path / "uploads"
    history = tmp_path / "history"
    uploads.mkdir()
    history.mkdir()
    monkeypatch.setattr(service, "UPLOAD_DIR", uploads)
    monkeypatch.setattr(service, "HISTORY_DIR", history)
    app.config.update(TESTING=True)
    return app.test_client()


def upload(client, sample_name: str):
    data = (SAMPLES / sample_name).read_bytes()
    response = client.post(
        "/api/analyze",
        data={"file": (io.BytesIO(data), sample_name)},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def generate(client, analysis, *, make_pdf=False, hospitality_mode=None, speakers=None):
    payload = {
        "upload_id": analysis["upload_id"],
        "preset_id": analysis["preset_id"],
        "metadata": analysis["metadata"],
        "speakers": speakers if speakers is not None else analysis["speakers"],
        "hospitality": {"mode": hospitality_mode or analysis["hospitality_mode"]},
        "activity_mapping_id": analysis["mapping_ids"]["activity"],
        "speaker_mapping_id": analysis["mapping_ids"]["speaker"],
        "make_pdf": make_pdf,
    }
    response = client.post("/api/generate", json=payload)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def download(client, run_id: str, name: str) -> bytes:
    response = client.get(f"/download/{run_id}/{name}")
    assert response.status_code == 200
    return response.data


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\u00a0", " ")).strip()


def body_skeleton(path: Path):
    """Paragraph/table sequence, with only whitespace normalised."""
    doc = Document(str(path))
    items = []
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            from docx.text.paragraph import Paragraph

            text = norm(Paragraph(child, doc).text)
            if text:
                items.append(("p", text))
        elif child.tag == qn("w:tbl"):
            from docx.table import Table

            table = Table(child, doc)
            rows = []
            for row in table.rows:
                rows.append(tuple(norm(cell.text) for cell in row.cells))
            items.append(("table", tuple(rows)))
    return items


def table_rows(path: Path, index: int):
    doc = Document(str(path))
    return [[norm(cell.text) for cell in row.cells] for row in doc.tables[index].rows]


def assert_no_tags(path: Path):
    doc = Document(str(path))
    texts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                texts.extend(p.text for p in cell.paragraphs)
    assert not any("{{" in t or "{%" in t for t in texts), "unrendered template tag"


def assert_no_hotel_row(path: Path):
    doc = Document(str(path))
    for table in doc.tables:
        for row in table.rows:
            if row.cells and "hotel accommodation" in norm(row.cells[0].text).lower():
                pytest.fail("hospitality row should have been removed")


# ---------------------------------------------------------------------------
# LEAP: activity + 3 speaker reports
# ---------------------------------------------------------------------------
def test_leap_activity_and_speaker_reports(client):
    analysis = upload(client, "leap_with_speakers.csv")
    assert analysis["detection"]["speaker_count"] == 3
    assert analysis["stats"]["activity"]["n"] == 18
    assert analysis["stats"]["activity"]["overall_display"] == "4.61 (Excellent)"
    assert analysis["hospitality_mode"] == "omit"

    items = analysis["stats"]["activity"]["items"]
    assert items["management.length"]["mean_display"] == "4.56"
    assert items["management.length"]["interpretation"] == "Excellent"
    assert items["management.secretariat"]["n"] == 17
    assert items["management.food"]["n"] == 11
    assert items["management.food"]["mean_display"] == "4.64"
    assert items["management.hospitality"]["n"] == 0
    assert analysis["stats"]["activity"]["comments"]["part2"]["count"] == 7
    assert analysis["stats"]["activity"]["comments"]["part3"]["count"] == 0

    speakers = analysis["stats"]["speakers"]
    assert [(s["topic_display"], s["resource_display"], s["n"]) for s in speakers] == [
        ("2.76 (Excellent)", "4.62 (Strongly Agree)", 19),
        ("2.79 (Excellent)", "4.63 (Strongly Agree)", 19),
        ("2.93 (Excellent)", "4.82 (Strongly Agree)", 19),
    ]
    assert [s["comments"]["q1"]["count"] for s in speakers] == [13, 13, 13]
    assert [s["comments"]["q2"]["count"] for s in speakers] == [3, 4, 2]
    assert [s["comments"]["q3"]["count"] for s in speakers] == [8, 5, 4]
    # The sample repeated Q2 answers in Speaker 2 Q3; our Q3 is the CSV's Q3.
    assert speakers[1]["comments"]["q3"]["comments"][0] == "School shooting"

    manifest = generate(client, analysis)
    assert len(manifest["files"]) == 4
    assert [f["kind"] for f in manifest["files"]].count("speaker") == 3
    assert manifest["zip"].endswith(".zip")
    assert manifest["n"] == 18

    run_dir = service.HISTORY_DIR / manifest["id"]
    activity_name = next(f["name"] for f in manifest["files"] if f["kind"] == "activity")
    speaker_names = [f["name"] for f in manifest["files"] if f["kind"] == "speaker"]
    activity_path = run_dir / activity_name

    assert_no_tags(activity_path)
    assert_no_hotel_row(activity_path)

    # The Activity Report must not absorb speaker content.
    activity_text = "\n".join(p.text for p in Document(str(activity_path)).paragraphs)
    assert "CATHERINE" not in activity_text
    assert "SPEAKER/TOPIC" not in activity_text

    # Metadata, summary, criteria values.
    meta_rows = table_rows(activity_path, 0)
    assert meta_rows[0][1] == "LEAP Capability Training"
    assert meta_rows[1][1] == "September 30, 8:00 AM to 5:00 PM"
    assert meta_rows[2][1] == "Acad II, PSHS-SRC in Koronadal City, South Cotabato"
    assert meta_rows[3][1] == "CID"
    summary = table_rows(activity_path, 1)
    assert summary[0][1] == "4.61 (Excellent)"
    assert summary[1][1] == "18"
    criteria = table_rows(activity_path, 2)
    assert len(criteria) == 16  # 17-row source minus the absent hospitality row
    by_label = {row[0]: row for row in criteria}
    assert by_label["Length of the program"][1] == "4.56"
    assert by_label["Length of the program"][2] == "Excellent"
    assert by_label["Food/ meals served"][1] == "4.64"
    assert by_label["Secretariat & support staff, if any"][1] == "4.71"

    # Signature names are restored through the template tags.
    paragraphs = [norm(p.text) for p in Document(str(activity_path)).paragraphs]
    assert any("ADRIAN ERLE B. VEGA" in p and "MARJUN I. BALQUIN" in p for p in paragraphs)
    assert "MARJUN I. BALQUIN" in paragraphs
    assert "LEAP Coordinator" in paragraphs

    # Speaker 1 is structurally identical to the supplied reference report.
    speaker1_path = run_dir / speaker_names[0]
    assert_no_tags(speaker1_path)
    assert body_skeleton(speaker1_path) == body_skeleton(SOURCES / "speaker_report_sample.docx")

    # Speaker 2 uses its own Q3 answers, not the sample's duplicated Q2 block.
    speaker2_path = run_dir / speaker_names[1]
    speaker2_text = "\n".join(p.text for p in Document(str(speaker2_path)).paragraphs)
    assert "School shooting" in speaker2_text
    assert "I think all topic is covered" in speaker2_text
    assert "Since the presentation was through a video" not in speaker2_text.split("3. What other topic", 1)[1]

    # Page geometry/header/footer are inherited from the source template.
    src = Document(str(SOURCES / "activity_report_sample.docx"))
    out = Document(str(activity_path))
    assert len(out.sections) == len(src.sections) == 1
    assert out.sections[0].page_width == src.sections[0].page_width
    assert out.sections[0].page_height == src.sections[0].page_height
    assert out.sections[0].left_margin == src.sections[0].left_margin
    assert out.sections[0].top_margin == src.sections[0].top_margin
    assert norm(out.sections[0].header.paragraphs[-1].text) == norm(src.sections[0].header.paragraphs[-1].text)
    assert len(out.tables[2].columns) == 3
    assert [c.width for c in out.tables[2].columns] == [c.width for c in src.tables[2].columns]


# ---------------------------------------------------------------------------
# GFPS: activity only, hospitality kept as N/A
# ---------------------------------------------------------------------------
def test_gfps_activity_only_and_hospitality_na(client):
    analysis = upload(client, "gfps_no_speakers.csv")
    assert analysis["detection"]["speaker_count"] == 0
    assert analysis["stats"]["speakers"] == []
    activity = analysis["stats"]["activity"]
    assert activity["n"] == 11
    assert activity["overall_display"] == "5.00 (Excellent)"
    assert activity["items"]["content.audio_visual"]["mean_display"] == "4.73"
    assert activity["items"]["management.length"]["mean_display"] == "4.91"
    assert activity["items"]["management.schedule"]["mean_display"] == "4.82"
    assert activity["items"]["management.food"]["mean_display"] == "4.91"
    assert activity["items"]["management.hospitality"]["mean_display"] == "5.00"
    assert activity["hospitality"] == {
        "has_question": True,
        "include": True,
        "mode": "na",
        "mean": None,
        "mean_display": "N/A",
        "interpretation": "N/A",
        "n": 8,
    }
    assert activity["comments"]["part2"]["count"] == 4
    assert activity["comments"]["part3"]["count"] == 2

    manifest = generate(client, analysis)
    assert len(manifest["files"]) == 1
    assert manifest["files"][0]["kind"] == "activity"
    run_dir = service.HISTORY_DIR / manifest["id"]
    path = run_dir / manifest["files"][0]["name"]
    assert_no_tags(path)

    criteria = table_rows(path, 2)
    assert len(criteria) == 17
    by_label = {row[0]: row for row in criteria}
    assert by_label["Hotel accommodation/ lodging"][1:] == ["N/A", "N/A"]
    assert by_label["Audio/Visuals reinforced program content"][1] == "4.73"
    assert by_label["Length of the program"][1] == "4.91"
    assert by_label["Schedule of activities"][1] == "4.82"
    assert table_rows(path, 1)[0][1] == "5.00 (Excellent)"
    assert table_rows(path, 1)[1][1] == "11"

    comments_text = "\n".join(p.text for p in Document(str(path)).paragraphs)
    assert "None so far" in comments_text
    assert "More of this kind of deepenings sessions..." in comments_text

    # The sample's all-5.00 values were stale; the recomputed values differ, but
    # the structural table geometry remains the template's.
    src = Document(str(SOURCES / "activity_report_gfps_sample.docx"))
    out = Document(str(path))
    assert len(out.tables) == len(src.tables) == 3
    assert len(out.tables[2].rows) == len(src.tables[2].rows) == 17
    assert [c.width for c in out.tables[2].columns] == [c.width for c in src.tables[2].columns]
    assert norm(out.sections[0].footer.paragraphs[0].text) == norm(src.sections[0].footer.paragraphs[0].text)


# ---------------------------------------------------------------------------
# Robustness / configuration
# ---------------------------------------------------------------------------
def test_ragged_rows_and_noise_do_not_crash(client):
    raw = (SAMPLES / "gfps_no_speakers.csv").read_text(encoding="utf-8-sig").splitlines()
    # Add one too-long and one too-short row.
    ragged = raw + [raw[1] + ",EXTRA", raw[1].rsplit(",", 2)[0]]
    response = client.post(
        "/api/analyze",
        data={"file": (io.BytesIO("\n".join(ragged).encode("utf-8")), "ragged.csv")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["csv"]["rows"] == 13
    assert body["warnings"]


def test_hospitality_compute_toggle(client):
    analysis = upload(client, "gfps_no_speakers.csv")
    response = client.post(
        "/api/reanalyze",
        json={
            "upload_id": analysis["upload_id"],
            "preset_id": analysis["preset_id"],
            "hospitality_mode": "compute",
            "activity_mapping_id": analysis["mapping_ids"]["activity"],
            "speaker_mapping_id": analysis["mapping_ids"]["speaker"],
        },
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["hospitality_mode"] == "compute"
    assert body["stats"]["activity"]["hospitality"]["mean_display"] == "5.00"
    assert body["stats"]["activity"]["hospitality"]["include"] is True


def test_prepared_checked_tags_are_filled(client):
    analysis = upload(client, "gfps_no_speakers.csv")
    analysis["metadata"]["prepared_by"] = "TEST PREPARER"
    analysis["metadata"]["checked_by"] = "TEST CHECKER"
    manifest = generate(client, analysis)
    run_dir = service.HISTORY_DIR / manifest["id"]
    path = run_dir / manifest["files"][0]["name"]
    paragraphs = [norm(p.text) for p in Document(str(path)).paragraphs]
    assert any("TEST PREPARER" in p and "TEST CHECKER" in p for p in paragraphs)
    assert not any("ADRIAN ERLE" in p for p in paragraphs)
