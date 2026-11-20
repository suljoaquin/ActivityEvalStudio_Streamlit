# Sample reconciliation audit

This is the exact comparison between the supplied sample reports and the reports this app generates from the same CSV. The generator **recomputes values from the CSV**; where the supplied `.docx` is internally inconsistent, the computed value wins and the difference is listed below.

## Inputs inspected

| Purpose | File |
|---|---|
| Activity sample, with 3 speakers | `docx_templates/source/activity_report_sample.docx` (copy of `2026_09_30 LEAP Capability Training.docx`) |
| Activity sample, no speakers | `docx_templates/source/activity_report_gfps_sample.docx` (copy of `2026_10_28-29 GFPS.docx`) |
| Speaker 1 sample | `docx_templates/source/speaker_report_sample.docx` (copy of `1. SpeakerEval_LEAP.docx`) |
| Speaker 2 sample | `docx_templates/source/speaker_report_2_sample.docx` (copy of `2. SpeakerEval_LEAP.docx`) |
| Speaker 3 sample | `docx_templates/source/speaker_report_3_sample.docx` (copy of `3. SpeakerEval_LEAP.docx`) |
| With-speaker CSV | `samples/leap_with_speakers.csv` |
| No-speaker CSV | `samples/gfps_no_speakers.csv` |

## Template inventory

- **Page size**: A4 (8.27 × 11.69 in) for both report types.
- **Activity margins**: L 1.0", R 1.0", T 1.5", B 0.7"; header 0.3"; footer 0.3".
- **Speaker margins**: L 1.0", R 1.0", T 1.0", B 1.0"; header/footer 0.3".
- **Sections**: one Word section in every supplied report. No section breaks, no alternating orientation, no different first-page header.
- **Header**: PSHS-SRC logos + "Activity Evaluation and Customer Satisfaction Committee". Preserved untouched.
- **Footer**: activity report uses the committee contact footer; speaker reports add a page-number field plus postal/email footer. Preserved untouched.
- **Embedded charts**: none. Only header/footer logos are images. No chart XML parts exist.
- **Tables**:
  - Activity metadata: 4×2, `Table Grid`.
  - Activity summary: 2×2.
  - Activity criteria: 17×3 (header + 3 merged group rows + 13 criteria rows); the hospitality row is row 12.
  - Speaker metadata: 4×2; speaker info: 2×2; summary: 2×2; respondents: 1×2.
  - Speaker topic: 5×3; speaker resource person: 13×3 with merged group rows.
- **With-speaker vs no-speaker Activity template**: structurally identical. The only differences are the metadata/signatory values and the comments. The generator therefore uses **one** Activity template for both cases.

## LEAP Capability Training (with 3 speakers)

CSV: 19 responses, all consenting. One response (row 4 in the CSV, timestamp 9/30/2026 15:48:35) answered no activity item but answered all three topic-depth items. That is the source of the 18/19 respondent difference.

### Activity Report

| Item | Supplied sample | Generated | Why |
|---|---:|---:|---|
| N respondents | 18 | **18** | Consenting responses with at least one valid activity rating. |
| Overall satisfaction | 4.61 (Excellent) | **4.61 (Excellent)** | Mean of the two Overall Evaluation item means. |
| Length of the program | 4.56, "Very Satisfactory" | **4.56, "Excellent"** | The template's own legend says 4.20–5.00 = Excellent. The sample label contradicts the legend. |
| Schedule of activities | 4.67, "Very Satisfactory" | **4.67, "Excellent"** | Same legend contradiction. |
| Audio/Visuals | 4.56, "Excellent" | **4.56, "Excellent"** | Match. |
| Food/meals | 4.64, "Very Satisfactory" | **4.64, "Excellent"** | The sample labels 4.64 as Very Satisfactory even though 4.64 is in 4.20–5.00. |
| Secretariat | 4.71 (n=17) | **4.71 (n=17)** | One N/A excluded. |
| Hotel accommodation row | N/A row present | **Row removed** | The LEAP form has no hotel/accommodation question. The acceptance rule is to remove the empty optional row cleanly. The row is removed at the `<w:tr>` level, with no blank page or orphaned break. |
| Part II comments | 7 numbered comments | **7** | `N/a` filtered; multi-line first answer preserved as a numbered first line plus unnumbered continuation. |
| Part III comments | "Every respondent answered “None.”" | **Same sentence** | All Part III answers were `N/a`/`none`; the template's no-comment sentence is used. |

The rest of the table values and all paragraph/heading/table formatting match the sample.

### Speaker 1 — HON. CATHERINE A. VELASCO-SUPEDA

All values match:

- Topic/Subject Matter: **2.76 (Excellent)** — 2.74, 2.79, 2.74.
- Resource Person: **4.62 (Strongly Agree)**.
- N: **19**.
- Item means: 4.61, 4.72, 4.56, 4.67, 4.72, 4.56, 4.44, 4.67, 4.56, 4.72.
- Comments: Q1 **13**, Q2 **3**, Q3 **8**.

The generated Speaker 1 pages 1–2 are pixel-identical to the supplied sample when both are rendered by LibreOffice (same SHA-256 page images), and its paragraph/table sequence is identical in the automated test.

### Speaker 2 — MS. MAUDE ANGELA G. AUJERO, RPh

- Topic/Subject Matter: **2.79 (Excellent)**.
- Resource Person: **4.63 (Strongly Agree)**.
- N: **19**.
- Comments: Q1 **13**, Q2 **4**, Q3 **5**.
- **Sample bug corrected**: the supplied Speaker 2 document repeats the Q2 answers under Q3. The generated report uses the actual Q3 column (`School shooting`, `Nothing in mind.`, `I think all topic is covered`, `idk`, `None, I think...`).

### Speaker 3 — MR. ARJIE P. CASTILLON, RMicro

- Topic/Subject Matter: **2.93 (Excellent)**.
- Resource Person: **4.82 (Strongly Agree)**.
- N: **19**.
- Comments: Q1 **13**, Q2 **2**, Q3 **4**.
- The sample's values match; the app reproduces them.

### Speaker report template quirks

- The sample's `RATING` column header wraps to `RATIN G` in LibreOffice because the 1,135-twip column plus cell margins cannot fit the 11 pt bold word. The generated files inherit the same table geometry and therefore render the same way. It is a property of the committee's template, not a generation error.
- Q3's heading had accidental leading spaces in the sample. The compiler removes only those spaces while preserving the bold heading runs.

## PSHS-SRC GFPS Deepening Session (no speakers)

CSV: 11 responses, all consenting. The supplied report shows every criterion as 5.00. The CSV contains 4s, so this app recomputes those items:

| Item | Supplied sample | Generated | CSV support |
|---|---:|---:|---|
| N respondents | 11 | **11** | All 11 answered at least one activity item. |
| Overall satisfaction | 5.00 (Excellent) | **5.00 (Excellent)** | Both Overall Evaluation items are 5.00. |
| Content objectives | 5.00 | **5.00** | Match. |
| Information clear | 5.00 | **5.00** | Match. |
| Examples/exercises | 5.00 | **5.00** | Match. |
| Audio/Visuals | 5.00 | **4.73** | Sample is stale/inconsistent. |
| Content relevance | 5.00 | **5.00** | Match. |
| Length | 5.00 | **4.91** | Sample is stale/inconsistent. |
| Schedule | 5.00 | **4.82** | Sample is stale/inconsistent. |
| Secretariat | 5.00 | **4.91** | Sample is stale/inconsistent. |
| Venue | 5.00 | **4.91** | Sample is stale/inconsistent. |
| Hotel accommodation | N/A | **N/A** | CSV collected 8 answers, but the preset treats this on-campus session as non-residential. Toggle **Applicable** to compute the 5.00 hotel mean. |
| Food/meals | 5.00 | **4.91** | Sample is stale/inconsistent. |
| Overall objectives accomplished | 5.00 | **5.00** | Match. |
| Increased knowledge | 5.00 | **5.00** | Match. |

Comments match the sample's filtering behavior:

- Part II: 4 comments (`More time`, `To conduct review of the day before activity`, `More time for GMEF`, `More of this kind of deepenings sessions...`); `NONE`/`none` filtered.
- Part III: 2 comments (`None so far`, `Conduct the Deepening Session outside...`); `NONE` filtered, `None so far` kept.

The table geometry, 17-row criteria table, N/A hotel row, headers, footers and signatory block match the supplied sample.

## Things the app intentionally does differently from the supplied files

1. **Rating labels follow the printed legend**, not the sample's inconsistent `Very Satisfactory` labels at 4.56/4.64/4.67.
2. **Speaker 2 Q3 is no longer a duplicate of Q2.**
3. **The empty LEAP hospitality row is removed**, because that form has no hospitality question. If the form has the question, the row is kept (N/A by default, or computed when the applicability toggle is on).
4. **GFPS numbers are recomputed** from all 11 responses, not copied from the stale all-5.00 sample.
5. **Prepared/checked names** are real template tags now; the sample files had them hard-coded.
6. **No section breaks are introduced or orphaned**. The supplied reports are single-section documents; the generator preserves that one section and its header/footer relationship.

## Verification performed

- Reopened every generated `.docx` with `python-docx`; no unrendered `{{ }}` / `{% %}` tags.
- **Opened every generated `.docx` in Microsoft Word 16 via COM.** All five opened without a repair prompt. Word page counts:
  - LEAP Activity: **2**
  - LEAP Speaker 1: **2**
  - LEAP Speaker 2: **3** (one extra Q3 comment compared with the sample's duplicated Q2 block)
  - LEAP Speaker 3: **2**
  - GFPS Activity: **2**
  - The supplied source reports also open as 2 pages each in Word. Speaker 2 therefore gains one page because its Q3 block now contains the five real Q3 answers instead of the sample's four duplicated Q2 answers.
- Converted all generated reports to PDF with LibreOffice Kit; page counts: LEAP Activity 2, each Speaker Report 3, GFPS Activity 2. No blank pages appeared where the hospitality row was removed. LibreOffice's pagination differs from Word for the speaker reports; the `.docx` is the source of truth.
- Compared rendered page images to the supplied Speaker 1 and Activity page 2 images: identical SHA-256 hashes for the unchanged pages.
- Automated tests compare the full paragraph/table skeleton of the generated Speaker 1 report to the supplied reference.

