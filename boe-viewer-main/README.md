# BOE Extractor & Viewer

Reads Indian Customs **Bill of Entry (BOE)** PDFs with AI, checks the extracted data, and shows it in a web page
(Parts I–VI) that can also be downloaded as a PDF report.

## What it does

- Drop a BOE PDF on the home page; the data appears in the same view as the built-in sample bills.
- Each page is read by a Google Gemini model (page image + the PDF text layer) into a strict schema.
- Every value is rechecked (see [How the data is rechecked](#how-the-data-is-rechecked)).
- Per-bill **PDF** download of the extracted data, per-bill **Delete**, live Gemini cost in the console.

## Folder layout

```
boe/
├── app/       local server + web page (server.py, boe_viewer.html, report.py, cost.py ...)
├── files2/    extraction pipeline (pipeline.py, schemas.py, checks.py), tests, requirements.txt
└── files1/    database schema (boe_schema.sql) and the original static viewer
```

Keep `app/` and `files2/` side by side: the app imports the pipeline from `files2/`.

## Requirements

- **Python 3.11 or newer** (developed on 3.14)
- A **Gemini API key** - free to create at <https://aistudio.google.com/apikey>. Uploads call the Gemini API and are
  billed to that key (roughly a few cents to a few dollars per bill, depending on its size and options).
- Internet access

## Setup

### Windows (PowerShell)

```powershell
cd boe\files2
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

### macOS / Linux

```bash
cd boe/files2
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

Do not copy a `.venv` folder from another machine; create it fresh as above.

## Run

### Windows

```powershell
cd boe\app
..\files2\.venv\Scripts\python server.py
```

### macOS / Linux

```bash
cd boe/app
../files2/.venv/bin/python server.py
```

Then open **http://127.0.0.1:8765**. Use `--port 9000` to change the port. Keep the terminal open: it prints the Gemini
cost of every call (`[cost ...]` lines).

## Using it

1. Open the page. In the **AI extraction** panel paste your **AI Key** and click **Save** (it is checked with Google
   first). The key is kept only in your browser.
   - Alternatively set `GEMINI_API_KEY` in the environment before starting the server and no key prompt is needed.
2. Drag a BOE PDF onto the drop zone (or **Choose file**). Progress is shown in the zone.
3. Click **View bill**. Sections: Part I summary, II invoices, III duties, IV supporting documents, V other
   compliances, VI declaration.
4. **PDF** on a row downloads the extracted data as a PDF; **Delete** removes the bill (sample bills can be restored
   from the link under the list).
5. Optional: turn on **Double-check with a second model** for a slower, costlier independent audit of every field.

Large PDFs: only pages that contain BOE content are rendered and sent to Gemini, so file size mostly affects upload
time and server memory (roughly the PDF size plus a few MB per extracted page). Raise the limits with `MAX_UPLOAD_MB` /
`MAX_PAGES` before starting the server; cost scales with the number of BOE pages, not the file size.

Resume: every finished page is saved under `app/uploads/.cache/`. If a run fails or is stopped, upload the same PDF
again and finished pages are restored instead of re-billed. The cache is deleted when the bill completes.

Uploaded bills are stored as JSON in `app/uploads/`. The original PDF is not kept.

### Confidence scores and editing

- Every field shows a **confidence pill** (for example `92%`). Hover it for how the score was made.
  - Parts I-III (summary, invoices, item duties): the real pipeline score - found on the page, passed the code
    cross-checks, and (if switched on) confirmed by the second model.
  - Everything else (status, parties, Part IV/V/VI, ...): a text match against the PDF - does the value
    appear on the page? Blank values and one-letter flags are shown as `-` (not scored).
- Fields below **80%** are highlighted amber and below **50%** red. The bar at the top of each bill counts them,
  **Review next** jumps to the next one, and the left menu shows how many each section has.
- **Edit any field:** click the pencil on a row, or click a table cell, then Enter to save or Esc to cancel.
  Edited fields show `edited` in blue and count as verified. **Revert to extracted value** is in the editor.
  - Uploaded bills: edits are saved on the server (`app/uploads/<id>.json`) together with the original value.
  - Sample bills: edits are kept in this browser only (localStorage).
- The PDF report uses the edited values. Bills uploaded before this feature have no scores; upload them again to get them.

### Cost in the browser console

Open DevTools (F12) → **Console** before uploading. Each Gemini call prints its tokens and cost, with a running total
and a summary table when the run finishes. The terminal running `server.py` shows the same lines.

### Models

Defaults are set in `app/extract_service.py` and can be overridden with environment variables:

| Variable | Default | Role |
|---|---|---|
| `EXECUTOR_MODEL` | `gemini-3.8-flash` | reads every page |
| `EVALUATOR_MODEL` | `gemini-3.1-pro-preview` | optional second-model audit |
| `MAX_UPLOAD_MB` | `300` | largest PDF the server accepts (the page shows this limit) |
| `MAX_PAGES` | `600` | largest page count accepted |
| `EXTRACT_CONCURRENCY` | `12` | Gemini calls run in parallel (raise for speed if your quota allows) |
| `RENDER_DPI` | `150` | page image resolution; `110` is faster with slightly lower accuracy |
| `EXTRACT_ATTEMPTS` | `4` | tries per page on temporary errors (rate limit, 5xx, timeout), with waiting between tries |

Prices used for the cost lines are in `app/cost.py`; update them if Google changes pricing.

## How the data is rechecked

1. **Strict prompts** - copy values exactly as printed; never compute, round or convert. Temperature 0.
2. **Evidence gate** (Parts I–III) - each value must appear in the page's text layer, otherwise the model must re-read
   (up to 2 retries).
3. **Code cross-checks** (`files2/checks.py`) - item arithmetic, invoice totals, counts, valuation, duty totals,
   proportional assessable value.
4. **Optional evaluator** - a different, stronger model checks each field against the page image.
5. **Per-field score** - fields below 0.8 are marked *needs review*; the banner on an uploaded bill lists them.

Not cross-checked: status flags, parties, supporting documents, Part V and declarations. Passing checks means the
data is consistent, not guaranteed correct.

## Tests

```powershell
cd boe\files2
.\.venv\Scripts\python -m pytest -q
```

(`./.venv/bin/python -m pytest -q` on macOS/Linux.) These cover the cross-check logic only and make no API calls.

### Command-line extraction (no web page)

```powershell
cd boe\files2
$env:GEMINI_API_KEY = "your-key"
.\.venv\Scripts\python pipeline.py path\to\BE.pdf --out result.json
```

Add `--no-eval` to skip the evaluator. It uses the same model defaults and environment variables as the app.

## Technology

- **Pydantic AI** - runs the AI agents and enforces the output schema
- **Google Gemini** - extractor (Flash) and optional auditor (Pro)
- **PyMuPDF** - splits PDFs into page images and text
- **Python standard-library HTTP server** - upload, progress polling, PDF report endpoint
- **ReportLab** - builds the extracted-data PDF
- **Plain HTML / CSS / JavaScript** - the viewer, no build step

## Troubleshooting

| Problem | Fix |
|---|---|
| Upload button says it needs the local server | Start `server.py` and open the page at `http://127.0.0.1:8765`, not the HTML file directly |
| "AI Key was rejected" | Paste a valid key from AI Studio; the old one is cleared automatically |
| "model ... is not available" | Set `EXECUTOR_MODEL` / `EVALUATOR_MODEL` to models your key can use |
| Rate limit / quota error | Wait and retry, or check the key's quota in Google AI Studio |
| No cost lines in the browser console | Open DevTools **before** starting the upload |
| Port already in use | Run `server.py --port 9000` |

## Privacy and security

- The key stays in the browser (localStorage) and is sent to the local server per request; it is never written to
  disk or logged.
- The server listens on `127.0.0.1` only and rejects cross-origin requests.
- Uploaded PDFs are sent to Google's Gemini API for processing. Do not upload documents you are not allowed to share
  with that service.
- The viewer ships with two sample bills built in; remove or replace them before sharing the project outside your
  organisation.
