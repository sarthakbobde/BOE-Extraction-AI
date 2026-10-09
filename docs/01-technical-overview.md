# BOE Extractor & Viewer — Technical Overview

How the application is built and how its pieces talk to each other. For *how the AI decides things* (extraction,
checks, scoring) read [`02-how-the-ai-decides.md`](02-how-the-ai-decides.md).

---

## 1. What the application does

You upload an Indian Customs **Bill of Entry (BOE)** PDF. The app:

1. reads every page with Google Gemini (page image + the PDF's text layer),
2. validates the result with code, scores every field, and stores it,
3. shows it in a web page that mirrors the PDF section by section (Parts I–VI), with an editable value per field, a
   confidence score per field, and the original PDF beside it with the value highlighted,
4. lets you correct values, and download the result as a PDF report.

Everything runs locally: a small Python server plus one HTML page. The only outside call is to the Gemini API.

---

## 2. Architecture

```
 Browser  (app/boe_viewer.html — plain HTML/CSS/JS, no framework)
   │   fetch /api/...                                  localStorage: AI key, sample-bill edits, UI choices
   ▼
 server.py  (Python standard-library ThreadingHTTPServer, 127.0.0.1 only)
   │
   ├── POST /api/extract ──► background thread ──► extract_service.extract()
   │                                                   │
   │                                                   ├── PyMuPDF   : pages → text layer + 150-dpi PNG
   │                                                   ├── pydantic-ai agents ──► Gemini (executor model)
   │                                                   ├── files2/checks.py     : cross-checks (pure Python)
   │                                                   ├── files2/pipeline.py   : scoring, optional evaluator model
   │                                                   ├── to_viewer.py         : extraction → viewer document
   │                                                   ├── confidence.py        : per-field scores
   │                                                   └── cost.py              : token & dollar tracking
   │
   ├── GET  /api/pdf/<id>/...  ──► pdfview.py (PyMuPDF: render pages, find text)
   ├── POST /api/report        ──► report.py  (ReportLab → PDF)
   └── uploads/<id>.json + <id>.pdf   (the only storage)
```

There is **no database in the running app**. Bills are JSON files. `files1/boe_schema.sql` is the designed PostgreSQL
model for loading the data later; nothing writes to it yet.

### Folder map

| Path | Purpose |
|---|---|
| `app/server.py` | HTTP server, all API routes, job runner, edit endpoint, file storage |
| `app/extract_service.py` | The extraction orchestrator: classify pages → call agents → checks → score → build document |
| `app/to_viewer.py` | Converts the extraction objects into the viewer's JSON document; maps pipeline scores to viewer paths |
| `app/viewer_schemas.py` | Pydantic schemas for sections the pipeline doesn't evidence-gate (status, parties, Part IV/V/VI …) |
| `app/confidence.py` | Text-match scoring for those sections |
| `app/sections.py` | Reads the *printed* Part IV section letters from a PDF (they differ by form version) |
| `app/pdfview.py` | Page rendering, page sizes, text search (for the PDF pane + highlights) |
| `app/report.py` | The extracted-data PDF report (ReportLab) |
| `app/cost.py` | Live Gemini cost meter |
| `app/boe_viewer.html` | The whole front end (~2,000 lines) |
| `app/uploads/` | Stored bills: `<id>.json` (data) + `<id>.pdf` (original). Git-ignored |
| `app/samples/` | `D1.pdf`, `D2.pdf` for the two built-in sample bills. Git-ignored |
| `files2/schemas.py` | Extraction schemas for Parts I–III (the evidence-checked core) |
| `files2/pipeline.py` | Prompts, agents, evidence gate, optional evaluator, field scoring (also a CLI) |
| `files2/checks.py` | Deterministic cross-checks |
| `files2/test_checks.py` | 20 tests for schemas, checks and score caps (+ `app/test_ratings.py`, 4 tests of the High/Medium/Low logic) |
| `files1/boe_schema.sql` | PostgreSQL schema (36 tables) + `migration_001/002` |

---

## 3. The upload lifecycle (step by step)

1. **Browser** (`handleFile` → `runExtraction`): sends the raw PDF as the request body to `POST /api/extract` with headers
   `X-Gemini-Key` (from localStorage, never stored on the server), `X-Filename`, `X-Eval` (second-model check on/off).
2. **Server** validates (starts with `%PDF`, ≤ 40 MB, key present), creates a job id, starts a thread, returns `{jobId}`.
3. **Job thread** runs `asyncio.run(extract(...))` and updates a job record (`done/total/message`).
4. **Browser** polls `GET /api/jobs/<id>` every second: progress bar, and the per-call cost events (printed to the
   browser console). The server prints the same cost lines to its own console / `server.log`.
5. **`extract()`** (`extract_service.py`):
   1. open the PDF (≤ 120 pages), build per-page text + PNG;
   2. classify each page into *kinds* (see §5);
   3. run one agent call per (page, kind), 4 at a time, as `asyncio` tasks;
   4. `assemble()` core results into a `BoeExtraction`; `run_all_checks()`;
   5. optional evaluator (second model) on Part I–III pages;
   6. `score_fields()` → per-field scores;
   7. `build_doc()` → viewer document + merged confidence;
   8. attach `sectionLetters` (printed Part IV letters).
6. **Server** `save_doc()`: assigns an id, replaces any older bill with the same (port, BE no, date), writes `<id>.json`
   and `<id>.pdf`. The job becomes `done` with the document.
7. **Browser** `ingestDoc()`: keeps an un-escaped copy in `RAW[key]`, an HTML-escaped copy in `DOCS[key]`, and renders.

Errors map to codes the UI understands: `bad_key`, `no_key`, `bad_pdf`, `not_boe`, `too_big`, `bad_model`,
`rate_limit`, `failed`. A rejected key clears the saved key and re-prompts.

---

## 4. The viewer document (what is stored in `<id>.json`)

One JSON object per bill. Every displayed value has a **dotted path** into it, e.g. `invoices.0.valuation.freight`,
`invoices.0.duties.5.bcdAmount`, `status.mode`. Paths are the glue between the UI, confidence scores, edits and the PDF
highlight.

```
boe            header: portCode, beNo, beDate, totals …           declarations   [{for, text}]
status         Part I A (flags, countries, ports)                 signatory      {chaName, date, place}
declarant      Part I B                                           compliance     Part V (or null)
dutySummary    Part I C — all 19 cells                            additional     Part IV A–L sections (tables)
manifest       Part I D                                           supportingDocs Part IV supporting documents
bonds[] warehouse[] payments[] events[] containers[]              conf           {path: {s, b, r}}   (scores; shown as High/Medium/Low)
invoices[]     { sno,no,date,po/lc/contract,adCode,amount,        edits          {path: {orig, origConf, at}}
                 parties{}, valuation{}, cost{}, items[[…]],      pageMap        which PDF page each section/row is on
                 duties{ itemsn: {A fields…, bcdRate, igstNotnNo,…} } }
hasPdf, pageCount, sectionLetters, schema(=2), quality{fields,failedChecks,needsReview,evaluator,review[],checks[]}
```

- **Items** are arrays `[sno, cth, description, unitPrice, qty, uqc, amount]` (path `…items.3.4` = quantity of item 4).
- **Duty matrices** (Part III B / C / C-A) are flattened: one key per cell, `<code><Row>`, e.g. `bcdRate`, `igstNotnNo`,
  `caidcDutyFg`. Codes are canonical lower-case (`cvd05`, `gcess`, `spexd`).
- **`schema: 2`** marks bills read with the full schema. Bills without it are "older": the viewer shows *partial /
  not extracted* tags on the sections that weren't read then.
- **Edits** change the value in place and record the original so it can be reverted. The server only accepts edits to
  data paths (a deny-list blocks `id`, `conf`, `edits`, `quality`, `pageMap`, `schema` …).

---

## 5. Extraction pipeline in code

### 5.1 Page kinds (`extract_service.classify_all`)
Pure text rules on the page's text layer (no AI): a page can have several kinds.

| Kind | Rule | Schema | Evidence-checked? |
|---|---|---|---|
| `summary` | contains `PART - I - BILL OF ENTRY SUMMARY` | `SummaryPage` | yes |
| `part1` | same page | `Part1Details` (status, declarant, manifest, bond, warehouse, payments, events, containers, header) | no |
| `invoice` | `PART - II - INVOICE & VALUATION` | `InvoicePage` | yes |
| `inv_details` | invoice page that has `BUYER'S NAME` (first page of an invoice) | `InvoiceDetails` | no |
| `duties` | `PART - III - DUTIES` | `DutyPage` (items → A fields, B/C/C-A `DutyCell`s) | yes |
| `part4` | `PART - IV - ADDITIONAL DETAILS` (every such page) | `Part4Page` | no |
| `part5` | `PART - V - OTHER COMPLIANCES` | `Part5Page` | no |
| `part6` | `PART - VI - DECLARATION` | `Part6Page` | no |

### 5.2 Agents
- Library: **pydantic-ai** (`Agent(model, output_type=Schema, instructions=…, retries=2)`), model settings
  `temperature=0`.
- Input per call: the page **text layer** (as text) + the page **PNG at 150 dpi** (as an image part).
- Concurrency: an `asyncio.Semaphore(4)`.
- Default models: executor `gemini-3.8-flash`, evaluator `gemini-3.1-pro-preview`
  (`EXECUTOR_MODEL` / `EVALUATOR_MODEL` env vars).
- The structured output is validated by pydantic: a malformed answer triggers a retry.

### 5.3 Schemas (the contract with the model)
- `Val` = `{value: str}`; `Ev(Val)` adds a `quote`. Numbers are kept **as the printed string** ("14482.490000"), so there
  is no float drift; conversion to `Decimal`/float happens later in code.
- Blank printed cell → `None`. A printed `0` stays `"0"`.
- `DutyCell{code, notn_no, notn_sno, rate, amount, duty_fg}` models one column of the Part III duty matrices.
- Part IV uses *row of cells in a fixed column order per section* (`PART4_SECTIONS`) — the prompt lists each section's
  columns and the model returns cells in that order.

### 5.4 From extraction to the viewer document (`to_viewer.build_doc`)
Formats and normalises (dates → `14-Feb-2026`, numbers → float, whitespace), groups invoice pages by invoice,
sorts items, flattens the duty matrices, merges Part IV containers/supporting documents, builds the page map, then
attaches confidence (see the AI document).

---

## 6. API reference

| Method & path | What it does |
|---|---|
| `GET /` | Serves `boe_viewer.html` |
| `GET /api/config` | `{serverKey, samplePdfs, executorModel, evaluatorModel}` |
| `GET /api/docs` | All stored bills (adds `hasPdf`, and `sectionLetters` for bills that have a PDF but no letters yet) |
| `POST /api/check-key` | Validates a key by listing models (free, no tokens) |
| `POST /api/extract` | Start an extraction job (raw PDF body) → `{jobId}` |
| `GET /api/jobs/<id>` | `{status, done, total, message, cost{events…}, doc?, error?}` (jobs kept 1 h) |
| `POST /api/docs/<id>/edit` | `{path, value}` or `{path, revert:true}`; stores the original for revert |
| `DELETE /api/docs/<id>` | Removes the bill's JSON and PDF |
| `GET /api/pdf/<id>/info` | `{pages, sizes[[w,h]…]}` — lets the viewer lay out every page before images load |
| `GET /api/pdf/<id>/page/<n>.png?w=1100` | A rendered page |
| `GET /api/pdf/<id>/find?pages=3,4&q=a\|\|b` | First page holding any variant, with match boxes as page fractions |
| `GET /api/pdf/<id>/file` | The original PDF (inline) |
| `POST /api/report` | Body = bill JSON → extracted-data PDF (ReportLab) |

`<id>` is a 12-hex bill id, or `D1` / `D2` for the sample bills (served from `app/samples/`).

Limits: PDF ≤ 40 MB and ≤ 120 pages; report body ≤ 8 MB; edit body ≤ 200 KB.

---

## 7. Front end (`boe_viewer.html`)

One file, plain JavaScript. Main parts:

| Part | What it does |
|---|---|
| `DOCS` / `RAW` | `RAW[key]` = real values; `DOCS[key]` = the same, HTML-escaped (all uploaded text is untrusted). Sample bills are hard-coded constants, cloned at start (`initDocs`) |
| `CATALOG`, `NAV`, `sectionsFor` | Every section of every part, in PDF order, with printed letters; for Part IV the letters come from the bill (`sectionLetters`) |
| `renderMain` | One branch per part/section. Rows come from `Fld(no, label, path)`; tables from `ecell(path, text)` |
| Editing | `row()` / `ecell()` carry `data-path`; `editField` / `editCell` open an inline editor; `commitEdit` coerces the type, POSTs to the server (uploads) or stores in localStorage (sample bills), re-renders |
| Confidence UI | `confOf(path)` → pill, colour classes (`c-low` < 80 %, `c-vlow` < 50 %, `c-edited`), review bar, `Review next`, per-section counters (`LOWMAP`) |
| PDF pane | All pages as a continuous scroll (sizes first, images lazily by position); `pdfFocus(path)` finds candidate pages (`pageMap`), asks `/find`, draws highlight boxes; the pane element survives re-renders so edits don't reset it |
| Upload card | Drag-and-drop, key panel (verified via `/api/check-key`), progress, cost events → browser console |
| Downloads | `downloadReport` posts `RAW[key]` to `/api/report` and saves the PDF |

Browser storage keys: `boe_gemini_key` (AI key), `boe_sample_edits` (edits to the two sample bills),
`boe_hidden_samples` (sample bills you deleted), `boe_pdf_open` (pane open/closed).

---

## 8. Security & privacy design

- Server binds to `127.0.0.1` only; POST/DELETE reject a cross-origin `Origin` header.
- The Gemini key lives in browser localStorage and travels in a request header; the server never writes it to disk or
  logs it (error messages have it masked).
- Uploaded text is HTML-escaped before it reaches `innerHTML` (`deepEscape`); the report builder escapes markup.
- IDs are validated by regex; edit paths are validated and deny-listed; sizes are capped.
- Uploaded PDFs are sent to Google's Gemini API, and kept in `app/uploads/` (git-ignored) until the bill is deleted.

---

## 9. Cost tracking

`cost.py` prices every call from its token usage (output tokens already include Gemini's "thinking" tokens).
Prices (USD per 1M tokens, standard tier): Flash `0.75 in / 3.75 out` until 2026-12-31 then `1.50 / 7.50`;
Pro-preview `2 / 12` (≤ 200k prompt tokens) else `4 / 18`. Each call prints a line on the server console and is sent to the
browser as an event. Real numbers so far: roughly **$0.016–0.02 per call**; a 6-page bill ≈ $0.07, a 19-page bill ≈ $0.34.

---

## 10. Database design (not wired in yet)

`files1/boe_schema.sql` — PostgreSQL, 36 tables: `boe` → `boe_invoice` → `boe_invoice_item` → `boe_item_duty`
(one row per item per duty type, with `ref_duty_type`), plus one table per Part I/IV/V/VI section and a
`boe_field_catalog`. Every field the extractor reads has a column. `migration_001` added the late-found fields;
`migration_002` turns "Duty Fg" into an amount column. Loading extracted JSON into these tables is future work.

---

## 11. Testing

- `cd files2 && python -m pytest -q` → **20 tests** on the schemas and cross-checks (golden data from a real bill,
  injected mistakes such as a digit swap, wrong column, dropped item; legacy-format loading; new duty rules).
- UI and mapping were verified with offline scripts (synthetic full-schema bill, sweeps over every section page) and
  with three real extractions compared with the PDF page images.
- Not covered by automated tests: the model's output quality (needs a real, paid run), the browser UI, the report layout.

---

## 12. Running & configuring

```powershell
cd boe\files2 ; python -m venv .venv ; .\.venv\Scripts\pip install -r requirements.txt
cd ..\app     ; ..\files2\.venv\Scripts\python server.py          # http://127.0.0.1:8765
```
Env vars: `GEMINI_API_KEY` (server-side key, so no key prompt), `EXECUTOR_MODEL`, `EVALUATOR_MODEL`,
`PYDANTIC_AI_NO_BANNER=1`. Tip: run the server in a visible terminal to see the cost lines.

---

## 13. How to extend

**Add a field** (e.g. a new box on the form)
1. Add it to the extraction schema (`files2/schemas.py` if it should be evidence-checked and scored, otherwise
   `app/viewer_schemas.py`), with the printed field number in its description.
2. Map it in `app/to_viewer.py` (document key) — and in `SUMMARY_MAP` / `HEADER_MAP` / `DUTY_MAP` so its pipeline score
   lands on the right path.
3. Show it in `renderMain` with `Fld(no, label, path)` (or an `ecell` column).
4. Add the column to `files1/boe_schema.sql` (+ a migration), and to `report.py` if it should print.

**Add a Part IV section:** add it to `PART4_SECTIONS` (columns, in printed order) and `PART4_TITLES`; the prompt, mapper
and viewer pick it up.

**Change the AI model:** `EXECUTOR_MODEL` / `EVALUATOR_MODEL`; if the provider changes, change `model_for()` in
`extract_service.py` (pydantic-ai supports Azure OpenAI, Anthropic and others) and the price table in `cost.py`.
Re-validate accuracy on real bills.

**Move to Power Pages / Azure:** every `fetch('/api/…')` in the viewer is a seam: list/edit/delete → Dataverse Web API,
extract/progress/PDF pages/report → an Azure service running this same Python. Details in the project notes.

---

## 14. Known limitations

- Single-user, local: no authentication, jobs are in memory (lost on restart), one process.
- No database yet; bills are files.
- `check_header_consistency` (BE number repeated on every page) exists in `checks.py` but is **not** wired into
  `run_all_checks`.
- Sections outside Parts I–III are read by the model but cross-checked only by the text match.
- Only two form versions have been seen (2025 and 2026). A future version with renamed or new Part IV sections may need
  `PART4_TITLES` (in `app/sections.py`) and `PART4_SECTIONS` extended.
- The PDF highlight searches the page text, so scanned (image-only) PDFs would not highlight or text-match.
