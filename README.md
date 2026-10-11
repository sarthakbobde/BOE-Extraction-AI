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
├── run.py                  start the viewer:  python run.py
├── requirements.txt        Python dependencies
├── pytest.ini              test settings (tests run from the repository root)
├── src/boe/                the application (a Python package)
│   ├── extraction/         reading a PDF with the AI and checking it
│   │   ├── pipeline.py       prompts, agents, evidence gate, evaluator, field scoring (also a CLI)
│   │   ├── schemas.py        schemas for Parts I-III (the evidence-checked core)
│   │   ├── viewer_schemas.py schemas for the other sections (status, parties, Part IV/V/VI ...)
│   │   ├── checks.py         deterministic cross-checks
│   │   ├── extract_service.py  orchestrator: classify pages, call agents, check, score, build the document
│   │   ├── sections.py       printed Part IV section letters
│   │   └── cost.py           live Gemini cost meter
│   ├── document/           turning the extraction into what the viewer shows
│   │   ├── to_viewer.py      extraction -> viewer document; confidence mapping
│   │   ├── confidence.py     text-match and model ratings
│   │   └── report.py         extracted-data PDF report
│   ├── web/                the local server and the page
│   │   ├── server.py         HTTP server and API routes
│   │   ├── pdfview.py        PDF page rendering and text search
│   │   └── static/boe_viewer.html   the whole front end
│   └── paths.py            where data lives on disk
├── tests/                  test_checks.py, test_ratings.py (no AI calls)
├── database/               schema.sql (PostgreSQL) and migrations/
├── docs/                   technical overview, how the AI decides, running the viewer
├── legacy/                 the original static viewer prototype
└── data/                   git-ignored: uploads/ (stored bills), samples/ (D1.pdf, D2.pdf), logs/
```

Set `BOE_DATA_DIR` to keep the data folder somewhere else.

## Requirements

- **Python 3.11 or newer** (developed on 3.14)
- A **Gemini API key** - free to create at <https://aistudio.google.com/apikey>. Uploads call the Gemini API and are
  billed to that key (roughly a few cents to a few dollars per bill, depending on its size and options).
- Internet access

## Setup

### Windows (PowerShell)

```powershell
cd boe
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

### macOS / Linux

```bash
cd boe
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

Do not copy a `.venv` folder from another machine; create it fresh as above.

## Run

### Windows

```powershell
cd boe
.\.venv\Scripts\python run.py
```

### macOS / Linux

```bash
cd boe
./.venv/bin/python run.py
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

Resume: every finished page is saved under `data/uploads/.cache/`. If a run fails or is stopped, upload the same PDF
again and finished pages are restored instead of re-billed. The cache is deleted when the bill completes.

Uploaded bills are stored in `data/uploads/` as `<id>.json` (the extracted data) and `<id>.pdf` (the original file, kept so
you can compare side by side). Deleting a bill removes both.

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
  - Uploaded bills: edits are saved on the server (`data/uploads/<id>.json`) together with the original value.
  - Sample bills: edits are kept in this browser only (localStorage).
- The PDF report uses the edited values. Bills uploaded before this feature have no scores; upload them again to get them.

### Side-by-side source PDF

On a bill's detail page, **Show source PDF** (left menu) opens the original PDF beside the data.

- It follows what you're looking at: switching section jumps to that part's page, and clicking a field (or a table
  cell, or opening an item) jumps to the page it came from and **highlights where the value is printed**.
- The PDF is one **continuous scroll** (all pages stacked; images load as you scroll). The counter in the header follows
  your position; the page arrows, zoom, Fit and **Open** (the full PDF in a new tab) are there too.
- Editing a field does not move you: the PDF keeps its place.
- Pages are rendered by the server (PyMuPDF), so no browser PDF plugin is needed. Page sizes are sent first so the
  layout does not jump while images load.
- Bills uploaded before PDFs were kept show "Source PDF was not kept" - upload them again.
- The two sample bills use `data/samples/D1.pdf` and `D2.pdf` (git-ignored; copy the sample PDFs there to enable it).

### Cost in the browser console

Open DevTools (F12) → **Console** before uploading. Each Gemini call prints its tokens and cost, with a running total
and a summary table when the run finishes. The terminal running `server.py` shows the same lines.

### Models

Defaults are set in `src/boe/extraction/extract_service.py` and can be overridden with environment variables:

| Variable | Default | Role |
|---|---|---|
| `EXECUTOR_MODEL` | `gemini-3.8-flash` | reads every page |
| `EVALUATOR_MODEL` | `gemini-3.1-pro-preview` | optional second-model audit |
| `MAX_UPLOAD_MB` | `300` | largest PDF the server accepts (the page shows this limit) |
| `MAX_PAGES` | `600` | largest page count accepted |
| `EXTRACT_CONCURRENCY` | `12` | Gemini calls run in parallel (raise for speed if your quota allows) |
| `RENDER_DPI` | `150` | page image resolution; `110` is faster with slightly lower accuracy |
| `EXTRACT_ATTEMPTS` | `4` | tries per page on temporary errors (rate limit, 5xx, timeout), with waiting between tries |

Prices used for the cost lines are in `src/boe/extraction/cost.py`; update them if Google changes pricing.

## Documentation

- [`docs/01-technical-overview.md`](docs/01-technical-overview.md) - architecture, data flow, API, front end, storage, how to extend.
- [`docs/02-how-the-ai-decides.md`](docs/02-how-the-ai-decides.md) - how pages are read, checked and scored, and what a score means.

## What is extracted (every printed field)

The viewer mirrors the PDF section by section, in the PDF's order and with its printed letters (Part IV letters are read
from each PDF because they differ between form versions):

- **Part I:** A Status (1-16), B Declarant (incl. AEO, UCR), C Duty summary (1-19), D Manifest (IGM, INW, GIGM, MAWB, HAWB),
  E Bond details, F Payment, G Warehouse, H Processing, I Invoice summary, J Containers.
- **Part II:** A Invoice (incl. PO / LC / contract / AD code), B Parties (incl. AEO), C Valuation (both currencies),
  D Cost & services (1-14), E Items.
- **Part III:** per item, A Item details (fields 1-30), B Item duty, C Other duties, C-A Other duties - A (each a matrix of
  duty columns x Notn No., Notn SNo., Rate, Amount, Duty Fg).
- **Part IV:** every section the form prints (A-L, supporting documents, containers, invoice details).
- **Part V / VI:** examination order (A and A1), instructions, PGA, compliance, remarks, OOC; declarations and signatory.

Bills extracted before this schema (no `schema: 2` in their JSON) show a "partial" / "not extracted" tag on the
sections that were not read; upload them again to get every field. The full list of fields per section is in
`database/schema.sql` (database) and `src/boe/extraction/schemas.py` (extraction).

## How the data is rechecked

1. **Strict prompts** - copy values exactly as printed; never compute, round or convert. Temperature 0.
2. **Evidence gate** (Parts I–III) - each value must appear in the page's text layer, otherwise the model must re-read
   (up to 2 retries).
3. **Code cross-checks** (`src/boe/extraction/checks.py`) - item arithmetic, invoice totals, counts, valuation, duty totals,
   proportional assessable value.
4. **Optional evaluator** - a different, stronger model checks each field against the page image.
5. **Per-field score** - fields below 0.8 are marked *needs review*; the banner on an uploaded bill lists them.

Not cross-checked: status flags, parties, supporting documents, Part V and declarations. Passing checks means the
data is consistent, not guaranteed correct.

## Tests

```powershell
cd boe
.\.venv\Scripts\python -m pytest -q
```

(`./.venv/bin/python -m pytest -q` on macOS/Linux.) These cover the cross-check logic only and make no API calls.

### Command-line extraction (no web page)

```powershell
cd boe
$env:GEMINI_API_KEY = "your-key"
$env:PYTHONPATH = "src"
.\.venv\Scripts\python -m boe.extraction.pipeline path\to\BE.pdf --out data\result.json
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
- Uploaded PDFs are also kept on disk in `data/uploads/` (git-ignored) until you delete the bill.
- The viewer ships with two sample bills built in; remove or replace them before sharing the project outside your
  organisation.
