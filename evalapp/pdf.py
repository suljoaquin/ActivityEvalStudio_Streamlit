"""PDF export: LibreOffice Kit first, Microsoft Word COM fallback."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .paths import CACHE_DIR

NODE = Path(
    r"C:\Users\fromp\AppData\Local\Programs\DeepSeek Harness\resources\runtime\primary-runtime\dependencies\node\bin\node.exe"
)
CLI = Path(
    r"C:\Users\fromp\AppData\Local\Programs\DeepSeek Harness\resources\app.asar.unpacked\dsh\node_modules\@deepseek-ai\libreoffice-kit\lib\cli.js"
)

_WORD_CANDIDATES = [
    Path(r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE"),
    Path(r"C:\Program Files (x86)\Microsoft Office\root\Office16\WINWORD.EXE"),
    Path(r"C:\Program Files\Microsoft Office\Office16\WINWORD.EXE"),
    Path(r"C:\Program Files (x86)\Microsoft Office\Office16\WINWORD.EXE"),
]


def libreoffice_available() -> bool:
    return NODE.exists() and CLI.exists()


def word_available() -> bool:
    if shutil.which("winword"):
        return True
    return any(path.exists() for path in _WORD_CANDIDATES)


def pdf_available() -> bool:
    return libreoffice_available() or word_available()


def _word_script(input_path: Path, output_path: Path) -> str:
    def quote(path: Path) -> str:
        return "'" + str(path).replace("'", "''") + "'"

    return "\n".join(
        [
            "$ErrorActionPreference = 'Stop'",
            "$word = $null",
            "$doc = $null",
            "try {",
            "  $word = New-Object -ComObject Word.Application",
            "  $word.Visible = $false",
            "  $word.DisplayAlerts = 0",
            f"  $doc = $word.Documents.Open({quote(input_path)}, $false, $true, $false)",
            f"  $doc.ExportAsFixedFormat({quote(output_path)}, 17)",
            "} finally {",
            "  if ($doc) { $doc.Close($false) }",
            "  if ($word) { $word.Quit() }",
            "}",
            "",
        ]
    )


def _convert_with_word(input_path: Path, output_path: Path) -> tuple[bool, str]:
    if not word_available():
        return False, "Microsoft Word is not available."
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if not powershell:
        return False, "Windows PowerShell is not available."
    script_dir = Path(tempfile.mkdtemp(prefix="activity-eval-word-"))
    script_path = script_dir / "export.ps1"
    try:
        script_path.write_text(_word_script(input_path, output_path), encoding="utf-8-sig")
        proc = subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
            ],
            capture_output=True,
            text=True,
            timeout=180,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        return False, "Microsoft Word did not finish exporting the PDF in time."
    except Exception as exc:
        return False, f"Microsoft Word export failed: {exc}"
    finally:
        shutil.rmtree(script_dir, ignore_errors=True)
    if proc.returncode != 0 or not output_path.exists():
        detail = (proc.stderr or proc.stdout or "").strip()
        return False, detail[:300] or "Microsoft Word export failed."
    try:
        if output_path.read_bytes()[:5] != b"%PDF-":
            return False, "Microsoft Word produced an invalid PDF."
    except OSError as exc:
        return False, f"PDF was not readable: {exc}"
    return True, ""


def convert_docx_to_pdf(input_path: Path, output_path: Path) -> tuple[bool, str]:
    if output_path.exists():
        try:
            output_path.unlink()
        except OSError as exc:
            return False, f"Could not replace the old PDF: {exc}"

    details: list[str] = []
    if libreoffice_available():
        try:
            temp_dir = CACHE_DIR / "pdf-tmp"
            temp_dir.mkdir(parents=True, exist_ok=True)
            env = os.environ.copy()
            env["TEMP"] = str(temp_dir)
            env["TMP"] = str(temp_dir)
            env["TMPDIR"] = str(temp_dir)
            proc = subprocess.run(
                [str(NODE), str(CLI), "convert", "--input", str(input_path), "--output", str(output_path)],
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
            )
            if proc.returncode == 0 and output_path.exists() and output_path.read_bytes()[:5] == b"%PDF-":
                return True, ""
            details.append((proc.stderr or proc.stdout or "LibreOffice conversion failed.").strip()[:200])
        except Exception as exc:
            details.append(f"LibreOffice: {exc}")

    ok, detail = _convert_with_word(input_path, output_path)
    if ok:
        return True, ""
    if detail:
        details.append(f"Word: {detail}")
    return False, " | ".join(details) or "PDF conversion failed."
