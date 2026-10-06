"""Map pipeline output onto the document shape used by boe_viewer.html (see DOCS in that file)."""
from __future__ import annotations

import re
from datetime import datetime

from confidence import resolves, score_doc

DATE_FORMATS = ("%d/%m/%Y", "%d-%b-%y", "%d-%b-%Y", "%d-%m-%Y", "%d/%m/%y")


def v(ev):
    """Ev | str | None -> str | None"""
    if ev is None:
        return None
    s = ev.value if hasattr(ev, "value") else ev
    s = None if s is None else re.sub(r"\s+", " ", str(s)).strip()
    return s or None


def num(x):
    s = v(x)
    if s is None:
        return None
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def integer(x):
    n = num(x)
    return None if n is None else int(n)


def date(x):
    s = v(x)
    if not s:
        return None
    for f in DATE_FORMATS:
        try:
            return datetime.strptime(s, f).strftime("%d-%b-%Y")
        except ValueError:
            pass
    return s


def pct(x):
    s = v(x)
    return "0" + s if s and s.startswith(".") else s


def rate_text(x):
    """'100 JPY=58.65INR' -> '100 JPY = 58.65 INR'"""
    s = v(x)
    if not s:
        return None
    m = re.match(r"^\s*([\d.]*)\s*([A-Z]{3})\s*=\s*([\d.]*)\s*([A-Z]{3})\s*$", s)
    if not m:
        return s
    a, c1, b, c2 = m.groups()
    return f"{a + ' ' if a else ''}{c1} = {b + ' ' if b else ''}{c2}"


_TOK = re.compile(r"[^.\[\]]+|\[\d+\]")
SUMMARY_MAP = {"port_code": "boe.portCode", "be_no": "boe.beNo", "be_date": "boe.beDate", "total_invoices": "boe.totalInvoices",
               "total_items": "boe.totalItems", "bcd": "dutySummary.bcd", "sws": "dutySummary.sws", "igst": "dutySummary.igst",
               "acd": "dutySummary.acd", "nccd": "dutySummary.nccd", "add": "dutySummary.add", "cvd": "dutySummary.cvd",
               "g_cess": "dutySummary.gCess", "sg": "dutySummary.sg", "saed": "dutySummary.saed", "gsia": "dutySummary.gsia",
               "tta": "dutySummary.tta", "health": "dutySummary.health", "interest": "dutySummary.interest",
               "penalty": "dutySummary.penalty", "fine": "dutySummary.fine",
               "total_assessable_value": "dutySummary.totalAssessableValue", "total_duty": "dutySummary.totalDuty",
               "total_amount": "dutySummary.totalAmount", "challan_amount": "payments.0.amount"}
SUMMARY_INV_MAP = {"invoice_no": "no", "amount": "amount", "currency": "currency"}
HEADER_MAP = {"inv_value": "valuation.invoiceValue", "freight": "valuation.freight", "insurance": "valuation.insurance",
              "invoice_currency": "valuation.currency", "incoterm": "valuation.incoterm", "misc_charge": "cost.miscCharge",
              "assessable_value": "cost.assessValue", "c_and_b": "cost.cb", "coc": "cost.coc", "cop": "cost.cop",
              "hnd_chg": "cost.hndChg", "g_and_s": "cost.gs", "doc_ch": "cost.docCh", "coo": "cost.coo", "r_and_lf": "cost.rlf",
              "oth_cost": "cost.othCost", "ld_uld": "cost.ldUld", "ws": "cost.ws", "otc": "cost.otc"}
ITEM_MAP = {"cth": 1, "description": 2, "unit_price": 3, "quantity": 4, "uqc": 5, "amount": 6}
DUTY_MAP = {"cth": "cth", "assess_value": "assessValue", "total_duty": "totalDuty", "ceth": "ceth", "description": "description",
            "fs": "fs", "pq": "pq", "dc": "dc", "wc": "wc", "aq": "aq", "upi": "upi", "coo": "coo", "c_qty": "cQty", "c_uqc": "cUqc",
            "s_qty": "sQty", "s_uqc": "sUqc", "sch": "sch", "stnd_pr": "stndPr", "rsp": "rsp", "reimp": "reimp", "prov": "prov",
            "end_use": "endUse", "prodn": "prodn", "cntrl": "cntrl", "qualfr": "qualfr", "contnt": "contnt", "stmnt": "stmnt",
            "sup_docs": "supDocs"}
CELL_ROWS = {"notn_no": "NotnNo", "notn_sno": "NotnSno", "rate": "Rate", "amount": "Amount", "duty_fg": "DutyFg"}
DUTY_GROUPS = ("item_duty", "other_duties", "other_duties_a")


def _toks(path: str) -> list[str]:
    return [t[1:-1] if t.startswith("[") else t for t in _TOK.findall(path)]


def map_pipeline_rows(rows, ex, inv_idx, item_idx) -> dict:
    """Pipeline field scores (python paths like invoice_pages[2].items[5].unit_price) -> viewer data paths."""
    out: dict[str, dict] = {}

    def put(vp, row):
        cur = out.get(vp)
        if cur is None or row["score"] < cur["s"]:           # several sources for one field: keep the worst
            out[vp] = {"s": row["score"], "b": "checked", "r": list(row["reasons"])}

    for row in rows:
        t = _toks(row["path"])
        if not t or t[0] == "(document)":
            continue
        try:
            if t[0] == "summary" and len(t) >= 2:
                if t[1] in SUMMARY_MAP:
                    put(SUMMARY_MAP[t[1]], row)
                elif t[1] == "invoices" and len(t) >= 4 and t[3] in SUMMARY_INV_MAP:
                    j = inv_idx.get(v(ex.summary.invoices[int(t[2])].sno))
                    if j is not None:
                        put(f"invoices.{j}.{SUMMARY_INV_MAP[t[3]]}", row)
            elif t[0] == "invoice_pages" and len(t) >= 3:
                page = ex.invoice_pages[int(t[1])]
                j = inv_idx.get(v(page.invoice_sno))
                if j is None:
                    continue
                if t[2] == "invoice_no":
                    put(f"invoices.{j}.no", row)
                elif t[2] == "header" and len(t) >= 4 and t[3] in HEADER_MAP:
                    put(f"invoices.{j}.{HEADER_MAP[t[3]]}", row)
                elif t[2] == "items" and len(t) >= 5 and t[4] in ITEM_MAP:
                    jj, n = item_idx[id(page.items[int(t[3])])]
                    put(f"invoices.{jj}.items.{n}.{ITEM_MAP[t[4]]}", row)
            elif t[0] == "duty_items" and len(t) >= 3:
                it = ex.duty_items[int(t[1])]
                j = inv_idx.get(v(it.invsno))
                if j is None:
                    continue
                base = f"invoices.{j}.duties.{v(it.itemsn)}"
                if t[2] in DUTY_MAP:
                    put(f"{base}.{DUTY_MAP[t[2]]}", row)
                elif t[2] in DUTY_GROUPS and len(t) >= 5 and t[4] in CELL_ROWS:
                    cell = getattr(it, t[2])[int(t[3])]
                    put(f"{base}.{cell.code.lower()}{CELL_ROWS[t[4]]}", row)
        except (IndexError, KeyError, ValueError):
            continue
    return out


def first(items):
    return items[0][1] if items else None


def build_doc(ex, extras: dict, quality: dict, filename: str, field_rows=None, full_text: str = "",
              section_pages: dict | None = None, page_count: int | None = None) -> dict:
    s = ex.summary
    p1 = first(extras.get("part1"))
    hdr, st, dc, mf = (p1.header, p1.status, p1.declarant, p1.manifest) if p1 else (None,) * 4

    containers, seen = [], set()
    cand = list(p1.containers) if p1 else []
    for _, p4 in extras.get("part4", []):
        cand += p4.containers
    for c in cand:
        key = v(c.container_number) or id(c)
        if key in seen:
            continue
        seen.add(key)
        containers.append({"sno": integer(c.sno) or len(containers) + 1, "lclFcl": v(c.lcl_fcl), "truck": v(c.truck),
                           "seal": v(c.seal), "containerNumber": v(c.container_number)})

    # ---- invoices
    inv_details = {}
    for _, d in extras.get("inv_details", []):
        inv_details[v(d.invoice_sno)] = d
    summary_inv = {v(i.sno): i for i in s.invoices}
    duties = {}
    for it in ex.duty_items:
        row = {"cth": v(it.cth), "ceth": v(it.ceth), "description": v(it.description), "fs": v(it.fs), "pq": v(it.pq),
               "dc": v(it.dc), "wc": v(it.wc), "aq": v(it.aq), "upi": num(it.upi), "coo": v(it.coo), "cQty": num(it.c_qty),
               "cUqc": v(it.c_uqc), "sQty": num(it.s_qty), "sUqc": v(it.s_uqc), "sch": v(it.sch), "stndPr": v(it.stnd_pr),
               "rsp": v(it.rsp), "reimp": v(it.reimp), "prov": v(it.prov), "endUse": v(it.end_use), "prodn": v(it.prodn),
               "cntrl": v(it.cntrl), "qualfr": v(it.qualfr), "contnt": v(it.contnt), "stmnt": v(it.stmnt),
               "supDocs": v(it.sup_docs), "assessValue": num(it.assess_value), "totalDuty": num(it.total_duty)}
        for group in DUTY_GROUPS:                                   # one flat key per matrix cell
            for c in getattr(it, group):
                k = c.code.lower()
                row.update({k + "NotnNo": v(c.notn_no), k + "NotnSno": v(c.notn_sno), k + "Rate": num(c.rate),
                            k + "Amount": num(c.amount), k + "DutyFg": num(c.duty_fg)})
        duties.setdefault(v(it.invsno), {})[v(it.itemsn)] = row

    grouped: dict[str, list] = {}
    for pg in ex.invoice_pages:
        grouped.setdefault(v(pg.invoice_sno), []).append(pg)
    invoices = []
    inv_idx: dict[str, int] = {}
    item_idx: dict[int, tuple[int, int]] = {}
    page_idx = {id(pg): k for k, pg in enumerate(ex.invoice_pages)}
    item_page: dict[int, int | None] = {}
    inv_pages: dict[int, set] = {}
    for sno in sorted(grouped, key=lambda x: (integer(x) is None, integer(x) or 0)):
        pages = grouped[sno]
        h = next((p.header for p in pages if p.header), None)
        det = inv_details.get(sno)
        si = summary_inv.get(sno)
        items = sorted((it for p in pages for it in p.items), key=lambda it: integer(it.sno) or 0)
        inv_idx[sno] = len(invoices)
        for pg in pages:
            pn = ex.page_of.get(f"invoice_pages[{page_idx[id(pg)]}]")
            inv_pages.setdefault(len(invoices), set()).add(pn)
            for it in pg.items:
                item_page[id(it)] = pn
        for n, it in enumerate(items):
            item_idx[id(it)] = (len(invoices), n)
        invoices.append({
            "sno": integer(sno) or len(invoices) + 1,
            "no": v(pages[0].invoice_no),
            "date": date(det.invoice_date) if det else None,
            "amount": num(si.amount) if si else (num(h.inv_value) if h else None),
            "currency": v(si.currency) if si else (v(h.invoice_currency) if h else None),
            "poNo": v(det.purchase_order_no) if det else None, "poDate": date(det.purchase_order_date) if det else None,
            "lcNo": v(det.lc_no) if det else None, "lcDate": date(det.lc_date) if det else None,
            "contractNo": v(det.contract_no) if det else None, "contractDate": date(det.contract_date) if det else None,
            "adCode": v(det.ad_code) if det else None,
            "parties": {"aeo": v(det.aeo) if det else None,
                        "buyer": v(det.buyer) if det else None, "seller": v(det.seller) if det else None,
                        "supplier": v(det.supplier) if det else None, "thirdParty": v(det.third_party) if det else None},
            "valuation": {
                "invoiceValue": num(h.inv_value) if h else None, "freight": num(h.freight) if h else None,
                "insurance": pct(h.insurance) if h else None, "hss": v(det.hss) if det else None,
                "loading": v(det.loading) if det else None, "commission": v(det.commission) if det else None,
                "payTerms": v(det.pay_terms) if det else None,
                "valuationMethod": v(det.valuation_method) if det else None,
                "currency": v(h.invoice_currency) if h else None, "freightCurrency": v(h.freight_currency) if h else None,
                "relatedParty": v(det.related_party) if det else None, "svbCh": v(det.svb_ch) if det else None,
                "svbNo": v(det.svb_no) if det else None, "svbDate": date(det.svb_date) if det else None,
                "loa": v(det.loa) if det else None, "incoterm": v(h.incoterm) if h else None},
            "cost": {"cb": num(h.c_and_b) if h else None, "coc": num(h.coc) if h else None, "cop": num(h.cop) if h else None,
                     "hndChg": num(h.hnd_chg) if h else None, "gs": num(h.g_and_s) if h else None,
                     "docCh": num(h.doc_ch) if h else None, "coo": num(h.coo) if h else None, "rlf": num(h.r_and_lf) if h else None,
                     "othCost": num(h.oth_cost) if h else None, "ldUld": num(h.ld_uld) if h else None,
                     "ws": num(h.ws) if h else None, "otc": num(h.otc) if h else None,
                     "miscCharge": num(h.misc_charge) if h else None, "assessValue": num(h.assessable_value) if h else None},
            "items": [[integer(it.sno), v(it.cth), v(it.description), num(it.unit_price), num(it.quantity),
                       v(it.uqc), num(it.amount)] for it in items],
            "duties": duties.get(sno, {}),
        })

    declarations, signatory = [], {"chaName": None, "date": None, "place": None}
    for _, p6 in extras.get("part6", []):
        declarations += [{"for": d.for_, "text": re.sub(r"\s+", " ", d.text).strip()} for d in p6.declarations]
        for k, val in (("chaName", p6.cha_name), ("date", p6.signed_date), ("place", p6.signed_place)):
            if val and not signatory[k]:
                signatory[k] = val.strip()

    supporting = []
    for _, p4 in extras.get("part4", []):
        for d in p4.supporting_docs:
            supporting.append({"inv": integer(d.invsno) or 0, "item": integer(d.itmsno) or 0, "type": v(d.doc_code),
                               "docType": v(d.doc_type), "icegate": v(d.icegate_id), "irn": v(d.irn),
                               "place": v(d.issue_place), "date": date(d.issue_date), "expiry": date(d.expiry_date)})

    from viewer_schemas import PART4_SECTIONS  # sections A-L, merged across pages, only those with data
    merged: dict[str, list] = {}
    for _, p4 in extras.get("part4", []):
        for sec in p4.sections:
            code = (sec.code or "").strip().lower()
            if code not in PART4_SECTIONS:
                continue
            width = len(PART4_SECTIONS[code][1])
            for r in sec.rows:
                cells = [v(c) for c in r.cells][:width]
                cells += [None] * (width - len(cells))
                if any(cells):
                    merged.setdefault(code, []).append(cells)
    order = list(PART4_SECTIONS)                    # dict order = the order the sections are printed in the PDF
    additional = [{"code": c, "title": PART4_SECTIONS[c][0], "columns": PART4_SECTIONS[c][1], "rows": merged[c]}
                  for c in sorted(merged, key=order.index)]

    def lines(xs):
        return [t for t in (re.sub(r"\s+", " ", x).strip() for x in xs) if t]

    compliance = None
    if extras.get("part5"):
        compliance = {"examOrder": None, "examOrderA1": None, "examInstructions": [], "pgaInstructions": [], "compliances": [],
                      "acRemarks": [], "examReport": [], "superintendentComments": [], "oocNo": None, "oocDate": None}
        for _, p5 in extras["part5"]:
            compliance["examOrder"] = compliance["examOrder"] or v(p5.exam_order)
            compliance["examOrderA1"] = compliance["examOrderA1"] or v(p5.exam_order_a1)
            compliance["examInstructions"] += lines(p5.exam_instructions)
            compliance["pgaInstructions"] += [{"inv": v(g.inv_no), "item": v(g.item_no), "agency": v(g.agency),
                                               "status": v(g.status)} for g in p5.pga_instructions]
            compliance["compliances"] += lines(p5.compliances)
            compliance["acRemarks"] += lines(p5.ac_remarks)
            compliance["examReport"] += lines(p5.exam_report)
            compliance["superintendentComments"] += lines(p5.superintendent_comments)
            compliance["oocNo"] = compliance["oocNo"] or v(p5.ooc_no)
            compliance["oocDate"] = compliance["oocDate"] or date(p5.ooc_date)

    port_code = v(s.port_code)
    be_no = v(s.be_no)
    # ---- where each thing sits in the PDF (drives the side-by-side viewer)
    rows_pg: dict[str, int] = {}
    for iid, (j, n) in item_idx.items():
        if item_page.get(iid):
            rows_pg[f"invoices.{j}.items.{n}"] = item_page[iid]
    duty_pages: dict[int, set] = {}
    for n, it in enumerate(ex.duty_items):
        j, pn = inv_idx.get(v(it.invsno)), ex.page_of.get(f"duty_items[{n}]")
        if j is not None and pn:
            rows_pg[f"invoices.{j}.duties.{v(it.itemsn)}"] = pn
            duty_pages.setdefault(j, set()).add(pn)
    sp = section_pages or {}
    page_map = {"I": sp.get("I") or [ex.page_of.get("summary", 1)],
                "II": {str(j): sorted(p for p in ps if p) for j, ps in inv_pages.items()},
                "III": {str(j): sorted(ps) for j, ps in duty_pages.items()},
                "IV": sp.get("IV", []), "V": sp.get("V", []), "VI": sp.get("VI", []), "rows": rows_pg}

    doc = {
        "label": f"{port_code} · BE {be_no}", "short": f"BE {be_no}", "sourceFile": filename, "uploaded": True,
        "quality": quality,
        "boe": {"portCode": port_code, "beNo": be_no, "beDate": date(s.be_date),
                "beType": v(hdr.be_type) if hdr else None, "iecBr": v(hdr.iec_br) if hdr else None,
                "copyType": (v(hdr.copy_type) if hdr else None) or "—", "gstin": v(hdr.gstin_type) if hdr else None,
                "cbCode": v(hdr.cb_code) if hdr else None, "docType": v(hdr.doc_type) if hdr else None,
                "port": (v(hdr.port_name) if hdr else None) or port_code,
                "totalInvoices": integer(s.total_invoices) or len(invoices),
                "totalItems": integer(s.total_items) or sum(len(i["items"]) for i in invoices),
                "totalContainers": (integer(hdr.total_containers) if hdr else None) or len(containers),
                "totalPackages": integer(hdr.total_packages) if hdr else None,
                "grossWeightKg": v(hdr.gross_weight) if hdr else None,
                "barcode": v(hdr.barcode_ref) if hdr else None},
        "status": {"beStatus": v(st.be_status) if st else None, "mode": v(st.mode) if st else None,
                   "assess": v(st.assess) if st else None, "exam": v(st.exam) if st else None,
                   "hss": v(st.hss) if st else None, "firstCheck": v(st.first_check) if st else None,
                   "provFinal": v(st.prov_final) if st else None, "defBe": v(st.def_be) if st else None,
                   "kaccha": v(st.kaccha) if st else None, "sec48": v(st.sec_48) if st else None,
                   "reimp": v(st.reimp) if st else None, "advBe": v(st.adv_be) if st else None,
                   "countryOfOrigin": v(st.country_of_origin) if st else None,
                   "countryOfConsignment": v(st.country_of_consignment) if st else None,
                   "portOfLoading": v(st.port_of_loading) if st else None,
                   "portOfShipment": v(st.port_of_shipment) if st else None},
        "declarant": {"importerName": v(dc.importer_name) if dc else None,
                      "importerAddress": v(dc.importer_address) if dc else None,
                      "cbName": v(dc.cb_name) if dc else None, "adCode": v(dc.ad_code) if dc else None,
                      "aeo": v(dc.aeo) if dc else None, "ucr": v(dc.ucr) if dc else None},
        "dutySummary": {"bcd": num(s.bcd), "acd": num(s.acd), "sws": num(s.sws), "nccd": num(s.nccd), "add": num(s.add),
                        "cvd": num(s.cvd), "igst": num(s.igst), "gCess": num(s.g_cess), "sg": num(s.sg), "saed": num(s.saed),
                        "gsia": num(s.gsia), "tta": num(s.tta), "health": num(s.health), "interest": num(s.interest),
                        "penalty": num(s.penalty), "fine": num(s.fine),
                        "totalAssessableValue": num(s.total_assessable_value), "totalDuty": num(s.total_duty),
                        "totalAmount": num(s.total_amount)},
        "manifest": {"igmNo": v(mf.igm_no) if mf else None, "igmDate": date(mf.igm_date) if mf else None,
                     "inwDate": date(mf.inw_date) if mf else None, "gigmNo": v(mf.gigm_no) if mf else None,
                     "gigmDate": date(mf.gigm_date) if mf else None, "mawbNo": v(mf.mawb_no) if mf else None, "mawbDate": date(mf.mawb_date) if mf else None,
                     "hawbNo": v(mf.hawb_no) if mf else None, "hawbDate": date(mf.hawb_date) if mf else None,
                     "packages": integer(mf.packages) if mf else None,
                     "grossWeightKg": v(mf.gross_weight) if mf else None},
        "bonds": [{"bondNo": v(b.bond_no), "port": v(b.port), "bondCd": v(b.bond_cd), "debtAmt": num(b.debt_amt),
                   "bgAmt": num(b.bg_amt)} for b in p1.bonds if any([b.bond_no, b.port, b.bond_cd, b.debt_amt, b.bg_amt])] if p1 else [],
        "warehouse": [{"wbeNo": v(w.wbe_no), "date": date(w.date), "site": v(w.site), "whCode": v(w.wh_code)}
                      for w in p1.warehouse if any([w.wbe_no, w.date, w.site, w.wh_code])] if p1 else [],
        "payments": [{"srNo": integer(p.sr_no) or i + 1, "challanNo": v(p.challan_no), "paidOn": date(p.paid_on),
                      "amount": num(p.amount)} for i, p in enumerate(p1.payments)] if p1 else [],
        "events": [{"event": v(e.event), "date": date(e.date), "time": v(e.time), "rate": rate_text(e.exchange_rate)}
                   for e in p1.events] if p1 else [],
        "containers": containers,
        "invoices": invoices,
        "supportingDocs": supporting,
        "additional": additional,
        "compliance": compliance,
        "declarations": declarations,
        "signatory": signatory,
    }
    conf = score_doc(doc, full_text) if full_text else {}
    conf.update(map_pipeline_rows(field_rows or [], ex, inv_idx, item_idx))
    doc["conf"] = {k: c for k, c in conf.items() if resolves(doc, k)}
    doc["edits"] = {}
    doc["pageMap"] = page_map
    doc["schema"] = 2                      # every printed field of Parts I-VI is read (older bills lack "schema")
    if page_count:
        doc["pageCount"] = page_count
    return doc
