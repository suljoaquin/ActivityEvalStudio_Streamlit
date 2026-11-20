from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parent.parent
STREAMLIT_APP = APP / "streamlit_app.py"


def _button(at: AppTest, label: str):
    for button in at.button:
        if button.label == label:
            return button
    raise AssertionError(f"Button not found: {label}. Found: {[b.label for b in at.button]}")


def test_streamlit_landing_loads():
    at = AppTest.from_file(str(STREAMLIT_APP), default_timeout=60).run()
    assert not at.exception
    assert any("Activity Eval Studio" in md.value for md in at.markdown)
    assert any("Upload CSV" in md.value for md in at.markdown)


def test_streamlit_leap_sample_and_generation():
    at = AppTest.from_file(str(STREAMLIT_APP), default_timeout=120).run()
    assert not at.exception

    _button(at, "LEAP · 3 speakers").click().run()
    assert not at.exception
    metrics = {(metric.label, metric.value) for metric in at.metric}
    assert ("Overall satisfaction", "4.61 (Excellent)") in metrics
    assert ("Activity N", "18") in metrics
    assert ("Speaker reports", "3") in metrics
    assert ("Topic/Subject Matter", "2.76 (Excellent)") in metrics

    generate = _button(at, "Generate report package")
    generate.click().run()
    assert not at.exception
    assert any("Package ready" in item.value for item in at.success)
    downloads = [item.label for item in at.get("download_button")]
    assert downloads.count("DOCX") == 4
    assert "Download ZIP package" in downloads


def test_streamlit_gfps_sample():
    at = AppTest.from_file(str(STREAMLIT_APP), default_timeout=120).run()
    assert not at.exception

    _button(at, "GFPS · no speakers").click().run()
    assert not at.exception
    metrics = {(metric.label, metric.value) for metric in at.metric}
    assert ("Overall satisfaction", "5.00 (Excellent)") in metrics
    assert ("Activity N", "11") in metrics
    assert ("Speaker reports", "0") in metrics
    assert any("No speaker question blocks were detected" in item.value for item in at.info)
