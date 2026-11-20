"""Flask entry point for the Activity Evaluation Report Generator."""
from __future__ import annotations

import hmac
import json
import os
import traceback

from flask import Flask, Response, jsonify, render_template, request, send_file

from evalapp.config import ConfigError
from evalapp.csvio import CSVError
from evalapp.paths import STATIC_DIR, WEB_DIR, seed_home
from evalapp.service import (
    AppError,
    analyze_demo,
    analyze_upload,
    bootstrap,
    generate_report,
    get_run,
    list_history,
    persist_mapping,
    persist_preset,
    retry_pdfs,
    run_file_path,
    save_upload,
)
from evalapp.template_builder import build_templates

seed_home()
app = Flask(__name__, template_folder=str(WEB_DIR), static_folder=str(STATIC_DIR))
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
app.config["JSON_SORT_KEYS"] = False

build_templates()

APP_USER = os.environ.get("APP_USER", "committee")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")


@app.before_request
def require_password():
    """Optional HTTP Basic auth for public deployments."""
    if not APP_PASSWORD or request.path == "/api/health":
        return None
    auth = request.authorization
    if (
        auth
        and hmac.compare_digest(auth.username or "", APP_USER)
        and hmac.compare_digest(auth.password or "", APP_PASSWORD)
    ):
        return None
    return Response(
        "Authentication required.\n",
        401,
        {"WWW-Authenticate": 'Basic realm="Activity Eval Studio", charset="UTF-8"'},
    )


def error_response(message: str, status: int = 400, **extra):
    payload = {"error": message}
    payload.update(extra)
    return jsonify(payload), status


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "service": "activity-eval", "version": "1.0.0"})


@app.get("/api/bootstrap")
def api_bootstrap():
    return jsonify(bootstrap())


@app.post("/api/analyze")
def api_analyze():
    if "file" not in request.files:
        return error_response("Choose a CSV file to upload.")
    file = request.files["file"]
    if not file.filename:
        return error_response("Choose a CSV file to upload.")
    if not file.filename.lower().endswith(".csv"):
        return error_response("Only .csv files are accepted. Export the Google Form responses as CSV.")
    data = file.read()
    try:
        meta = save_upload(data, file.filename)
        overrides = None
        if request.form.get("overrides"):
            try:
                overrides = json.loads(request.form["overrides"])
            except json.JSONDecodeError:
                return error_response("The advanced override JSON is not valid.")
        result = analyze_upload(
            meta["upload_id"],
            preset_id=request.form.get("preset_id") or None,
            activity_mapping_id=request.form.get("activity_mapping_id") or None,
            speaker_mapping_id=request.form.get("speaker_mapping_id") or None,
            overrides=overrides,
            hospitality_mode=request.form.get("hospitality_mode") or None,
        )
        return jsonify(result)
    except (CSVError, ConfigError, AppError, ValueError) as exc:
        return error_response(str(exc))
    except Exception as exc:
        app.logger.error("analyze failed: %s\n%s", exc, traceback.format_exc())
        return error_response(f"Could not analyse the CSV: {exc}", 500)


@app.post("/api/reanalyze")
def api_reanalyze():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not payload.get("upload_id"):
        return error_response("An upload id is required.")
    try:
        result = analyze_upload(
            payload["upload_id"],
            preset_id=payload.get("preset_id"),
            activity_mapping_id=payload.get("activity_mapping_id"),
            speaker_mapping_id=payload.get("speaker_mapping_id"),
            overrides=payload.get("overrides"),
            hospitality_mode=payload.get("hospitality_mode"),
        )
        return jsonify(result)
    except (CSVError, ConfigError, AppError, ValueError) as exc:
        return error_response(str(exc))


@app.post("/api/demo")
def api_demo():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(analyze_demo(str(payload.get("sample", ""))))
    except (CSVError, ConfigError, AppError, ValueError) as exc:
        return error_response(str(exc))


@app.post("/api/generate")
def api_generate():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error_response("Expected a JSON request body.")
    upload_id = payload.get("upload_id")
    if not upload_id:
        return error_response("Upload a CSV before generating reports.")
    try:
        manifest = generate_report(upload_id, payload)
        return jsonify(manifest)
    except (CSVError, ConfigError, AppError, ValueError) as exc:
        return error_response(str(exc))
    except Exception as exc:
        app.logger.error("generate failed: %s\n%s", exc, traceback.format_exc())
        return error_response(f"Could not generate the reports: {exc}", 500)


@app.get("/api/history")
def api_history():
    return jsonify({"runs": list_history()})


@app.get("/api/history/<run_id>")
def api_run(run_id: str):
    try:
        return jsonify(get_run(run_id))
    except AppError as exc:
        return error_response(str(exc), 404)


@app.post("/api/history/<run_id>/pdf")
def api_run_pdf(run_id: str):
    try:
        return jsonify(retry_pdfs(run_id))
    except AppError as exc:
        return error_response(str(exc), 404)
    except Exception as exc:
        return error_response(f"PDF export failed: {exc}", 500)


@app.get("/download/<run_id>/<path:filename>")
def download(run_id: str, filename: str):
    try:
        path = run_file_path(run_id, filename)
        return send_file(path, as_attachment=True, download_name=filename)
    except AppError as exc:
        return error_response(str(exc), 404)


@app.post("/api/mappings")
def api_save_mapping():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error_response("Expected a JSON object.")
    try:
        saved = persist_mapping(data)
        return jsonify({"ok": True, "mapping": {"id": saved.get("id"), "name": saved.get("name", saved.get("id"))}})
    except (ConfigError, ValueError) as exc:
        return error_response(str(exc))


@app.post("/api/presets")
def api_save_preset():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error_response("Expected a JSON object.")
    try:
        saved = persist_preset(data)
        return jsonify({"ok": True, "preset": {"id": saved.get("id"), "name": saved.get("name", saved.get("id"))}})
    except (ConfigError, ValueError) as exc:
        return error_response(str(exc))


@app.errorhandler(413)
def too_large(_):
    return error_response("The upload is larger than 16 MB.", 413)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5051"))
    host = os.environ.get("HOST", "127.0.0.1")
    app.run(host=host, port=port, debug=False, use_reloader=False)
