# Deploy Activity Eval Studio as a webpage

The hosted edition is **`streamlit_app.py`**. It uses the same CSV parser, aggregation engine and Word templates as the desktop/Flask app, but presents the workflow as a single Streamlit page with in-browser upload and download.

This is the recommended route for **GitHub + Streamlit Community Cloud** — no Docker, no server administration, no Python installation for your coworkers.

A clean, GitHub-ready source bundle is also included:

```text
dist/ActivityEvalStudio_Streamlit.zip
```

Unzip it, then push/upload the contents to GitHub. It includes `streamlit_app.py`, the `.streamlit/` theme, configs, templates and requirements. It excludes local data, generated reports and secrets.

> GitHub Pages and Netlify are static hosts: they cannot run the Python `.docx` templating engine. Vercel can run Python serverless functions, but file-generation/downloads and persistent history are awkward there. Streamlit Cloud is the cleanest fit for this app.

---

## 1. Put the project on GitHub

From `activity-eval-app/`:

```powershell
git init
git add .
git commit -m "Activity Eval Studio — Streamlit edition"
git branch -M main
git remote add origin https://github.com/YOUR-ACCOUNT/activity-eval-studio.git
git push -u origin main
```

Do **not** commit:

- `.streamlit/secrets.toml`
- `data/`
- `output/`
- `dist/`
- `test-home*/`
- `__pycache__/`

The included `.gitignore` covers these.

If you prefer the GitHub website, create a new repository and upload the project files. Keep the hidden `.streamlit/` folder — it contains the theme and upload-size settings.

---

## 2. Deploy on Streamlit Community Cloud

1. Go to <https://share.streamlit.io/> and sign in with GitHub.
2. Choose **Create app** / **New app**.
3. Select:
   - **Repository:** your `activity-eval-studio` repo
   - **Branch:** `main`
   - **Main file path:** `streamlit_app.py`
4. Open **Advanced settings**:
   - **Python version:** 3.12
   - **Secrets** (recommended):
     ```toml
     APP_PASSWORD = "choose-a-strong-password"
     ```
5. Click **Deploy**.

The first build installs `requirements.txt`, seeds the templates into `/tmp`, and compiles the docxtpl templates. It usually takes a minute or two.

You will get a URL like:

```text
https://your-app-name.streamlit.app
```

Share that URL and the password with your coworkers. They only need a browser.

---

## 3. Password / privacy

- If `APP_PASSWORD` is set, the page shows a password screen before any content.
- If it is not set, **anyone with the URL can use the app**.
- Streamlit Cloud also has its own app-sharing controls (workspace members, email restriction, etc.) depending on your plan.
- The CSV is uploaded to and processed on Streamlit's servers, not on the coworker's machine. Do not upload highly sensitive data to a public app; use the password gate, private app sharing, or host it on a school server if that is a concern.

---

## 4. What works on Streamlit Cloud

| Feature | Hosted Streamlit edition |
|---|---|
| CSV upload / parsing | Yes |
| Activity + speaker detection | Yes |
| Metadata and speaker editing | Yes |
| Statistics and comments preview | Yes |
| Activity Report DOCX | Yes |
| Speaker Reports DOCX | Yes |
| ZIP download | Yes |
| PDF export | **No** on Streamlit Community Cloud (no Word/LibreOffice). Generate DOCX and use Word → Save As → PDF. |
| Persistent history across app restarts | No. Generated files live in the Streamlit session/container only. |
| Template/mapping edits | Edit the JSON/`.docx` files in GitHub and redeploy. |

The app intentionally keeps the hosted edition simple: every visit is a fresh report-generation session. That avoids storing participant data longer than needed.

---

## 5. Updating the app

Push changes to `main`:

```powershell
git add .
git commit -m "Update templates"
git push
```

Streamlit Cloud redeploys automatically.

If you change a `.docx` template or a `config/templates/*.json` profile, the app recompiles the docxtpl templates on the next start.

If you change a mapping/preset, it is seeded into the container's `/tmp` on startup. A redeploy starts a fresh container, so the new files are used.

---

## 6. Optional: run the Streamlit edition locally

```powershell
python -m pip install -r requirements.txt
python -m streamlit run streamlit_app.py
```

Then open the URL Streamlit prints, usually <http://localhost:8501>.

For a local password, copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and change the password.

---

## 7. Troubleshooting

**App won't start / build error**
- Check the Streamlit Cloud build logs.
- Confirm `streamlit_app.py` is at the repository root.
- Confirm `requirements.txt` is committed.
- Confirm `docx_templates/`, `config/` and `samples/` are committed.

**"ModuleNotFoundError: evalapp"**
- Run Streamlit from the project root, or ensure the repo root is the working directory. `streamlit_app.py` imports the local `evalapp` package.

**Password screen won't accept the password**
- Check the exact `APP_PASSWORD` value in Streamlit Cloud → App → Settings → Secrets.
- Reboot the app after changing secrets.

**PDF button is missing**
- Expected. Streamlit Community Cloud does not include Microsoft Word or LibreOffice. The hosted edition produces DOCX; use Word's Save As → PDF.

**App sleeps**
- Free Streamlit apps sleep after inactivity. The first visit wakes it; wait a few seconds.
