"""Executor / Evaluator pipeline for Indian Bill of Entry PDFs.

    PDF -> classify pages (regex on text layer)
        -> EXECUTOR (Gemini, page image + text layer) per page  --retry--> evidence validator
        -> assemble BoeExtraction
        -> deterministic cross-checks (checks.py)
        -> EVALUATOR (second Gemini call, independent prompt/model) re-reads each page
        -> per-field score -> auto-accept / needs_review

Usage:
    export GEMINI_API_KEY=...
    python pipeline.py path/to/BE.pdf [--max-pages 12] [--no-eval] [--out result.json]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass

import pymupdf  # PyMuPDF
from pydantic import BaseModel
from pydantic_ai import Agent, BinaryContent, ModelRetry, RunContext
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.settings import ModelSettings

from checks import Issue, evidence_issues, run_all_checks
from schemas import BoeExtraction, DutyPage, InvoicePage, SummaryPage, flatten

EXECUTOR_MODEL = os.getenv("EXECUTOR_MODEL", "gemini-3.8-flash")
EVALUATOR_MODEL = os.getenv("EVALUATOR_MODEL", "gemini-3.1-pro-preview")   # different model = fewer shared blind spots
REVIEW_THRESHOLD = 0.8
SETTINGS = ModelSettings(temperature=0.0)


# --------------------------------------------------------------------------- pages
@dataclass
class Page:
    number: int          # 1-based
    text: str
    png: bytes


def load_pages(path: str, dpi: int = 150) -> list[Page]:
    doc = pymupdf.open(path)
    return [Page(i + 1, p.get_text(), p.get_pixmap(dpi=dpi).tobytes("png")) for i, p in enumerate(doc)]


def classify(text: str) -> str:
    t = re.sub(r"\s+", " ", text)          # title has irregular spacing ("PART - I  -  BILL ...")
    if "PART - I - BILL OF ENTRY SUMMARY" in t:
        return "summary"
    if "PART - II - INVOICE & VALUATION" in t:
        return "invoice"
    if "PART - III - DUTIES" in t:
        return "duties"
    return "other"          # Part IV-VI: not extracted in this first test


# --------------------------------------------------------------------------- agents
def make_model(name: str) -> GoogleModel:
    return GoogleModel(name, provider=GoogleProvider(api_key=os.environ["GEMINI_API_KEY"]))


COMMON = """You extract data from ONE page of an Indian Customs Bill of Entry (digitally generated PDF).
You get the page IMAGE and the raw TEXT LAYER (column order in the text layer is scrambled; use the image for
layout, the text layer to copy digits exactly).
Rules:
- Copy values exactly as printed. Never compute, round, convert, or fix numbers.
- A blank cell is null. A printed 0 is "0".
- Columns are easy to confuse (BCD / SWS / IGST / CAIDC). Follow the column header strictly.
- Process every row/item on the page; do not skip or merge repeated identical rows.
"""

PROMPTS = {
    "summary": COMMON + "This is Part I (summary). Exchange rate may be 'per 100 units' (e.g. 100 JPY=58.65INR).",
    "invoice": COMMON + "This is Part II. First pages of an invoice have sections A-D plus items; continuation pages "
                        "have only A and the item table (set header=null). 14.Cur may show two currencies: "
                        "invoice currency then freight currency.",
    "duties": COMMON + "This is Part III. Each block is one item. Read only the B. ITEM DUTY table for rate/amount.",
}
OUTPUT = {"summary": SummaryPage, "invoice": InvoicePage, "duties": DutyPage}


@dataclass
class PageCtx:
    page: Page


def make_executor(kind: str, model) -> Agent:
    agent = Agent(model, output_type=OUTPUT[kind], deps_type=PageCtx, instructions=PROMPTS[kind],
                  retries=2, model_settings=SETTINGS)

    @agent.output_validator
    def evidence_gate(ctx: RunContext[PageCtx], out):
        bad = evidence_issues(out, ctx.deps.page.text)
        if bad:
            lines = "\n".join(f"- {i.paths[0]}: {i.message}" for i in bad[:25])
            raise ModelRetry("These values do not appear on the page. Re-read the page image and the text layer "
                             f"and correct them (or use null if blank):\n{lines}")
        return out

    return agent


class FieldVerdict(BaseModel):
    path: str
    supported: bool
    reason: str = ""


class EvalReport(BaseModel):
    verdicts: list[FieldVerdict]


def make_evaluator(model) -> Agent:
    return Agent(model, output_type=EvalReport, model_settings=SETTINGS, retries=2, instructions=(
        "You are a strict auditor. You get a page image and a list of 'path = value' claims extracted from it. "
        "For EACH path decide whether the page image shows exactly that value in the correct row and column. "
        "Pay attention to the row (item number) and the column header. Return one verdict per path; "
        "supported=false when the value is wrong, in the wrong column/row, or not visible."))


# --------------------------------------------------------------------------- run
async def run_executors(pages: list[Page], executor_model, sem) -> tuple[dict, dict]:
    agents = {k: make_executor(k, executor_model) for k in OUTPUT}

    async def one(pg: Page):
        kind = classify(pg.text)
        if kind == "other":
            return pg, kind, None
        async with sem:
            res = await agents[kind].run(
                [f"PAGE TEXT LAYER:\n{pg.text}", BinaryContent(pg.png, media_type="image/png")],
                deps=PageCtx(pg))
        return pg, kind, res.output

    results = await asyncio.gather(*[one(p) for p in pages])
    return {pg.number: (kind, out) for pg, kind, out in results}, {pg.number: pg for pg in pages}


def assemble(by_page: dict) -> BoeExtraction:
    summary, inv_pages, duty_items, page_of = None, [], [], {}
    for n in sorted(by_page):
        kind, out = by_page[n]
        if kind == "summary":
            summary = out; page_of["summary"] = n
        elif kind == "invoice":
            page_of[f"invoice_pages[{len(inv_pages)}]"] = n; inv_pages.append(out)
        elif kind == "duties":
            for it in out.items:
                page_of[f"duty_items[{len(duty_items)}]"] = n; duty_items.append(it)
    if summary is None:
        raise RuntimeError("No Part I summary page found")
    return BoeExtraction(summary=summary, invoice_pages=inv_pages, duty_items=duty_items, page_of=page_of)


def page_for(path: str, page_of: dict[str, int]) -> int | None:
    root = path.split(".")[0]
    return page_of.get(root)


async def run_evaluator(ex: BoeExtraction, pages: dict[int, Page], model, sem,
                        on_usage=None) -> dict[str, FieldVerdict]:
    agent = make_evaluator(model)
    by_page = defaultdict(dict)
    for path, ev in flatten(ex).items():
        pn = page_for(path, ex.page_of)
        if pn:
            by_page[pn][path] = ev.value

    async def one(pn: int, claims: dict[str, str]):
        listing = "\n".join(f"{p} = {v}" for p, v in claims.items())
        async with sem:
            res = await agent.run([f"Claims:\n{listing}", BinaryContent(pages[pn].png, media_type="image/png")])
        if on_usage:
            on_usage(f"evaluator p{pn}", res.usage() if callable(res.usage) else res.usage)
        return res.output.verdicts

    out = {}
    for verdicts in await asyncio.gather(*[one(pn, c) for pn, c in by_page.items()]):
        out.update({v.path: v for v in verdicts})
    return out


# --------------------------------------------------------------------------- scoring / routing
def score_fields(ex: BoeExtraction, pages: dict[int, Page], issues: list[Issue],
                 verdicts: dict[str, FieldVerdict] | None) -> list[dict]:
    ev_bad = set()
    for prefix_root in {p.split(".")[0] for p in flatten(ex)}:
        pn = ex.page_of.get(prefix_root)
        if pn:
            sub = ex.summary if prefix_root == "summary" else (
                ex.invoice_pages[int(prefix_root.split("[")[1][:-1])] if prefix_root.startswith("invoice_pages")
                else ex.duty_items[int(prefix_root.split("[")[1][:-1])])
            ev_bad |= {i.paths[0] for i in evidence_issues(sub, pages[pn].text, prefix_root)}
    failed = defaultdict(list)
    for i in issues:
        for p in i.paths:
            failed[p].append(f"{i.check}: {i.message}")

    rows = []
    for path, ev in flatten(ex).items():
        score, reasons = 1.0, []
        if path in ev_bad:
            score -= 0.6; reasons.append("value not found in page text")
        if path in failed:
            score -= 0.5; reasons += failed[path]
        if verdicts is not None:
            v = verdicts.get(path)
            if v is None:
                score -= 0.2; reasons.append("evaluator gave no verdict")
            elif not v.supported:
                score -= 0.4; reasons.append(f"evaluator: {v.reason or 'not supported'}")
        rows.append({"path": path, "value": ev.value, "page": page_for(path, ex.page_of),
                     "score": round(max(score, 0.0), 2), "reasons": reasons,
                     "status": "needs_review" if score < REVIEW_THRESHOLD else "auto_accepted"})
    # checks that couldn't point to a field still need a human
    for i in issues:
        if not i.paths:
            rows.append({"path": "(document)", "value": "", "page": None, "score": 0.0,
                         "reasons": [f"{i.check}: {i.message}"], "status": "needs_review"})
    return rows


async def main(args):
    pages = load_pages(args.pdf)[: args.max_pages]
    sem = asyncio.Semaphore(4)
    by_page, page_map = await run_executors(pages, make_model(EXECUTOR_MODEL), sem)
    ex = assemble(by_page)
    issues = run_all_checks(ex)
    verdicts = None if args.no_eval else await run_evaluator(ex, page_map, make_model(EVALUATOR_MODEL), sem)
    rows = score_fields(ex, page_map, issues, verdicts)

    review = [r for r in rows if r["status"] == "needs_review"]
    print(f"{len(rows)} fields, {len(review)} need review, {len(issues)} failed checks")
    for r in review:
        print(f"  p{r['page']}  {r['path']} = {r['value']!r}  ({r['score']})  <- {'; '.join(r['reasons'])}")
    json.dump({"extraction": ex.model_dump(), "issues": [i.__dict__ for i in issues], "fields": rows},
              open(args.out, "w"), indent=2)
    print("wrote", args.out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--max-pages", type=int, default=999)
    ap.add_argument("--no-eval", action="store_true")
    ap.add_argument("--out", default="result.json")
    asyncio.run(main(ap.parse_args()))
