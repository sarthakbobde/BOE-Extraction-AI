"""Runs the executor/evaluator pipeline on an uploaded PDF and returns a viewer-shaped document.

Reuses ../files2 (pipeline.py, checks.py, schemas.py) for the core extraction and cross-checks, and adds
extra agents for the sections the viewer displays (status, declarant, manifest, parties, Part IV/VI ...).
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import re
import shutil
import sys
import threading
from collections import defaultdict
from typing import Callable

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "files2"))

import pymupdf  # noqa: E402
from pydantic_ai import Agent, BinaryContent  # noqa: E402
from pydantic_ai.models.google import GoogleModel  # noqa: E402
from pydantic_ai.providers.google import GoogleProvider  # noqa: E402

import pipeline as core  # noqa: E402
from sections import part4_letters  # noqa: E402
from cost import CostMeter  # noqa: E402
from checks import run_all_checks  # noqa: E402
from to_viewer import build_doc  # noqa: E402
from viewer_schemas import (PART4_SECTIONS, InvoiceDetails, Part1Details, Part4Page, Part5Page,  # noqa: E402
                            Part6Page)

EXECUTOR_MODEL = os.getenv("EXECUTOR_MODEL", "gemini-3.8-flash")
EVALUATOR_MODEL = os.getenv("EVALUATOR_MODEL", "gemini-3.1-pro-preview")
CONCURRENCY = int(os.getenv("EXTRACT_CONCURRENCY", "12"))   # parallel Gemini calls
RENDER_DPI = int(os.getenv("RENDER_DPI", "150"))             # lower (e.g. 110) = faster, slightly less accurate
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads", ".cache")
ATTEMPTS = int(os.getenv("EXTRACT_ATTEMPTS", "4"))           # tries per page on temporary errors (429/5xx/timeouts)
MAX_PAGES = int(os.getenv("MAX_PAGES", "600"))      # largest page count accepted

DOUBT_RULE = ("\nConfidence: also fill `doubts` with ONLY the values you are not fully sure you read correctly (small or "
              "blurry print, ambiguous cell, possibly the wrong row or column). {how} Level 'medium' = some doubt, "
              "'low' = a guess. Leave `doubts` empty when you are sure of everything.")

EXTRA_PROMPTS = {
    "part1": core.COMMON + "This is Part I. Extract the header, ALL of A. STATUS (fields 1-16, flags are single letters "
                           "Y/N/T/F/P), B. DECLARANT (incl. AEO, UCR), D. MANIFEST (IGM no/date, INW date, GIGM no/date, "
                           "MAWB, HAWB, packages, gross weight), E. BOND DETAILS rows, F. PAYMENT rows, G. WH rows, "
                           "H. PROCESSING events (plus the OOC NO. and OOC DATE printed there) and J. CONTAINER rows. A section that is blank on the page gives an "
                           "empty list / null values. Events: list every row of H. PROCESSING DETAILS that has a date.",
    "inv_details": core.COMMON + "This is the first page of a Part II invoice. Extract section A (1.S.NO, 2.INVOICE NO & DT, "
                                 "3.PURCHASE ORDER NO & DT, 4.LC NO & DATE, 5.CONTRACT NO & DATE, 6.AD CODE), B (transacting "
                                 "parties incl. 5.AEO) and C (valuation). Join multi-line addresses with ', '. Split a "
                                 "combined 'number & date' cell into its number and its date.",
    "part4": core.COMMON + "This is a Part IV (additional details) page. Section LETTERS differ between form versions, so "
                           "identify each section by its printed TITLE. One list entry per printed DATA row; printed "
                           "column headers and the glossary are not data. Extract: (1) the SUPPORTING DOCUMENTS section "
                           "(printed 'L.' or 'M.') into supporting_docs, (2) the CONTAINER DETAILS section (printed 'M.' "
                           "or 'N.') into containers, and (3) for the sections below, ONLY those with at least one data "
                           "row, a section entry whose code is the key shown, with one 'cells' list per row, cells in "
                           "EXACTLY this column order (null for a blank cell):\n"
                           + "\n".join(f"  {k} (title: {t}): " + ", ".join(cols) for k, (t, cols) in PART4_SECTIONS.items())
                           + "\nSkip the INVOICE DETAILS section (invoice list). Read each row's cells from the image so "
                             "values stay in the right column. A page may contain only some sections or only the "
                             "headings with no rows: then return empty lists.",
    "part5": core.COMMON + "This is Part V (other compliances). Extract each section A-F and OOC No/Date only if it "
                           "has printed content; leave lists empty and values null for blank sections. One list entry "
                           "per printed line or row. Do not copy the printed section headings or glossary as content.",
    "part6": core.COMMON + "This is Part VI. Extract every 'Declaration for N/M' paragraph (text with whitespace "
                           "normalised) and the authorised signatory CHA name, date and place.",
}
EXTRA_PROMPTS["part1"] += DOUBT_RULE.format(how="`field` is the schema field path, e.g. 'status.kaccha', 'declarant.ucr', "
                                           "'manifest.igm_no', 'header.be_type', 'payments[0].amount', "
                                           "'events[1].time', 'ooc_no'.")
EXTRA_PROMPTS["inv_details"] += DOUBT_RULE.format(how="`field` is the attribute name, e.g. 'buyer', 'lc_no', 'svb_date'.")
EXTRA_PROMPTS["part4"] += DOUBT_RULE.format(how="`field` is '<section code>[<row number counting from 0 on this page>]."
                                                "<column number counting from 1>', e.g. 'licence[0].4'.")
EXTRA_OUTPUT = {"part1": Part1Details, "inv_details": InvoiceDetails, "part4": Part4Page, "part5": Part5Page,
                "part6": Part6Page}


class ExtractionError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def model_for(name: str, api_key: str) -> GoogleModel:
    return GoogleModel(name, provider=GoogleProvider(api_key=api_key))


def check_key(key: str) -> dict:
    """Validate a Gemini key by listing models (free, no tokens billed)."""
    if not key:
        return {"ok": False, "error": "Enter a key first."}
    try:
        from google import genai
        client = genai.Client(api_key=key)      # keep a reference: a temporary client is closed on GC mid-request
        next(iter(client.models.list()), None)
        return {"ok": True}
    except Exception as e:  # noqa: BLE001
        msg = str(e).replace(key, "***")
        if any(w in msg for w in ("API key", "API_KEY", "401", "403", "400", "INVALID_ARGUMENT", "PERMISSION")):
            return {"ok": False, "error": "This AI Key was rejected."}
        return {"ok": False, "error": "Could not verify the key: " + msg[:200]}


def classify_all(text: str) -> list[str]:
    """Core kind plus extra kinds for one page."""
    t = re.sub(r"\s+", " ", text)
    kinds = []
    core_kind = core.classify(text)
    if core_kind != "other":
        kinds.append(core_kind)
    if core_kind == "summary":
        kinds.append("part1")
    if core_kind == "invoice" and "BUYER'S NAME" in t:
        kinds.append("inv_details")
    if "PART - IV - ADDITIONAL DETAILS" in t:      # any Part IV page: section letters vary by form version
        kinds.append("part4")
    if "PART - V - OTHER COMPLIANCES" in t:
        kinds.append("part5")
    if "PART - VI - DECLARATION" in t:
        kinds.append("part6")
    return kinds


def _friendly(e: Exception, key: str) -> ExtractionError:
    msg = str(e).replace(key, "***") if key else str(e)
    status = getattr(e, "status_code", None)
    if status in (400, 401, 403) and ("API key" in msg or "API_KEY" in msg or status in (401, 403)):
        return ExtractionError("bad_key", "The AI Key was rejected. Please check it and try again.")
    if status == 404:
        return ExtractionError("bad_model", "The configured Gemini model is not available: " + msg[:300])
    if status == 429:
        return ExtractionError("rate_limit", "AI provider rate limit / quota reached. Try again later.")
    return ExtractionError("failed", msg[:500])


async def extract(pdf: bytes, filename: str, api_key: str, with_eval: bool,
                  progress: Callable[[int, int, str, dict], None]) -> dict:
    try:
        d = pymupdf.open(stream=pdf, filetype="pdf")
    except Exception:
        raise ExtractionError("bad_pdf", "That file could not be opened as a PDF.")
    if len(d) > MAX_PAGES:
        raise ExtractionError("too_big", f"PDF has {len(d)} pages; the limit is {MAX_PAGES}.")
    # Read text for every page (cheap), but render page images only for pages that will be sent to the model:
    # large PDFs are mostly irrelevant pages, and 150-dpi PNGs of all of them would exhaust memory.
    progress(0, 0, f"Scanning {len(d)} pages", {})
    texts = [p.get_text() for p in d]
    kinds = {i + 1: classify_all(t) for i, t in enumerate(texts)}
    if not any("summary" in k for k in kinds.values()):
        raise ExtractionError("not_boe", "This does not look like an Indian Bill of Entry (no 'PART - I - BILL OF "
                                         "ENTRY SUMMARY' page found).")
    pages = [core.Page(i + 1, texts[i], b"") for i in range(len(texts))]     # images are rendered on demand
    page_map = {p.number: p for p in pages}
    doc_lock = threading.Lock()                       # PyMuPDF documents are not thread-safe

    def render(pn: int) -> bytes:
        with doc_lock:
            return d[pn - 1].get_pixmap(dpi=RENDER_DPI).tobytes("png")

    exec_model = model_for(EXECUTOR_MODEL, api_key)
    sem = asyncio.Semaphore(CONCURRENCY)
    core_agents = {k: core.make_executor(k, exec_model) for k in core.OUTPUT}
    extra_agents = {k: Agent(exec_model, output_type=EXTRA_OUTPUT[k], instructions=EXTRA_PROMPTS[k], retries=2,
                             model_settings=core.SETTINGS) for k in EXTRA_OUTPUT}

    jobs = [(pn, k) for pn, ks in kinds.items() for k in ks]
    total = len(jobs) + (len({pn for pn, k in jobs if k in core.OUTPUT}) if with_eval else 0)
    done = 0
    meter = CostMeter(label=filename[:30])
    print(f"[extract] {filename}: {len(pages)} pages, {len(jobs)} extraction calls"
          f"{' + evaluator' if with_eval else ''}  ({EXECUTOR_MODEL}{' / ' + EVALUATOR_MODEL if with_eval else ''})",
          flush=True)

    def tick(msg: str):
        nonlocal done
        done += 1
        progress(done, total, msg, meter.snapshot())

    progress(0, total, "Reading pages", meter.snapshot())

    # --- resume cache: every finished page is saved, so a failed/interrupted run restarts where it stopped
    digest = hashlib.sha256(pdf + f"{EXECUTOR_MODEL}|{RENDER_DPI}".encode()).hexdigest()[:20]
    cdir = os.path.join(CACHE_DIR, digest)
    os.makedirs(cdir, exist_ok=True)
    out_cls = {**core.OUTPUT, **EXTRA_OUTPUT}
    remaining = defaultdict(int)                      # page -> kinds still to run (frees its image when 0)
    for pn, k in jobs:
        remaining[pn] += 1
    keep_png = {pn for pn, k in jobs if with_eval and k in core.OUTPUT}    # evaluator re-reads these images
    png_locks = {pn: asyncio.Lock() for pn in remaining}
    cached_n = 0

    async def get_png(pn: int) -> bytes:
        async with png_locks[pn]:
            pg = page_map[pn]
            if not pg.png:
                pg.png = await asyncio.to_thread(render, pn)
            return pg.png

    def release(pn: int):
        remaining[pn] -= 1
        if remaining[pn] <= 0 and pn not in keep_png:
            page_map[pn].png = b""

    async def call_with_retry(run):
        for attempt in range(1, ATTEMPTS + 1):
            try:
                return await run()
            except Exception as e:  # noqa: BLE001
                status = getattr(e, "status_code", None)
                temporary = status in (429, 500, 502, 503, 504) or isinstance(e, (TimeoutError, ConnectionError))
                if not temporary or attempt == ATTEMPTS:
                    raise
                await asyncio.sleep(min(30, 2 ** attempt) + (hash((id(e), attempt)) % 100) / 100)

    async def one(pn: int, kind: str):
        nonlocal cached_n
        cf = os.path.join(cdir, f"p{pn}_{kind}.json")
        if os.path.exists(cf):
            try:
                out = out_cls[kind].model_validate_json(open(cf, encoding="utf-8").read())
                cached_n += 1
                if pn in keep_png:
                    await get_png(pn)                  # the evaluator still needs this page's image
                release(pn)
                tick(f"Page {pn} ({kind}) restored from earlier run")
                return pn, kind, out
            except Exception:  # noqa: BLE001
                pass                                   # unreadable cache entry: just redo the page
        async with sem:
            pg = page_map[pn]
            content = [f"PAGE TEXT LAYER:\n{pg.text}", BinaryContent(await get_png(pn), media_type="image/png")]
            if kind in core_agents:
                res = await call_with_retry(lambda: core_agents[kind].run(content, deps=core.PageCtx(pg)))
            else:
                res = await call_with_retry(lambda: extra_agents[kind].run(content))
        meter.add(f"p{pn} {kind}", EXECUTOR_MODEL, res.usage() if callable(res.usage) else res.usage)
        with open(cf, "w", encoding="utf-8") as f:
            f.write(res.output.model_dump_json())
        release(pn)
        tick(f"Extracted page {pn} ({kind})")
        return pn, kind, res.output

    try:
        async with asyncio.TaskGroup() as tg:          # first hard failure cancels the rest (finished pages stay cached)
            tasks = [tg.create_task(one(pn, k)) for pn, k in jobs]
        results = [t.result() for t in tasks]
    except* Exception as eg:  # noqa: BLE001
        print(meter.summary_line().replace("DONE", "FAILED") + "  (finished pages are cached; re-upload to resume)",
              flush=True)
        raise _friendly(eg.exceptions[0], api_key)
    d.close()

    by_page = {pn: (k, out) for pn, k, out in results if k in core.OUTPUT}
    # a page can only be one core kind, so by_page is keyed by page number
    ex = core.assemble(by_page)
    issues = run_all_checks(ex)
    verdicts = None
    if with_eval:
        try:
            def on_usage(stage, usage):
                meter.add(stage, EVALUATOR_MODEL, usage)
                tick(f"Evaluated {stage.split()[-1]}")

            verdicts = await core.run_evaluator(ex, page_map, model_for(EVALUATOR_MODEL, api_key), sem, on_usage)
        except Exception as e:  # noqa: BLE001
            raise _friendly(e, api_key)
    rows = core.score_fields(ex, page_map, issues, verdicts)

    extras = defaultdict(list)
    for pn, k, out in sorted(results, key=lambda r: r[0]):
        if k in EXTRA_OUTPUT:
            extras[k].append((pn, out))

    review = [r for r in rows if r["status"] == "needs_review"]
    quality = {
        "fields": len(rows), "needsReview": len(review), "failedChecks": len(issues), "evaluator": with_eval,
        "pages": len(pages), "pagesExtracted": len({pn for pn, _ in jobs}),
        "review": [{"path": r["path"], "value": r["value"], "page": r["page"], "reasons": r["reasons"]}
                   for r in review[:60]],
        "checks": [{"check": i.check, "message": i.message} for i in issues[:60]],
    }
    print(meter.summary_line() + (f"  ({cached_n} pages restored from cache)" if cached_n else ""), flush=True)
    shutil.rmtree(cdir, ignore_errors=True)         # extracted data is now saved as the bill; drop the resume cache
    section_pages = {"I": sorted(pn for pn, ks in kinds.items() if "summary" in ks or "part1" in ks),
                     "IV": sorted(pn for pn, ks in kinds.items() if "part4" in ks),
                     "V": sorted(pn for pn, ks in kinds.items() if "part5" in ks),
                     "VI": sorted(pn for pn, ks in kinds.items() if "part6" in ks)}
    out = build_doc(ex, extras, quality, filename, field_rows=rows, full_text="\n".join(pg.text for pg in pages),
                     section_pages=section_pages, page_count=len(pages))
    out["sectionLetters"] = part4_letters([pg.text for pg in pages])     # printed Part IV letters (vary by form version)
    return out
