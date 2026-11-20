"""Streamlit edition of Activity Eval Studio.

This is the version to deploy on Streamlit Community Cloud (or any Streamlit
host). It reuses the same CSV parser, aggregation engine and Word templates as
the Flask edition, but handles uploads and downloads inside a single page.
"""
from __future__ import annotations

import hashlib
import hmac
import html
import os
import tempfile
from pathlib import Path

# Set the writable home BEFORE importing evalapp.paths. Streamlit Cloud has a
# read-only source tree, so configuration and generated files live in /tmp.
os.environ.setdefault(
    "ACTIVITY_EVAL_HOME",
    str(Path(tempfile.gettempdir()) / "activity-eval-studio"),
)

import pandas as pd
import streamlit as st

from evalapp.paths import HOME_ROOT, HISTORY_DIR, seed_home
from evalapp.service import analyze_bytes, generate_report, save_upload

seed_home()

from evalapp.template_builder import build_templates  # noqa: E402

build_templates()

st.set_page_config(
    page_title="Activity Eval Studio",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

APP_PASSWORD = ""
try:
    _secret = st.secrets.get("APP_PASSWORD", "")
    APP_PASSWORD = str(_secret) if _secret else ""
except Exception:
    APP_PASSWORD = os.environ.get("APP_PASSWORD", "")

CUSTOM_CSS = """
<style>
  .stApp { background: linear-gradient(180deg, #f7f4ed 0%, #f2eee5 100%); }
  .block-container { padding-top: 4.2rem; padding-bottom: 4rem; max-width: 1180px; }
  h1, h2, h3 { color: #17233b; }
  .hero-eyebrow { color: #8a6227; font-size: .72rem; font-weight: 800; letter-spacing: .16em; text-transform: uppercase; }
  .hero-title { font-family: Georgia, "Times New Roman", serif; font-size: clamp(2.3rem, 5vw, 4.1rem); line-height: 1.02; letter-spacing: -.03em; color: #17233b; margin: .5rem 0 .8rem; max-width: 16ch; }
  .hero-title em { color: #216b63; }
  .hero-lede { color: #3d4a63; font-size: 1.02rem; line-height: 1.65; max-width: 65ch; }
  .brand { font-size: 1.1rem; font-weight: 800; color: #17233b; letter-spacing: -.02em; }
  .brand-sub { font-size: .64rem; letter-spacing: .14em; text-transform: uppercase; color: #67718a; }
  .soft-card { background: #fffdf8; border: 1px solid #ded7c9; border-radius: 16px; padding: 18px 20px; box-shadow: 0 8px 22px rgba(23,35,59,.05); }
  .soft-card h4 { margin: 0 0 4px; color: #17233b; font-size: .95rem; }
  .soft-card p { margin: 0; color: #67718a; font-size: .82rem; line-height: 1.5; }
  .status-ok { color: #216b63; font-size: .8rem; }
  .status-warn { color: #9a671d; font-size: .8rem; }
  .status-err { color: #a23c34; font-size: .8rem; }
  .small-note { color: #67718a; font-size: .78rem; }
  .comment-line { display: grid; grid-template-columns: 2.1rem 1fr; gap: .25rem; padding: .35rem 0; border-bottom: 1px solid #eee8dc; white-space: pre-wrap; color: #17233b; font-size: .9rem; line-height: 1.5; }
  .comment-line:last-child { border-bottom: 0; }
  .comment-num { color: #8a6227; font-weight: 700; font-variant-numeric: tabular-nums; }
  div[data-testid="stSidebar"] { background: #fffdf8; border-right: 1px solid #ded7c9; }
  .stButton > button[kind="primary"] { background: #17233b; border-color: #17233b; }
  .stButton > button[kind="primary"]:hover { background: #223252; border-color: #223252; }
  .stDownloadButton > button { border-color: #b1843c; }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def _password_gate() -> None:
    if not APP_PASSWORD or st.session_state.get("authenticated"):
        return
    st.markdown(
        '<div class="hero-eyebrow">Activity Evaluation &amp; Customer Satisfaction Committee</div>'
        '<div class="hero-title">Activity Eval <em>Studio</em>.</div>',
        unsafe_allow_html=True,
    )
    st.caption("This report generator is password-protected.")
    password = st.text_input("Password", type="password")
    if st.button("Enter", type="primary"):
        if hmac.compare_digest(password, APP_PASSWORD):
            st.session_state.authenticated = True
            st.rerun()
        st.error("Incorrect password.")
    st.stop()


_password_gate()


def _sample(name: str) -> dict:
    spec = {
        "leap": {
            "path": HOME_ROOT / "samples" / "leap_with_speakers.csv",
            "filename": "2026_09_30 LeAP Capability Training (Responses).csv",
            "preset": "leap_2026_09_30",
            "label": "LEAP · 3 speakers",
        },
        "gfps": {
            "path": HOME_ROOT / "samples" / "gfps_no_speakers.csv",
            "filename": "2026_10_28-29 PSHS-SRC GFPS Deepening Session (Responses).csv",
            "preset": "gfps_2026_10_28",
            "label": "GFPS · no speakers",
        },
    }[name]
    spec["bytes"] = spec["path"].read_bytes()
    return spec


@st.cache_data(show_spinner=False)
def _analyze(data: bytes, filename: str, preset_id: str | None, hospitality_mode: str | None):
    return analyze_bytes(
        data,
        filename,
        preset_id=preset_id,
        hospitality_mode=hospitality_mode,
    )


def _init_form(analysis: dict, analysis_key: str) -> None:
    if st.session_state.get("analysis_key") == analysis_key:
        return
    st.session_state["analysis_key"] = analysis_key
    st.session_state["package"] = None
    for key, value in analysis["metadata"].items():
        st.session_state[f"meta_{key}"] = value
    for index, speaker in enumerate(analysis["speakers"]):
        st.session_state[f"speaker_name_{index}"] = speaker.get("name", "")
        st.session_state[f"speaker_topic_{index}"] = speaker.get("topic", "")
    st.session_state["meta_prepared_by"] = analysis["metadata"].get("prepared_by", "")
    st.session_state["meta_checked_by"] = analysis["metadata"].get("checked_by", "")


def _meta_value(key: str) -> str:
    return str(st.session_state.get(f"meta_{key}", "")).strip()


def _speaker_values(count: int) -> list[dict]:
    return [
        {
            "name": str(st.session_state.get(f"speaker_name_{index}", "")).strip(),
            "topic": str(st.session_state.get(f"speaker_topic_{index}", "")).strip(),
        }
        for index in range(count)
    ]


def _badge(text: str, kind: str = "ok") -> str:
    symbol = {"ok": "✓", "warn": "!", "err": "×"}.get(kind, "•")
    return f'<div class="status-{kind}">{symbol} {html.escape(text)}</div>'


def _activity_rows(analysis: dict, mode: str) -> pd.DataFrame:
    rows = []
    for spec in analysis["mappings"]["activity"].get("items", []):
        item = analysis["stats"]["activity"]["items"].get(spec["key"])
        if not item:
            continue
        if spec["key"] == "management.hospitality" and mode == "omit":
            continue
        mean = item["mean_display"]
        label = item["interpretation"]
        if spec["key"] == "management.hospitality" and mode != "compute":
            mean, label = "N/A", "N/A"
        rows.append(
            {
                "Criterion": item["label"],
                "n": item["n"],
                "Mean": mean,
                "Rating": label,
            }
        )
    return pd.DataFrame(rows)


def _speaker_table(speaker: dict, mapping: dict, section: str) -> pd.DataFrame:
    rows = []
    for spec in mapping.get(f"{section}_items", []):
        item = speaker.get(f"{section}_items", {}).get(spec["key"])
        if not item:
            continue
        rows.append(
            {
                "Item": item["label"],
                "n": item["n"],
                "Mean": item["mean_display"],
                "Rating": item["interpretation"],
            }
        )
    return pd.DataFrame(rows)


def _show_comments(comments: dict, key: str, empty_text: str) -> None:
    data = comments.get(key) or {}
    items = data.get("comments", [])
    if not items:
        st.info(empty_text)
        return
    for index, comment in enumerate(items, start=1):
        st.markdown(
            f'<div class="comment-line"><span class="comment-num">{index}.</span>'
            f'<span>{html.escape(comment)}</span></div>',
            unsafe_allow_html=True,
        )


def _landing() -> None:
    st.markdown(
        '<div class="hero-eyebrow">Evaluation reports, without the retyping</div>'
        '<div class="hero-title">Turn form responses into <em>committee-ready</em> reports.</div>'
        '<div class="hero-lede">Upload a Google Forms CSV. The studio detects the activity and speaker sections, '
        'recomputes every mean, N and comment, then fills the committee\'s own Word templates — headers, logos, '
        'tables and all.</div>',
        unsafe_allow_html=True,
    )
    st.write("")
    cols = st.columns(3)
    with cols[0]:
        st.markdown('<div class="soft-card"><h4>1 · Upload</h4><p>Drop the Google Forms CSV. One activity at a time.</p></div>', unsafe_allow_html=True)
    with cols[1]:
        st.markdown('<div class="soft-card"><h4>2 · Verify</h4><p>Check detected speakers, N, sections and statistics before generating.</p></div>', unsafe_allow_html=True)
    with cols[2]:
        st.markdown('<div class="soft-card"><h4>3 · Download</h4><p>Get the Activity Report plus one Speaker Report per resource person.</p></div>', unsafe_allow_html=True)
    st.write("")
    st.caption("No CSV is sent anywhere except this Streamlit server. Generated files are available only in your current session.")


# ----------------------------- sidebar -------------------------------------
with st.sidebar:
    st.markdown('<div class="brand">AE. Activity Eval Studio</div><div class="brand-sub">PSHS-SRC · Committee Reports</div>', unsafe_allow_html=True)
    st.divider()
    if "uploader_key" not in st.session_state:
        st.session_state["uploader_key"] = 0
    st.markdown("**Upload CSV**")
    uploaded = st.file_uploader(
        "Upload the Google Forms CSV",
        type=["csv"],
        key=f"uploader_{st.session_state['uploader_key']}",
        label_visibility="collapsed",
        help="Export the form responses as CSV. The app reads consent, activity items and repeated speaker blocks.",
    )
    st.markdown("**Try a sample**")
    sample_clicked = None
    if st.button("LEAP · 3 speakers", width="stretch"):
        sample_clicked = "leap"
    if st.button("GFPS · no speakers", width="stretch"):
        sample_clicked = "gfps"

    if sample_clicked:
        spec = _sample(sample_clicked)
        st.session_state["demo"] = {
            "bytes": spec["bytes"],
            "filename": spec["filename"],
            "preset": spec["preset"],
        }
        st.session_state["uploader_key"] = st.session_state.get("uploader_key", 0) + 1
        st.session_state["analysis_key"] = None
        st.session_state["package"] = None
        st.rerun()

    st.divider()
    st.markdown("**How it works**")
    st.caption(
        "The Word templates are the source of truth. The app fills them in place; it does not rebuild the layout. "
        "Headers, footers, logos, table widths and page settings are inherited."
    )
    st.divider()
    st.caption("Activity Evaluation & Customer Satisfaction Committee")
    st.caption("Philippine Science High School — SOCCSKSARGEN Region Campus")

# ----------------------------- upload selection ----------------------------
if uploaded is not None:
    if st.session_state.get("demo"):
        st.session_state["demo"] = None
    data = uploaded.getvalue()
    filename = uploaded.name
    preset_id = None
elif st.session_state.get("demo"):
    demo = st.session_state["demo"]
    data = demo["bytes"]
    filename = demo["filename"]
    preset_id = demo["preset"]
else:
    _landing()
    st.stop()

# ----------------------------- analysis ------------------------------------
analysis_key = hashlib.sha256(data).hexdigest()[:16] + "|" + filename
try:
    base_analysis = _analyze(data, filename, preset_id, None)
except Exception as exc:
    st.error(f"Could not read that CSV: {exc}")
    st.stop()

_init_form(base_analysis, analysis_key)

st.markdown(
    '<div class="hero-eyebrow">Current activity</div>'
    f'<div style="font-family:Georgia,serif;font-size:2rem;letter-spacing:-.02em;color:#17233b;margin:2px 0">{html.escape(base_analysis["metadata"]["title"] or "Activity")}</div>',
    unsafe_allow_html=True,
)
st.caption(f"{filename} · {base_analysis['csv']['rows']} responses · {base_analysis['csv']['columns']} columns")

# Show / choose hospitality before the main statistics.
has_hospitality = base_analysis["detection"]["hospitality_column"] is not None
if has_hospitality:
    labels = ["N/A · keep row", "Compute from responses", "Remove row"]
    current = st.session_state.get(f"hosp_{analysis_key}")
    default_label = {
        "na": labels[0],
        "compute": labels[1],
        "omit": labels[2],
    }.get(current or base_analysis["hospitality_mode"], labels[0])
    choice = st.radio(
        "Hospitality / venue row",
        labels,
        index=labels.index(default_label),
        horizontal=True,
        key=f"hosp_{analysis_key}",
        help="Hotel accommodation is optional. Keep it as N/A for a non-residential activity, compute it, or remove the row.",
    )
    mode = {"N/A · keep row": "na", "Compute from responses": "compute", "Remove row": "omit"}[choice]
else:
    mode = "omit"
    st.caption("No hotel/accommodation question was detected; the optional hospitality row will be removed.")

if mode != base_analysis["hospitality_mode"]:
    try:
        base_analysis = _analyze(data, filename, preset_id, mode)
    except Exception as exc:
        st.error(f"Could not recompute the CSV: {exc}")
        st.stop()

analysis = base_analysis
activity = analysis["stats"]["activity"]
speakers = analysis["stats"]["speakers"]

# ----------------------------- headline metrics ----------------------------
metrics = st.columns(4)
metrics[0].metric("Overall satisfaction", activity["overall_display"])
metrics[1].metric("Activity N", activity["n"])
metrics[2].metric("Speaker reports", len(speakers))
if not has_hospitality:
    hotel_display = "Removed"
elif mode == "compute":
    hotel_display = f"{activity['hospitality']['mean_display']}"
elif mode == "omit":
    hotel_display = "Removed"
else:
    hotel_display = "N/A"
metrics[3].metric("Hospitality", hotel_display)

# ----------------------------- validation ----------------------------------
with st.container(border=True):
    st.subheader("What the studio found")
    checks = analysis["validation"]["checks"]
    for check in checks:
        if check["status"] == "error":
            st.error(f"{check['label']} — {check['detail']}")
        elif check["status"] == "warn":
            st.warning(f"{check['label']} — {check['detail']}")
        else:
            st.markdown(_badge(f"{check['label']} — {check['detail']}", "ok"), unsafe_allow_html=True)
    if analysis["anomaly_notes"]:
        with st.expander("Known differences from the supplied samples"):
            for note in analysis["anomaly_notes"]:
                st.write(f"- {note}")
    if analysis["warnings"]:
        with st.expander("Parser notes"):
            for warning in analysis["warnings"]:
                st.write(f"- {warning}")

# ----------------------------- metadata ------------------------------------
with st.container(border=True):
    st.subheader("Report details")
    st.caption("Labels and layout stay fixed. These values, the statistics and the comments are filled into the template.")
    c1, c2 = st.columns(2)
    c1.text_input("Training / workshop / activity", key="meta_title")
    c2.text_input("Date", key="meta_date")
    c1.text_input("Proponent", key="meta_proponent")
    c2.text_input("Venue", key="meta_venue")
    c1.text_input("Prepared by", key="meta_prepared_by")
    c2.text_input("Checked by", key="meta_checked_by")
    c1.text_input("Concurring signatory", key="meta_signatory_name")
    c2.text_input("Signatory role", key="meta_signatory_role")

# ----------------------------- speakers ------------------------------------
with st.container(border=True):
    st.subheader("Resource persons")
    if not speakers:
        st.info("No speaker question blocks were detected. Only the Activity Report will be generated.")
    else:
        st.caption("Speaker names and topics are not in the CSV; they are prefilled from the preset and are editable.")
        for index, speaker in enumerate(speakers):
            st.markdown(f"**Speaker {index + 1}** · N = {speaker['n']}")
            c1, c2 = st.columns([1, 1.4])
            c1.text_input("Resource person", key=f"speaker_name_{index}", label_visibility="collapsed", placeholder="Resource person")
            c2.text_area("Topic / subject matter", key=f"speaker_topic_{index}", height=72, label_visibility="collapsed", placeholder="Topic / subject matter")
            st.divider()

# ----------------------------- statistics ---------------------------------
with st.container(border=True):
    st.subheader("Statistics & comments")
    st.caption(f"{activity['n']} respondents contributed at least one valid activity rating. Each item's n excludes blanks and N/A.")
    st.dataframe(
        _activity_rows(analysis, mode),
        hide_index=True,
        width="stretch",
        column_config={
            "n": st.column_config.NumberColumn("n", width="small"),
            "Mean": st.column_config.TextColumn("Mean", width="small"),
            "Rating": st.column_config.TextColumn("Rating", width="medium"),
        },
    )

    tab2, tab3 = st.tabs(
        [
            f"Part II · {activity['comments']['part2']['count']} comments",
            f"Part III · {activity['comments']['part3']['count']} comments",
        ]
    )
    with tab2:
        _show_comments(activity["comments"], "part2", "No comments were provided for Part II.")
    with tab3:
        _show_comments(
            activity["comments"],
            "part3",
            activity.get("part3_sentence", "No comments were provided for Part III."),
        )

    if speakers:
        st.divider()
        st.subheader("Speaker breakdown")
        for index, speaker in enumerate(speakers):
            with st.expander(f"{index + 1}. {speaker['name']} — {speaker['topic'] or 'No topic entered'}"):
                m1, m2, m3 = st.columns(3)
                m1.metric("Topic/Subject Matter", speaker["topic_display"])
                m2.metric("Resource Person", speaker["resource_display"])
                m3.metric("N", speaker["n"])
                st.markdown("**Topic / subject matter**")
                st.dataframe(
                    _speaker_table(speaker, analysis["mappings"]["speaker"], "topic"),
                    hide_index=True,
                    width="stretch",
                )
                st.markdown("**Resource person**")
                st.dataframe(
                    _speaker_table(speaker, analysis["mappings"]["speaker"], "resource"),
                    hide_index=True,
                    width="stretch",
                )
                st.caption(
                    f"Comments: Q1 {speaker['comments']['q1']['count']} · "
                    f"Q2 {speaker['comments']['q2']['count']} · "
                    f"Q3 {speaker['comments']['q3']['count']}"
                )

# ----------------------------- mapping -------------------------------------
with st.expander("Column mapping & template information"):
    st.caption(
        "The app maps CSV headers to semantic report rows using JSON files in config/mappings. "
        "The Word layout is described by config/templates. To adapt a new form or template, edit those files "
        "in the repository and redeploy; no render code changes are needed."
    )
    st.code(
        f"Activity mapping: {analysis['mapping_ids']['activity']}\n"
        f"Speaker mapping: {analysis['mapping_ids']['speaker']}\n"
        f"Preset: {analysis.get('preset_id') or 'Generic / none'}",
        language="text",
    )
    with st.expander("Inspect mapped columns"):
        st.dataframe(
            pd.DataFrame(analysis["csv"]["inventory"]),
            hide_index=True,
            width="stretch",
        )

# ----------------------------- generate ------------------------------------
with st.container(border=True):
    st.subheader("Output package")
    st.caption(f"{1 + len(speakers)} Word report(s) will be generated. PDFs are not available on Streamlit Community Cloud.")
    if st.button("Generate report package", type="primary", width="stretch"):
        missing = []
        if not _meta_value("title"):
            missing.append("activity title")
        for index, speaker in enumerate(speakers):
            if not str(st.session_state.get(f"speaker_name_{index}", "")).strip():
                missing.append(f"speaker {index + 1} name")
        if missing:
            st.error("Please complete: " + ", ".join(missing))
        else:
            with st.spinner("Filling the Word templates…"):
                try:
                    upload = save_upload(data, filename)
                    meta = {
                        "title": _meta_value("title"),
                        "date": _meta_value("date"),
                        "venue": _meta_value("venue"),
                        "proponent": _meta_value("proponent"),
                        "prepared_by": _meta_value("prepared_by"),
                        "checked_by": _meta_value("checked_by"),
                        "signatory_name": _meta_value("signatory_name"),
                        "signatory_role": _meta_value("signatory_role"),
                    }
                    payload = {
                        "upload_id": upload["upload_id"],
                        "preset_id": analysis.get("preset_id") or "__none__",
                        "metadata": meta,
                        "speakers": _speaker_values(len(speakers)),
                        "hospitality": {"mode": mode},
                        "activity_mapping_id": analysis["mapping_ids"]["activity"],
                        "speaker_mapping_id": analysis["mapping_ids"]["speaker"],
                        "make_pdf": False,
                    }
                    manifest = generate_report(upload["upload_id"], payload)
                    run_dir = HISTORY_DIR / manifest["id"]
                    files = []
                    for item in manifest["files"]:
                        files.append(
                            {
                                **item,
                                "bytes": (run_dir / item["name"]).read_bytes(),
                            }
                        )
                    st.session_state["package"] = {
                        "manifest": manifest,
                        "files": files,
                        "zip_bytes": (run_dir / manifest["zip"]).read_bytes(),
                    }
                except Exception as exc:
                    st.error(f"Could not generate the package: {exc}")

package = st.session_state.get("package")
if package:
    st.success(f"Package ready — {len(package['files'])} Word report(s).")
    st.download_button(
        "Download ZIP package",
        data=package["zip_bytes"],
        file_name=package["manifest"]["zip"],
        mime="application/zip",
        type="primary",
        width="stretch",
    )
    st.markdown("**Individual reports**")
    for item in package["files"]:
        c1, c2 = st.columns([4, 1])
        c1.write(f"**{item['label']}**")
        c2.download_button(
            "DOCX",
            data=item["bytes"],
            file_name=item["name"],
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            key=f"download_{item['name']}",
            width="stretch",
        )

st.caption(
    "Reports are generated from the committee's Word templates. "
    "The hosted Streamlit edition produces DOCX files; open them in Word and use Save As → PDF if a PDF is needed."
)
