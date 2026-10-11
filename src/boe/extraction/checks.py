"""Deterministic validators. No LLM involved. Everything uses Decimal.

Each check returns Issues that name the exact field paths involved, so the review UI
can highlight only those fields.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from statistics import median

from boe.extraction.schemas import BoeExtraction, Ev, flatten

ZERO = Decimal(0)
_NUM = re.compile(r"(?<![\w.])-?(?:\d[\d,]*\.?\d*|\.\d+)")


@dataclass
class Issue:
    check: str
    message: str
    paths: list[str]


def D(s: str | None) -> Decimal | None:
    if s is None:
        return None
    s = s.strip().replace(",", "").rstrip("%").strip()
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def dv(ev: Ev | None, default: Decimal | None = None) -> Decimal | None:
    """Decimal value of an Ev; blank (None) -> default."""
    if ev is None:
        return default
    return D(ev.value)


def close(a: Decimal, b: Decimal, tol: Decimal) -> bool:
    return abs(a - b) <= tol


# ------------------------------------------------------------------ evidence
def numbers_on_page(text: str) -> set[Decimal]:
    out = set()
    for m in _NUM.findall(text):
        d = D(m)
        if d is not None:
            out.add(d)
    return out


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def evidence_issues(model, page_text: str, prefix: str = "") -> list[Issue]:
    """Value of every Ev must literally exist in the page text layer."""
    nums, norm_text = numbers_on_page(page_text), _norm(page_text)
    issues = []
    for path, ev in flatten(model, prefix).items():
        val = ev.value.strip()
        d = D(val)
        found = (d in nums) if d is not None else (_norm(val) in norm_text)
        if not found:
            issues.append(Issue("evidence", f"value {val!r} not found in page text", [path]))
    return issues


# ------------------------------------------------------------------ business checks
def parse_rates(texts: list[str]) -> dict[str, Decimal]:
    """'100 JPY=58.65INR' -> {'JPY': 0.5865};  '1 EUR=89.9INR' -> {'EUR': 89.9}  (INR per 1 unit)."""
    rates = {}
    for t in texts:
        m = re.search(r"(\d+(?:\.\d+)?)\s*([A-Z]{3})\s*=\s*([\d.]+)\s*INR", t.replace(" ", ""))
        if m:
            rates[m.group(2)] = Decimal(m.group(3)) / Decimal(m.group(1))
    return rates


def check_header_consistency(ex: BoeExtraction, page_texts: dict[int, str]) -> list[Issue]:
    """BE no./date repeat on every page; they must all agree with the Part I extraction."""
    seen = defaultdict(int)
    for txt in page_texts.values():
        m = re.search(r"\b(\d{7})\s+(\d{2}/\d{2}/\d{4})\b", txt)
        if m:
            seen[m.groups()] += 1
    if not seen:
        return []
    (be_no, be_date), _ = max(seen.items(), key=lambda kv: kv[1])
    out = []
    if ex.summary.be_no.value != be_no:
        out.append(Issue("header_vote", f"BE no {ex.summary.be_no.value} != page-header majority {be_no}", ["summary.be_no"]))
    if ex.summary.be_date.value != be_date:
        out.append(Issue("header_vote", f"BE date {ex.summary.be_date.value} != page-header majority {be_date}", ["summary.be_date"]))
    if len(seen) > 1:
        out.append(Issue("header_vote", f"pages disagree on BE no/date: {dict(seen)}", []))
    return out


def check_item_arithmetic(ex: BoeExtraction) -> list[Issue]:
    out = []
    for i, pg in enumerate(ex.invoice_pages):
        for j, it in enumerate(pg.items):
            p, q, a = dv(it.unit_price), dv(it.quantity), dv(it.amount)
            if None in (p, q, a):
                out.append(Issue("item_arith", "unparseable number", [f"invoice_pages[{i}].items[{j}]"]))
            elif not close(p * q, a, Decimal("0.011")):
                base = f"invoice_pages[{i}].items[{j}]"
                out.append(Issue("item_arith", f"{p} x {q} = {p*q:.2f} but amount is {a}",
                                 [f"{base}.unit_price", f"{base}.quantity", f"{base}.amount"]))
    return out


def _group_items(ex):
    groups = defaultdict(list)  # invoice_no -> [(i, j, item)]
    headers = {}
    for i, pg in enumerate(ex.invoice_pages):
        for j, it in enumerate(pg.items):
            groups[pg.invoice_no.value].append((i, j, it))
        if pg.header:
            headers[pg.invoice_no.value] = (i, pg.header)
    return groups, headers


def check_invoice_totals(ex: BoeExtraction) -> list[Issue]:
    out = []
    groups, headers = _group_items(ex)
    for inv_no, (hi, h) in headers.items():
        total = sum((dv(it.amount, ZERO) for _, _, it in groups[inv_no]), ZERO)
        iv = dv(h.inv_value)
        if iv is not None and not close(total, iv, Decimal("0.05")):
            paths = [f"invoice_pages[{hi}].header.inv_value"] + \
                    [f"invoice_pages[{i}].items[{j}].amount" for i, j, _ in groups[inv_no]]
            out.append(Issue("invoice_total", f"invoice {inv_no}: items sum {total} != invoice value {iv}", paths))
    return out


def check_counts(ex: BoeExtraction) -> list[Issue]:
    out = []
    n_items = sum(len(p.items) for p in ex.invoice_pages)
    n_duty = len(ex.duty_items)
    declared = dv(ex.summary.total_items)
    if declared is not None and declared != n_items:
        out.append(Issue("count", f"header says {declared} items, Part II has {n_items}", ["summary.total_items"]))
    if n_duty != n_items:
        out.append(Issue("count", f"Part II has {n_items} items, Part III has {n_duty}", []))
    declared_inv = dv(ex.summary.total_invoices)
    n_inv = len({p.invoice_no.value for p in ex.invoice_pages})
    if declared_inv is not None and declared_inv != n_inv:
        out.append(Issue("count", f"header says {declared_inv} invoices, found {n_inv}", ["summary.total_invoices"]))
    return out


def check_summary_invoices(ex: BoeExtraction) -> list[Issue]:
    out = []
    _, headers = _group_items(ex)
    for k, ref in enumerate(ex.summary.invoices):
        if ref.invoice_no.value in headers:
            hi, h = headers[ref.invoice_no.value]
            if not close(dv(ref.amount), dv(h.inv_value), Decimal("0.005")):
                out.append(Issue("summary_invoice", f"invoice {ref.invoice_no.value}: Part I {ref.amount.value} != Part II {h.inv_value.value}",
                                 [f"summary.invoices[{k}].amount", f"invoice_pages[{hi}].header.inv_value"]))
        else:
            out.append(Issue("summary_invoice", f"invoice {ref.invoice_no.value} listed in Part I but no Part II found", [f"summary.invoices[{k}].invoice_no"]))
    return out


def check_valuation(ex: BoeExtraction) -> list[Issue]:
    """AV(INR) = (inv+misc)*rate + ins% * (inv+misc)*rate + freight*freight_rate.  Verified on both sample BEs."""
    out = []
    rates = parse_rates([e.value for e in ex.summary.exchange_rates])
    for inv_no, (hi, h) in _group_items(ex)[1].items():
        base = f"invoice_pages[{hi}].header"
        cur = h.invoice_currency.value.strip()
        fcur = (h.freight_currency.value.strip() if h.freight_currency else cur)
        r_inv = Decimal(1) if cur == "INR" else rates.get(cur)
        r_fr = Decimal(1) if fcur == "INR" else rates.get(fcur)
        if r_inv is None or r_fr is None:
            out.append(Issue("valuation", f"invoice {inv_no}: no exchange rate for {cur}/{fcur}", ["summary.exchange_rates"]))
            continue
        inv, misc = dv(h.inv_value), dv(h.misc_charge, ZERO)
        fr, av = dv(h.freight, ZERO), dv(h.assessable_value)
        pct = dv(h.insurance, ZERO)
        goods = (inv + misc) * r_inv
        ins = goods * pct / 100 if (h.insurance and "%" in h.insurance.value) else (pct * r_inv)
        expected = goods + ins + fr * r_fr
        tol = max(Decimal(1), av * Decimal("0.00001"))
        if not close(expected, av, tol):
            out.append(Issue("valuation", f"invoice {inv_no}: computed assessable {expected:.2f} != printed {av}",
                             [f"{base}.{f}" for f in ("inv_value", "freight", "insurance", "misc_charge", "assessable_value")]
                             + ["summary.exchange_rates"]))
    return out


def check_duty_items(ex: BoeExtraction) -> list[Issue]:
    out = []
    for k, d in enumerate(ex.duty_items):
        p = f"duty_items[{k}]"
        av, td = dv(d.assess_value), dv(d.total_duty)
        bcd_r, bcd_a = dv(d.bcd_rate), dv(d.bcd_amount, ZERO)
        sws, ig_r, ig_a = dv(d.sws_amount, ZERO), dv(d.igst_rate), dv(d.igst_amount, ZERO)
        if None in (av, td, bcd_r, ig_r):
            out.append(Issue("duty_item", "missing/unparseable duty field", [p]))
            continue
        bcd_notional = av * bcd_r / 100          # payable OR foregone (licence/notification)
        if bcd_a > 0 and not close(bcd_a, bcd_notional, Decimal("0.1")):
            out.append(Issue("duty_bcd", f"BCD {bcd_a} != {bcd_r}% of {av} = {bcd_notional:.2f}", [f"{p}.bcd_amount", f"{p}.bcd_rate", f"{p}.assess_value"]))
        if not close(sws, bcd_notional / 10, Decimal("0.15")):
            out.append(Issue("duty_sws", f"SWS {sws} != 10% of BCD ({bcd_notional/10:.2f})", [f"{p}.sws_amount", f"{p}.bcd_rate", f"{p}.assess_value"]))
        exp_igst = ig_r / 100 * (av + bcd_notional + sws)
        if not close(ig_a, exp_igst, Decimal("0.4")):
            out.append(Issue("duty_igst", f"IGST {ig_a} != {ig_r}% x (AV+BCD+SWS) = {exp_igst:.2f}", [f"{p}.igst_amount", f"{p}.igst_rate", f"{p}.assess_value", f"{p}.sws_amount"]))
        base_total = bcd_a + sws + ig_a
        # other duty amounts printed in B (CVD_05, SAD, G.CESS, ADD, CVD, SG) and C / C-A also count towards the total
        extras = sum((dv(c.amount, ZERO) for c in d.item_duty + d.other_duties + d.other_duties_a
                      if c.code not in ("BCD", "SWS", "IGST", "TVALUE", "AGGR")), ZERO)
        if not (close(td, base_total, Decimal("0.2")) or close(td, base_total + extras, Decimal("0.2"))):
            out.append(Issue("duty_total", f"item total {td} != BCD+SWS+IGST = {base_total}", [f"{p}.total_duty", f"{p}.bcd_amount", f"{p}.sws_amount", f"{p}.igst_amount"]))
    return out


def check_duty_totals(ex: BoeExtraction) -> list[Issue]:
    out, s, n = [], ex.summary, len(ex.duty_items)
    tol = Decimal("0.06") * n + 1                 # items are printed to 1 decimal, summary to whole rupees
    for name, attr in (("bcd", "bcd_amount"), ("sws", "sws_amount"), ("igst", "igst_amount")):
        printed = dv(getattr(s, name), None)
        if printed is None:
            continue
        total = sum((dv(getattr(d, attr), ZERO) for d in ex.duty_items), ZERO)
        if not close(total, printed, tol):
            out.append(Issue("duty_rollup", f"sum of item {name.upper()} {total} != Part I {printed}", [f"summary.{name}"]))
    td = dv(s.total_duty)
    heads = ("bcd", "acd", "sws", "nccd", "add", "cvd", "igst", "g_cess", "sg", "saed", "gsia", "tta", "health")
    parts = sum((dv(getattr(s, n_), ZERO) for n_ in heads), ZERO)
    if not close(parts, td, Decimal(1)):
        out.append(Issue("duty_summary", f"sum of duty heads {parts} != total duty {td}",
                         ["summary.total_duty"] + [f"summary.{n_}" for n_ in heads if getattr(s, n_) is not None]))
    if not close(td, dv(s.challan_amount), Decimal(1)):
        out.append(Issue("challan", f"total duty {td} != challan {s.challan_amount.value}", ["summary.total_duty", "summary.challan_amount"]))
    levy = sum((dv(getattr(s, n_), ZERO) for n_ in ("interest", "penalty", "fine")), ZERO)     # total amount = duty + int + penalty + fine
    if not close(td + levy, dv(s.total_amount), Decimal(1)):
        out.append(Issue("duty_summary", f"total duty {td} + interest/penalty/fine {levy} != total amount {s.total_amount.value}",
                         ["summary.total_amount"]))
    item_av = sum((dv(d.assess_value, ZERO) for d in ex.duty_items), ZERO)
    if not close(item_av, dv(s.total_assessable_value), Decimal("0.02") * n + 1):
        out.append(Issue("av_rollup", f"sum of item AV {item_av} != Part I {s.total_assessable_value.value}", ["summary.total_assessable_value"]))
    return out


def check_av_proportional(ex: BoeExtraction) -> list[Issue]:
    """Within one invoice every item's AV/amount ratio is the same (rate x freight/ins loading).
    Catches rows mis-linked between Part II and Part III."""
    out = []
    sno_to_inv = {p.invoice_sno.value: p.invoice_no.value for p in ex.invoice_pages}
    amount = {}
    for i, pg in enumerate(ex.invoice_pages):
        for j, it in enumerate(pg.items):
            amount[(pg.invoice_sno.value, it.sno.value)] = (dv(it.amount), f"invoice_pages[{i}].items[{j}].amount")
    by_inv = defaultdict(list)
    for k, d in enumerate(ex.duty_items):
        key = (d.invsno.value, d.itemsn.value)
        if key in amount and dv(d.assess_value):
            by_inv[d.invsno.value].append((k, dv(d.assess_value), *amount[key]))
        else:
            out.append(Issue("av_link", f"duty item {key} has no matching Part II item", [f"duty_items[{k}].invsno", f"duty_items[{k}].itemsn"]))
    for inv, rows in by_inv.items():
        ratios = [av / amt for _, av, amt, _ in rows if amt]
        if len(ratios) < 3:
            continue
        med = Decimal(median(ratios))
        for k, av, amt, apath in rows:
            if abs(av - amt * med) > med * Decimal("0.006") + Decimal("0.02") + av * Decimal("0.00001"):
                out.append(Issue("av_ratio", f"invoice {sno_to_inv.get(inv, inv)}: AV {av} vs amount {amt} breaks the invoice-wide ratio {med:.5f}",
                                 [f"duty_items[{k}].assess_value", apath]))
    return out


ALL_CHECKS = [check_item_arithmetic, check_invoice_totals, check_counts, check_summary_invoices,
              check_valuation, check_duty_items, check_duty_totals, check_av_proportional]


def run_all_checks(ex: BoeExtraction) -> list[Issue]:
    return [i for chk in ALL_CHECKS for i in chk(ex)]
