ACTIVITY EVAL STUDIO — PORTABLE WINDOWS APP
===========================================

No Python installation is needed. Everything is in this folder.

QUICK START
-----------
1. Unzip the whole folder somewhere you can write to, such as:
   Documents\Activity Eval Studio
   (Do not run the exe from inside the zip preview.)
2. Double-click: ActivityEvalStudio.exe
3. A console window opens and your browser goes to:
   http://127.0.0.1:5051
   If 5051 is already in use, the app picks the next free port and prints it.
4. Keep the console window open while you work. Closing it stops the app.
5. Click "LEAP · 3 speakers" or "GFPS · no speakers" to try the supplied
   samples, or drop your own Google Forms CSV.

WHAT IT MAKES
-------------
- One Activity Report .docx for every activity.
- One Speaker/Topic Evaluation Report .docx per detected speaker.
- A ZIP containing everything.
- Optional PDFs. PDF export uses Microsoft Word if installed, otherwise
  LibreOffice Kit if available on the machine.

WHERE FILES GO
--------------
Uploads, generated reports and history are stored per Windows user in:

   %LOCALAPPDATA%\ActivityEvalStudio

The app does not send your CSV anywhere. Everything is local.

TEMPLATES AND MAPPINGS
----------------------
The app seeds its editable configuration into the folder above on first run.
If the committee gives you an updated .docx template or mapping later, use the
app's "Column mapping" panel or replace the files in:

   %LOCALAPPDATA%\ActivityEvalStudio\config
   %LOCALAPPDATA%\ActivityEvalStudio\docx_templates

To reset the app to the templates bundled in this package, close the app and
rename/delete:
   %LOCALAPPDATA%\ActivityEvalStudio
The app will rebuild its working folder on the next launch.

WINDOWS SMARTSCREEN
-------------------
The exe is not code-signed. Windows may show "Windows protected your PC".
Click "More info" -> "Run anyway". If your organization blocks unsigned apps,
ask IT to allow ActivityEvalStudio.exe or sign it with the school's code-signing
certificate.

TROUBLESHOOTING
---------------
- Browser did not open: open the URL printed in the console manually.
- Port already in use: the app automatically chooses the next free port.
- PDF export failed: the DOCX files are still valid. Install Microsoft Word or
  use the packaged PDF only if Word/LibreOffice is available.
- Antivirus quarantine: add an exclusion for the unzipped folder, or run from
  a local Documents folder rather than a network share.
- To stop the app: close the console window.

SHARING WITH MORE PEOPLE
------------------------
Share the entire zipped folder, not just the .exe. Keep the _internal folder
next to the exe. Each person gets their own history under their own
%LOCALAPPDATA%\ActivityEvalStudio.
