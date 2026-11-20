# Activity Eval Studio

A local web app that turns Google Forms evaluation CSVs into committee-ready **Microsoft Word** reports using the committee's own `.docx` files as the formatting source of truth.

- **Activity Report** — always generated.
- **Speaker/Topic Evaluation Report** — one per detected speaker/resource person, generated alongside the Activity Report.
- **DOCX first, PDF optional** — PDFs are produced with LibreOffice Kit when requested.

The app is designed for the PSHS-SRC Activity Evaluation & Customer Satisfaction Committee. It runs locally at `http://127.0.0.1:5051`, requires no login, and keeps uploads and generated packages on the machine.

---

## What was built

| Feature | Where |
|---|---|
| CSV upload, parsed preview, drag-and-drop | `web/index.html`, `static/` |
| Structure detection (activity, speaker blocks, hospitality) | `evalapp/detect.py` |
| Reusable JSON column mapping | `config/mappings/` |
| Aggregation (n, mean, labels, frequencies, comments) | `evalapp/aggregate.py` |
| Word-native rendering from the supplied templates | `evalapp/template_builder.py`, `evalapp/render.py` |
| Validation screen & editable metadata/speakers | single-page UI, `/api/analyze`, `/api/reanalyze` |
| DOCX + ZIP + optional PDF downloads | `/api/generate`, `/download/...` |
| History / re-download | `data/history/`, `/api/history` |
| Automated end-to-end tests | `tests/test_end_to_end.py` |

### Demo output from the two supplied CSVs

- `output/demo/LEAP_Capability_Training_Activity_Report.docx`
- `output/demo/LEAP_Capability_Training_Speaker_01_HON_CATHERINE_A_VELASCO-SUPEDA.docx`
- `output/demo/LEAP_Capability_Training_Speaker_02_MS_MAUDE_ANGELA_G_AUJERO_RPh.docx`
- `output/demo/LEAP_Capability_Training_Speaker_03_MR_ARJIE_P_CASTILLON_RMicro.docx`
- `output/demo/PSHS-SRC_GFPS_Deepening_Session_Activity_Report.docx`
- `output/demo/LEAP_Capability_Training_Evaluation_Package.zip`
- `output/demo/PSHS-SRC_GFPS_Deepening_Session_Evaluation_Package.zip`

See [SAMPLE_AUDIT.md](SAMPLE_AUDIT.md) for the exact reconciliation between the generated files and the supplied sample reports.

---

## Quick start

From `activity-eval-app/`:

```powershell
# Easiest: bundled runtime that already has the dependencies
.\run.ps1
```

Or manually:

```powershell
# Use the bundled runtime that already has the dependencies
$py = "C:\Users\fromp\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$env:PYTHONPATH = (Get-Location)
& $py app.py
```

Or, with a normal Python 3.12+ environment:

```powershell
python -m pip install -r requirements.txt
$env:PYTHONPATH = (Get-Location)
python app.py
```

Open **http://127.0.0.1:5051**.

### Try it immediately

- Click **LEAP · 3 speakers** to load the supplied with-speaker CSV.
- Click **GFPS · no speakers** to load the supplied activity-only CSV.
- Click **Generate report package**.

The sample buttons call `/api/demo`; they do not require you to find the CSVs.

---

## Share with coworkers who do not have Python

The repository includes a prebuilt **portable Windows package**:

`dist/ActivityEvalStudio_Windows.zip` (about 20 MB)

Each coworker should:

1. Receive the **whole ZIP** (OneDrive, Teams, email if allowed, or a shared drive).
2. Unzip the entire folder — keep `ActivityEvalStudio.exe` next to `_internal`.
3. Put it somewhere writable, such as `Documents\Activity Eval Studio`.
4. Double-click `ActivityEvalStudio.exe`.
5. Keep the console window open; the browser opens the app automatically.

No Python, pip, Node, or admin rights are needed. Each user's uploads and history are stored per Windows account in `%LOCALAPPDATA%\ActivityEvalStudio`, so the app folder can be read-only.

The package is unsigned, so Windows may show **“Windows protected your PC.”** Choose **More info → Run anyway**, or have IT sign the exe. If an organization blocks unsigned executables, deploy the exe through software distribution or host the Flask app internally.

PDF export uses Microsoft Word if installed (or LibreOffice Kit if present). DOCX generation works regardless. See `README_FIRST.txt` inside the ZIP for the end-user guide.

### Rebuilding the portable package

```powershell
python -m pip install -r requirements-build.txt
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\build_portable.ps1
```

This runs PyInstaller from `ActivityEvalStudio.spec`, copies `README_FIRST.txt` and `SAMPLE_AUDIT.md`, and recreates `dist/ActivityEvalStudio_Windows.zip`.

The frozen build resolves paths differently from the dev build:

- **Read-only app assets** come from the PyInstaller bundle.
- **Writable config, templates, uploads and history** are seeded to `%LOCALAPPDATA%\ActivityEvalStudio` on first run.
- Set `ACTIVITY_EVAL_HOME` to use a different writable folder (useful for a USB/portable profile).
- Delete/rename `%LOCALAPPDATA%\ActivityEvalStudio` to reset to the bundled configuration.

---

## Host as a webpage (Streamlit Cloud)

No Docker required. The hosted edition is [`streamlit_app.py`](streamlit_app.py), using the same parser, aggregation engine and Word templates as the desktop/Flask edition.

**Step-by-step: [STREAMLIT_DEPLOY.md](STREAMLIT_DEPLOY.md).**

Short version:

1. Push this project to a GitHub repository (`.gitignore` already excludes data, output and secrets).
2. Go to <https://share.streamlit.io/>, create a new app, and choose:
   - Repository: your repo
   - Branch: `main`
   - Main file: `streamlit_app.py`
3. Optionally add a secret:
   ```toml
   APP_PASSWORD = "choose-a-strong-password"
   ```
4. Deploy. Share the resulting `https://…streamlit.app` URL.

Streamlit Community Cloud runs the Python engine, so coworkers only need a browser. The hosted edition produces **DOCX + ZIP** downloads. **PDF export is not available on Streamlit Cloud** (no Word/LibreOffice); open the DOCX in Word and use Save As → PDF. Generated files and history are session/container-local, not permanent cloud storage.

GitHub Pages and Netlify are static hosts and cannot run the Python `.docx` engine. Vercel could run a Python function, but file downloads and persistent state are awkward; Streamlit is the cleanest fit for this app.

---

## Why `docxtpl` (and not HTML-to-Word)

The supplied `.docx` files are already finished reports: A4 page size, custom margins, header/footer with logos, table borders, merged cells, section numbering and the committee's fonts. Rebuilding that in HTML would immediately drift.

This project uses **`docxtpl` (python-docx + Jinja)** because:

1. It opens the supplied `.docx` as the base package and writes values into it.
2. Word styles, theme, headers, footers, page-number fields, images, table grid widths, cell merges and borders are inherited — never re-declared.
3. Jinja paragraph loops (`{%p for ... %}` / `{%p endfor %}`) cleanly render a variable number of comments without losing the comment paragraph's run formatting.
4. It runs in the same Python process as the CSV/statistics engine, so there is one runtime and one dependency set.

The templates supplied by the committee are **finished reports**, not blank tag templates. The app therefore ships a small compiler (`evalapp/template_builder.py`) that turns those finished reports into docxtpl templates by replacing only the dynamic values with tags, while leaving every other package part alone. The source files stay in `docx_templates/source/`; the compiled templates are in `docx_templates/compiled/`.

### Conditional sections / rows

- **Comment sections** use `{%p if ... %}` / `{%p for ... %}` blocks. Empty sections disappear together with their heading paragraphs; no orphaned page breaks are created.
- **Hospitality row** is handled at the Word table-row level after rendering. If the form has no hotel/accommodation question (or the user chooses **Remove row**), the entire `<w:tr>` is removed. The row is *not* replaced with an empty paragraph.
- The supplied Activity and Speaker templates use **one Word section each** and no section breaks. The compiler preserves that section's page size, margins, header, footer and page-number fields. If a future template introduces multiple sections, add the optional section anchors to the template profile and verify pagination after the new template is compiled.
- There are **no embedded charts** in the supplied templates; all report figures are table values.

---

## Business rules implemented

### Report set

- Activity Report is generated for every upload.
- Speaker Reports are generated only when speaker question blocks exist.
- The Activity Report for an activity with speakers is the **same report** as for an activity without speakers. Speaker values are not merged into it. The supplied with-speaker and no-speaker Activity reports have identical structure; only the metadata, values and comments differ.
- One Speaker Report is produced per detected block (or per distinct value of a speaker-name column, if the form uses one).

### Detection

- Activity items are found by normalized header patterns in `config/mappings/activity_default.json`.
- Speaker blocks are detected by repeated `Depth of Content` question blocks; the detector slices each block by column position, not by duplicate header name.
- A speaker-name column (`Speaker name`, `Resource person`, etc.) is supported: if present with multiple distinct names, respondents are grouped by that column and one report is produced per name.
- Hospitality is detected by `hotel`, `accommodation`, `lodging`, or `hospitality` in the activity headers.
- Manual overrides are accepted through the advanced `overrides` JSON (`speaker_blocks`, `activity_end`, `hospitality_col`, `consent_col`).

### Statistics

- A blank or `N/A` response is excluded from **that item's n**.
- Each item's mean is computed over its own valid responses.
- The interpretation label uses the legend in the mapping JSON and is applied to the **displayed 2-decimal mean**.
  - Activity: `4.20–5.00 Excellent`, `3.40–4.19 Very Satisfactory`, `2.60–3.39 Satisfactory`, `1.80–2.59 Unsatisfactory`, `1.00–1.79 Very Unsatisfactory`.
  - Speaker topic: `2.33–3.00 Excellent`, `1.68–2.32 Satisfactory`, `1.00–1.67 Low`.
  - Speaker resource person: `4.20–5.00 Strongly Agree`, `3.40–4.19 Agree`, `2.60–3.39 Neutral`, `1.80–2.59 Disagree`, `1.00–1.79 Strongly Disagree`.
- Activity **Overall Satisfaction** is the mean of the two Overall Evaluation item means. The speaker **Topic/Subject Matter** and **Resource Person** overall scores are the mean of the displayed item means, matching the committee's sample calculation (using Decimal arithmetic at `.005` boundaries).
- **N respondents**: the Activity Report counts consenting responses with at least one valid activity rating. A Speaker Report counts consenting responses with at least one valid rating in that speaker's block. This is why the LEAP sample correctly has N=18 on the Activity Report and N=19 on each Speaker Report: one respondent skipped every activity item but answered every topic item.
- **Comments**: verbatim, blanks and exact noise values (`N/A`, `none`, `.`, `-`, etc.) are filtered; repeated substantive answers such as `Yes` are preserved. Numbering is added in CSV order. Multi-line comments keep their line breaks and only the first line receives the number.
- **Hospitality**: default is N/A for a non-residential activity, with an **Applicable** toggle to compute the mean. If the form has no hospitality question, the row is removed. The GFPS preset keeps N/A because the sample does.

### Signature block

`Prepared by`, `Checked by`, `Concurring signatory` and signatory role are editable and rendered through tags. The original bold/underline/tab formatting is preserved.

---

## Mapping configuration (no render-code changes)

The app has three configuration layers.

### 1. CSV mapping

`config/mappings/activity_default.json` and `speaker_default.json` map a **semantic key** to one or more normalized header substrings:

```json
{
  "key": "management.length",
  "group": "Management of Training/ Workshop/ Activity",
  "patterns": ["length of the program"]
}
```

Also configurable there:

- `legend` / `topic_legend` / `resource_legend`
- `scale` / `topic_scale` / `resource_scale`
- `comments` and `limits`
- `noise` (exact values filtered from comments)
- `overall_keys`, `overall_method`
- `consent_patterns`, `ignore_patterns`

To adapt a new form:

1. Copy one of the mappings to a new id, e.g. `config/mappings/my_form_2027.json`.
2. Change `id`, `name`, and the `patterns` that differ.
3. Select it in the UI (or save it through the **Column mapping → Save as…** editor).
4. No Python change is required.

The UI exposes the current mapping as editable JSON and can save a new mapping to `config/mappings/`. The mapping table in the UI shows each CSV column and its semantic target.

### 2. Template profile

`config/templates/activity_report.json` and `speaker_report.json` describe **where** each semantic value lives in the `.docx`:

- source and compiled paths
- table anchor text
- metadata row order
- summary cell coordinates
- criteria/topic/resource row → semantic key maps
- comment heading prefixes
- signature name/role anchors

To swap a template:

1. Put the new finished `.docx` in `docx_templates/source/` (or anywhere and update the path).
2. Edit the matching template profile JSON so its table anchors and row maps point at the new layout.
3. Run:

   ```powershell
   $env:PYTHONPATH = (Get-Location)
   & $py -m evalapp.template_builder --force
   ```

4. Upload a sample CSV and generate. No changes to `evalapp/render.py` are needed.

The compiler will refuse to run if a required anchor is missing, rather than silently producing a blank report.

### 3. Activity preset

`config/presets/*.json` packages metadata, speaker names/topics, hospitality default and known sample notes:

```json
{
  "id": "leap_2026_09_30",
  "match": { "filename_contains": ["leap"], "speaker_count": 3 },
  "metadata": { "title": "...", "date": "...", "...": "..." },
  "speakers": [{ "name": "...", "topic": "..." }],
  "hospitality": { "mode": "na" }
}
```

Presets fill the validation screen automatically based on the upload file name and speaker count. Everything is editable in the UI before generation. The UI also lets you choose **Generic · no preset**.

Speaker names and topics are not present in the Google Forms CSV, so they necessarily come from the preset or the editable speaker cards.

---

## Running the tests

```powershell
$env:PYTHONPATH = (Get-Location)
& $py -m pytest tests -q
```

The end-to-end suite:

- uploads both supplied CSVs through the Flask API,
- asserts detection, N values, means, labels, comment counts and the corrected Speaker 2 Q3,
- generates the full package,
- reopens every `.docx` with `python-docx`,
- asserts there are no unrendered tags,
- asserts the hospitality row is removed only when no question exists,
- compares Speaker 1's full paragraph/table sequence with the supplied reference `1. SpeakerEval_LEAP.docx`,
- checks page size, margins, header/footer, table geometry, and signature tags,
- exercises ragged rows, the hospitality compute toggle, and prepared/checked overrides.

Expected result:

```text
8 passed
```

The tests do not require Word or LibreOffice. PDF export is exercised separately through the UI/API when Word/LibreOffice is available. Three additional tests load the Streamlit edition through `AppTest`, click the two sample buttons, generate a package, and assert the download buttons appear.

---

## PDF export

The **Also export PDFs** toggle calls LibreOffice Kit via the bundled CLI:

```text
<node> <libreoffice-kit-cli> convert --input <docx> --output <pdf>
```

PDFs are optional and best-effort. If the sidecar is unavailable, DOCX generation still succeeds and the UI reports the PDF failure as a warning.

LibreOffice pagination can differ slightly from Microsoft Word; the `.docx` is the source of truth.

---

## API summary

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/health` | Health check |
| `GET` | `/api/bootstrap` | Presets, mappings, recent history |
| `POST` | `/api/analyze` | Multipart CSV upload; returns detection, stats, validation |
| `POST` | `/api/demo` | Load `leap` or `gfps` sample |
| `POST` | `/api/reanalyze` | Re-run aggregation after a preset/hospitality change |
| `POST` | `/api/generate` | Generate DOCX/ZIP; optional PDFs |
| `GET` | `/api/history` | List generated packages |
| `POST` | `/api/history/<id>/pdf` | Create PDFs for an existing package |
| `GET` | `/download/<id>/<file>` | Download one file |
| `POST` | `/api/mappings` | Save a mapping JSON |
| `POST` | `/api/presets` | Save a preset JSON |

All error responses are `{ "error": "readable message" }` with a 4xx/5xx status. Malformed CSV rows produce warnings, not crashes.

---

## File map

```text
activity-eval-app/
├─ app.py                          Flask entry point (dev / server)
├─ wsgi.py                         Gunicorn entry point
├─ streamlit_app.py                hosted Streamlit edition
├─ desktop.py                      packaged-app launcher (server + browser)
├─ ActivityEvalStudio.spec         PyInstaller build definition
├─ build_portable.ps1              builds dist/ActivityEvalStudio_Windows.zip
├─ README_FIRST.txt                end-user guide inside the portable ZIP
├─ STREAMLIT_DEPLOY.md             GitHub + Streamlit Cloud deployment guide
├─ .streamlit/config.toml          Streamlit theme / upload settings
├─ evalapp/
│  ├─ csvio.py                     tolerant CSV reader (BOM, ragged rows, duplicates)
│  ├─ detect.py                    activity/speaker/hospitality detection
│  ├─ aggregate.py                 n, means, labels, frequencies, comments
│  ├─ template_builder.py          finished .docx -> docxtpl template compiler
│  ├─ render.py                    per-report render + optional row removal
│  ├─ service.py                   uploads, analysis, generation, history
│  ├─ config.py                    mapping/preset loading and saving
│  ├─ normalization.py             header normalization, Decimal rounding, labels
│  ├─ pdf.py                       LibreOffice Kit / Microsoft Word PDF export
│  └─ paths.py                     dev/frozen path resolution and home seeding
├─ config/
│  ├─ mappings/                    reusable CSV→semantic mappings
│  ├─ templates/                   docx anchor/row profiles
│  └─ presets/                     LEAP and GFPS metadata/speakers
├─ docx_templates/
│  ├─ source/                      the supplied finished reports
│  └─ compiled/                    generated docxtpl templates
├─ web/index.html                  single-page UI
├─ static/                         CSS + JS
├─ samples/                        the two supplied CSVs
├─ tests/test_end_to_end.py
├─ tests/test_streamlit_app.py
├─ tools/build_web_bundle.py       builds the GitHub/Streamlit source ZIP
├─ tools/                          read-only docx inspection helpers
├─ dist/                           portable Windows ZIP + Streamlit source ZIP
└─ README.md / SAMPLE_AUDIT.md / STREAMLIT_DEPLOY.md
```

---

## Known limits / next steps

- **Single upload** is implemented; batch upload is a future extension. The API already isolates each upload by id, so the UI can be extended without changing the generator.
- **Speaker names/topics** must be entered or preset; they are not in the Google Forms export.
- **Charts**: the supplied templates have no embedded charts. If a new template adds one, update the chart data through `python-docx`/OOXML after rendering; the current compiler does not rewrite chart parts.
- **Multi-section templates**: the supplied templates use one section. A future template with multiple headers/orientations needs section-aware optional blocks; add them to the template profile and verify pagination.
- **Word repair prompts**: the renderer preserves the original package and emits valid OOXML. All five demo reports were opened in Microsoft Word 16 via COM without a repair prompt, and the test suite reopens every report. If a custom template is edited outside this compiler, validate it in Word/LibreOffice first.
- This is a local committee tool, not a multi-tenant web service; there is no authentication or remote storage.
