# How the AI Decides — Extraction, Checking and Scoring

This document explains *why a value ends up on screen and why it gets the confidence it gets*. For the code structure
read [`01-technical-overview.md`](01-technical-overview.md).

---

## 0. The idea in one paragraph

**The AI only reads. Code decides how much to trust what it read.**
Gemini looks at each page and fills a strict form (a schema). It is never asked to calculate, round or "fix" anything.
Then independent, mostly non-AI signals test every value: *Is it literally on the page? Do the numbers add up? (Optionally:
does a second model agree?)* Each field gets a score from those signals. Fields that look doubtful are highlighted for a
human, and a human's edit always wins.

```
 PDF page ──► [code] what kind of page?
          ──► [AI]   read it into a schema   ◄── retry if a value isn't on the page
          ──► [code] cross-checks across the whole bill
          ──► [AI, optional] second model audits each field against the image
          ──► [code] score per field  ──► viewer (green / amber / red)  ──► [human] edit
```

---

## 1. Who does what

| Decision | Made by | How |
|---|---|---|
| What kind of page is this? | **Code** | text rules on the page's text layer |
| What does each cell say? | **AI** (Gemini Flash) | page image + text layer → schema |
| Is the value really on the page? | **Code** | number/text search, forces an AI retry |
| Do the numbers add up? | **Code** | ~15 arithmetic/consistency checks |
| Does a second reader agree? | **AI** (Gemini Pro), optional | per-field "supported?" verdict |
| How confident are we? | **Code** | fixed penalty formula / text-match rules |
| Which Part IV letters does this form use? | **Code** | read the printed headings |
| Which PDF page and spot hold this value? | **Code** | page map + text search in the PDF |
| What is finally true? | **Human** | edits override everything |

---

## 2. Step 1 — Deciding what each page is (code)

The page's text layer is whitespace-normalised and tested for its part title:

| Text found | Page kind(s) |
|---|---|
| `PART - I - BILL OF ENTRY SUMMARY` | summary **and** part1 |
| `PART - II - INVOICE & VALUATION` | invoice (+ `inv_details` if it contains `BUYER'S NAME`, i.e. the first page of an invoice) |
| `PART - III - DUTIES` | duties |
| `PART - IV - ADDITIONAL DETAILS` | part4 (every such page) |
| `PART - V - OTHER COMPLIANCES` | part5 |
| `PART - VI - DECLARATION` | part6 |

Why code and not AI: it is free, instant and deterministic. A page can carry several kinds, each becoming its own AI call.
If no "Part I summary" page exists, the upload is rejected as *not a Bill of Entry*.

---

## 3. Step 2 — How the AI reads a page

### What the model receives
For every (page, kind): the page's **text layer** *and* a **150-dpi image** of the page, plus kind-specific instructions.

- The **image** tells it the *layout* (which cell is under which heading — the text layer's reading order is scrambled).
- The **text layer** lets it copy digits exactly (no OCR misreads).

### The rules every prompt contains
- Copy values exactly as printed. **Never compute, round, convert or fix numbers.**
- A blank cell is `null`. A printed `0` is `"0"`.
- Columns are easy to confuse (BCD / SWS / IGST / CAIDC) — follow the printed heading strictly.
- Process every row/item; do not skip or merge repeated identical rows.
- Temperature is 0 (no randomness).

### The schema is the contract
The model must answer in a pydantic schema; a malformed answer is retried (up to 2 times).

- Values are **printed strings** (`"14482.490000"`), converted to numbers only by code, so nothing drifts.
- The schemas carry the *printed field numbers* (e.g. "11.UPI"), which doubles as instruction.
- **Part III** is described as the form prints it: per item, A (30 fields) plus three matrices (B, C, C-A) whose
  **columns** are duties and whose **rows** are *Notn No., Notn SNo., Rate, Amount, Duty Fg*. The model returns one entry per
  column that has at least one non-blank cell.
- **Part IV** sections each have a fixed column order; the model returns cells in that order, matched by section **title**
  (letters differ between form versions).
- Optional second pass for tables with many columns is *not* used; one call reads a whole page.

### Why one call per page and kind
Smaller, focused prompts are more accurate than one giant prompt, failures are isolated (one page can retry alone), and
calls run 12 at a time. The cost is visible per call.

---

## 4. Step 3 — The evidence gate (forces the AI to stay honest)

For the core sections (Part I summary, Part II invoice pages, Part III duties), each extracted value is searched for in the
**same page's text layer**:

- **Numbers:** every number in the page text is parsed into an exact `Decimal`; the value passes if its `Decimal` is in that
  set (so `1,315.10` = `1315.1` = `1315.100000`).
- **Text:** compared lower-cased with whitespace collapsed; it must appear as a substring.

If any value fails, the model is *told which ones* (up to 25) and must re-read the image and text and correct them — this is
a retry loop of at most 2. A value that still isn't found stays, and is penalised in scoring (§7).

Why it works: a hallucinated or mis-copied number almost never exists elsewhere on the page.
What it cannot catch: a *real* number from the wrong cell (right digits, wrong row/column). That is what §5 and §6 are for.

---

## 5. Step 4 — Cross-checks (pure code, whole bill)

After all pages are read, arithmetic and consistency checks run. Each failure **names the exact fields involved**.
Tolerances exist because the PDF prints rounded values (items to 1 decimal, summary to whole rupees).

| Check | Rule | Tolerance |
|---|---|---|
| `item_arith` | unit price × quantity = amount | 0.011 |
| `invoice_total` | items add up to the invoice value | 0.05 |
| `count` | header item/invoice counts = what was found; Part II items = Part III items | exact |
| `summary_invoice` | Part I invoice amount = Part II invoice value | 0.005 |
| `valuation` | assessable value = (invoice + misc) × rate + insurance + freight × freight-rate | max(1, 0.001 %) |
| `duty_bcd` | BCD = rate % × assessable value (when BCD > 0) | 0.1 |
| `duty_sws` | SWS = 10 % of the notional BCD | 0.15 |
| `duty_igst` | IGST = rate % × (assessable value + notional BCD + SWS) | 0.4 |
| `duty_total` | item total = BCD + SWS + IGST (or that plus any other duty amounts printed) | 0.2 |
| `duty_rollup` | item BCD / SWS / IGST add up to the Part I figure | 0.06 per item + 1 |
| `duty_summary` | all duty heads add up to total duty; total duty + interest + penalty + fine = total amount | 1 |
| `challan` | total duty = challan amount | 1 |
| `av_rollup` | item assessable values add up to the Part I total | 0.02 per item + 1 |
| `av_ratio` / `av_link` | within an invoice every item's AV ÷ amount is the same (median ± 0.6 %), and every duty item links to a Part II item | median-based |

Notes on the design:
- The "notional BCD" (rate × value) is used even when BCD payable is 0, because exemptions print the foregone duty
  elsewhere — so an exempted item doesn't fail.
- A check with no specific field (e.g. "Part II has 24 items, Part III has 23") becomes a **document-level** finding with
  score 0, shown in the failed-checks list.
- `check_header_consistency` (BE number repeated on each page) exists in `checks.py` but is **not currently run**.

---

## 6. Step 5 — Optional second-model audit

Switch on "Double-check with a second model" and, per Part I–III page, a *different, stronger* model (Gemini Pro) gets the
page image plus a list of claims like `duty_items[2].bcd_amount = 1315.1`. It is asked, as a strict auditor, whether the
image shows **exactly that value in the correct row and column**, and returns `supported: true/false` per claim.

- It catches the "right number, wrong cell" mistakes the evidence gate cannot.
- Costs roughly as much again as the extraction and takes longer, so it is **off by default**.
- A claim the auditor didn't answer is treated as a (smaller) negative.

---

## 7. Step 6 — The score for Parts I–III (the pipeline score)

Computed in `files2/pipeline.py → score_fields`. Every field starts at **1.0** (100 %), then:

| Signal | Penalty | Applied |
|---|---|---|
| Value not found on the page after retries | −0.6 | once |
| Field is named by **any** failed cross-check | −0.5 | **once**, however many checks name it |
| Second model says "not supported" (if on) | −0.4 | once |
| Second model gave no answer (if on) | −0.2 | once |

| The model itself marked the value `medium` / `low` confidence | cap at 0.7 / 0.4 | once (the score can only go down) |

Floor 0. **Below 0.8 = "needs review".** The viewer shows the score as a word, not a percentage:
**High** (0.8 and above), **Medium** (0.5 to under 0.8), **Low** (under 0.5).

Every value this formula can produce:

| Score | Cause | Shown |
|---|---|---|
| 100 % | nothing wrong | green |
| 80 % | second model gave no answer | green |
| 60 % | second model disagrees | amber |
| 50 % | named by a failed check | amber |
| 40 % | not found on the page | red |
| 30 % | failed check + no second-model answer | red |
| 10 % | failed check + second model disagrees | red |
| 0 % | not found + failed check (−1.1), or not found + second model disagrees (−1.0) | red |

**Worked example (a real test bill, "FAKE_BOE_test", Part I):**
- *IGST 63,407* → 50 %: `duty_rollup` — the items' IGST adds up to 63,424.70, allowed gap for 3 items is 1.18, actual
  gap 17.70.
- *Total amount 99,216* → 50 %: `duty_summary` — total duty 98,316 + interest/penalty/fine 0 ≠ 99,216 (gap 900).
- *Total duty, BCD, SWS* → 100 %: every check they appear in passed, and each was found on the page.

Why the penalty is "once": a field implicated by three checks is not three times as wrong; it needs the same single
look from a human.

---

## 8. The score for everything else (text match and the model's own rating)

Status, parties, declarant extras, Part IV, V and VI are read by the model but have no arithmetic to check. They get a
simpler, weaker test: **does the value appear in the PDF's text?** (whole-document search).

| Value | Found | Not found |
|---|---|---|
| Number | 90 % | 45 % |
| Date (matched in any printed format: `14/02/2026`, `14-FEB-26` …) | 90 % | 45 % |
| Text, matched with spaces/line-breaks removed (≥ 6 characters) | 90 % | — |
| Text, word by word | 90 % if every word is present | `40 % + 50 % × share of words found` |

- **Capped at 90 %** on purpose: a text match is weaker than a checked field, and should look weaker.
- **Too generic to text-match** — zeros, whole numbers under 10, one-letter flags (`N`, `Y`), and similar. These are
  searched for nowhere, because they appear all over the PDF. Instead they take **the model's own rating**: **High** (0.9)
  unless the model listed the value in its `doubts` (see below).
- **No rating at all**: blank values (nothing was extracted) and structural labels / serial keys (table column
  headings, `sno`).
- It checks existence *somewhere in the document*, not the right cell — so it is deliberately lenient.

**The model's own confidence.** Every core value (`Val`/`Ev`) carries `conf: high | medium | low` (default `high`).
For the other sections the model returns a `doubts` list naming only the values it is not sure about (Part I, the
invoice details and Part IV cells). A doubt never raises a score: it caps it at Medium (0.7) or Low (0.4), whichever
signal is lower wins. Self-reported confidence is optimistic, so it can lift a generic value to High but can never
override a failed check or a missing value. Part V/VI text and Part IV supporting documents / containers have no
doubts list yet; they are rated by text match only.

---

## 9. Putting it together in the viewer

- Each field's score lives in `doc.conf["<path>"] = {s, b, r}` (`s` score, `b` basis `checked|text|edited`, `r` reasons).
- Pipeline paths (like `duty_items[3].item_duty[2].amount`) are translated to viewer paths
  (`invoices.0.duties.4.igstAmount`) in `to_viewer.map_pipeline_rows`.
- If one viewer field has several pipeline sources, the **worst** score is kept. Pipeline scores **override** text-match
  scores for the same field.
- **Labels and colours:** **High** (green, ≥ 80 %), **Medium** (amber, 50–80 %), **Low** (red, < 50 %), blue = edited.
  Blank values show no label. Bills read before ratings existed lack `doc.rated`; their unrated values show a muted
  "Medium" until the bill is uploaded again.
- **Edited** = 100 % "edited" (a human verified it). *Revert* restores the stored original value and its original score;
  editing a value back to the original is treated as a revert.
- **Counters:**
  - The *green* "Extracted from…" banner is the pipeline's own tally (Parts I–III only, from the last run).
  - The *amber* review bar counts every field rated Medium or Low (below 80 %) from all sources (live — it drops as you edit).
  - Left-menu badges and the list's "N to review" use the same live count. **Review next** walks the low fields.

---

## 10. Other decisions the system makes

| Decision | How |
|---|---|
| Part IV section letters | read from the PDF's printed headings and matched by **title** (2025 form: supporting documents = `L.`; 2026 form: `M.` and an extra "G. Scheme notification") |
| Which PDF page holds a field | **page map** built at extraction: section pages, plus the page of every item and duty row |
| Where to highlight | search candidate pages for the value's *printed variants* (numbers as `x`, `x.00`, `x,xxx.xx`; dates as `dd/mm/yyyy`, `dd-MON-yy`; text as full / first words / longest word); zeros, tiny numbers and one-letter flags are not highlighted (they'd match everywhere) |
| Invoice grouping | invoice pages are grouped by serial number; items sorted by item number |
| Containers | merged from Part I and Part IV, de-duplicated by container number |
| Re-uploading a bill | replaces the stored bill with the same (port, BE number, date) |
| Dates | normalised to `dd-Mon-yyyy`; numbers to floats; whitespace collapsed |

---

## 11. What the score does — and does not — mean

It **is**: a measure of how much independent evidence supports a value (found on the page, consistent with the bill's own
arithmetic, optionally confirmed by a second reader).

It is **not**:
- a probability of being right, or proof. **100 % means nothing we tested disagreed.** Two wrong numbers that still add up
  would pass.
- precise about *which* field is wrong: a failed check lowers every field it names, including correct ones.
- able to see **omissions**: a blank is "not scored", so a value the model missed entirely is invisible to the score.
- strict for non-core sections: the text match is existence-only and tops out at 90 %.
- proof for generic values: a flag or zero rated High means the *AI* was confident, not that anything verified it.

Lessons from real runs (all fixed, and a good guide to the failure modes):
- A label we added (a *table column heading*) was being scored and flagged — headings are now ignored.
- `MEDUEC571373` looked missing because the PDF wraps it as `MEDUEC5713` + `73` — matching now ignores line breaks.
- "Total amount = total duty" wrongly flagged bills with interest/penalty — the rule now includes them.
- A hand-typed reference bill had *invented* values (a payment date, zeros) that the PDF leaves blank — the model was right.
- The report was rounding numbers to 6 digits — fixed (and found by a test, not by eye).

---

## 12. Evidence from real extractions

| Bill | Pages / calls | Cost | Result |
|---|---|---|---|
| BE 3604502 | 6 / 8 | $0.07 | Parts I–III matched the page image cell by cell (every status flag, 19 duty cells, manifest, 28 item fields, B/C duty matrices) |
| BE 7526371 (Delhi) | 19 / 21 | $0.34 | vs a hand-checked reference: **all 192** Part III values matched; remaining differences were the reference's own fill-ins; 0 failed checks, nothing below 80 % |
| BE 7796810 | 9 / 11 | $0.21 | extracted without errors; 0 flagged |

Extraction was done with the fast model only (second-model audit off). Larger or noisier bills should still be spot-checked
on the amber/red fields.

---

## 13. Cost and speed levers

- Output tokens (including the model's hidden "thinking") dominate cost; Part III pages are the most expensive.
- Ways to reduce cost: lower the model's thinking level for extraction, keep the audit off (or audit only flagged pages),
  cache per-page results, read digitally-generated tables in code and use the AI only as a fallback.
- Typical cost today: ≈ $0.016–0.02 per call; a 51-page bill is estimated at ≈ $1.0–1.4 without the audit.

---

## 14. Where to tune the decisions

| What | Where |
|---|---|
| Model names / retries / temperature | `EXECUTOR_MODEL`, `EVALUATOR_MODEL`; `retries=2`, `ModelSettings(temperature=0)` in `files2/pipeline.py` |
| Prompts | `files2/pipeline.py → PROMPTS`, `app/extract_service.py → EXTRA_PROMPTS` |
| Schemas (what is asked) | `files2/schemas.py`, `app/viewer_schemas.py` |
| Check rules and tolerances | `files2/checks.py` |
| Penalties and the 0.8 review threshold | `files2/pipeline.py → score_fields`, `REVIEW_THRESHOLD` |
| Text-match scores, the model rating (`MODEL_HIGH`, `MODEL_CAP`) and skip rules | `app/confidence.py`, `files2/pipeline.py → MODEL_CAP` |
| Doubt-to-viewer-path mapping | `app/to_viewer.py → part1_doubt_path`, `INV_DOUBT`, `build_doc` |
| Medium / Low thresholds in the UI | `LOW_BELOW`, `VLOW_BELOW`, `confLevel()` in `app/boe_viewer.html` |
| Pipeline-path → viewer-path mapping | `app/to_viewer.py → map_pipeline_rows` (+ the `*_MAP` tables) |
| Page classification | `app/extract_service.py → classify_all` |

---

## 15. Glossary

- **Evidence gate** — the check that an extracted value exists in the page's text; failures force a re-read.
- **Cross-check** — an arithmetic/consistency rule across fields; failures name the fields involved.
- **Evaluator / second-model audit** — an independent model's per-field "supported?" verdict (optional).
- **Pipeline score** — the 0–100 % score for Part I–III fields built from the three signals above.
- **Text match** — the weaker existence-only score for the other sections (max 90 %).
- **High / Medium / Low** — how the score is shown: 80 %+, 50–80 %, under 50 %.
- **Doubts** — values the model itself listed as not fully sure about; they lower the rating.
- **Needs review** — a score below 80 % (Medium or Low).
- **Edited** — a human-verified value (100 %).
- **Path** — the dotted address of a value in the bill document, e.g. `invoices.0.valuation.freight`.
- **Page map** — which PDF page each section / item / duty row came from; powers the jump-and-highlight.
