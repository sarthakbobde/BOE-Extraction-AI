"""Map pipeline output onto the document shape used by boe_viewer.html (see DOCS in that file)."""
from __future__ import annotations

import re
from datetime import datetime

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


def first(items):
    return items[0][1] if items else None


def build_doc(ex, extras: dict, quality: dict, filename: str) -> dict:
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
        duties.setdefault(v(it.invsno), {})[v(it.itemsn)] = {
            "cth": v(it.cth), "assessValue": num(it.assess_value), "totalDuty": num(it.total_duty),
            "bcdRate": num(it.bcd_rate), "bcdAmount": num(it.bcd_amount), "swsAmount": num(it.sws_amount),
            "igstRate": num(it.igst_rate), "igstAmount": num(it.igst_amount)}

    grouped: dict[str, list] = {}
    for pg in ex.invoice_pages:
        grouped.setdefault(v(pg.invoice_sno), []).append(pg)
    invoices = []
    for sno in sorted(grouped, key=lambda x: (integer(x) is None, integer(x) or 0)):
        pages = grouped[sno]
        h = next((p.header for p in pages if p.header), None)
        det = inv_details.get(sno)
        si = summary_inv.get(sno)
        items = sorted((it for p in pages for it in p.items), key=lambda it: integer(it.sno) or 0)
        invoices.append({
            "sno": integer(sno) or len(invoices) + 1,
            "no": v(pages[0].invoice_no),
            "date": date(det.invoice_date) if det else None,
            "amount": num(si.amount) if si else (num(h.inv_value) if h else None),
            "currency": v(si.currency) if si else (v(h.invoice_currency) if h else None),
            "parties": {"buyer": v(det.buyer) if det else None, "seller": v(det.seller) if det else None,
                        "supplier": v(det.supplier) if det else None, "thirdParty": v(det.third_party) if det else None},
            "valuation": {
                "invoiceValue": num(h.inv_value) if h else None, "freight": num(h.freight) if h else None,
                "insurance": pct(h.insurance) if h else None, "hss": v(det.hss) if det else None,
                "loading": v(det.loading) if det else None, "commission": v(det.commission) if det else None,
                "payTerms": v(det.pay_terms) if det else None,
                "valuationMethod": v(det.valuation_method) if det else None,
                "currency": v(h.invoice_currency) if h else None,
                "relatedParty": v(det.related_party) if det else None, "svbCh": v(det.svb_ch) if det else None,
                "svbNo": v(det.svb_no) if det else None, "svbDate": date(det.svb_date) if det else None,
                "loa": v(det.loa) if det else None, "incoterm": v(h.incoterm) if h else None},
            "cost": {"miscCharge": num(h.misc_charge) if h else None, "assessValue": num(h.assessable_value) if h else None},
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
                               "icegate": v(d.icegate_id), "irn": v(d.irn), "place": v(d.issue_place),
                               "date": date(d.issue_date)})

    def lines(xs):
        return [t for t in (re.sub(r"\s+", " ", x).strip() for x in xs) if t]

    compliance = None
    if extras.get("part5"):
        compliance = {"examOrder": None, "examInstructions": [], "pgaInstructions": [], "compliances": [],
                      "acRemarks": [], "examReport": [], "superintendentComments": [], "oocNo": None, "oocDate": None}
        for _, p5 in extras["part5"]:
            compliance["examOrder"] = compliance["examOrder"] or v(p5.exam_order)
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
    return {
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
                   "provFinal": v(st.prov_final) if st else None,
                   "countryOfOrigin": v(st.country_of_origin) if st else None,
                   "countryOfConsignment": v(st.country_of_consignment) if st else None,
                   "portOfLoading": v(st.port_of_loading) if st else None,
                   "portOfShipment": v(st.port_of_shipment) if st else None},
        "declarant": {"importerName": v(dc.importer_name) if dc else None,
                      "importerAddress": v(dc.importer_address) if dc else None,
                      "cbName": v(dc.cb_name) if dc else None, "adCode": v(dc.ad_code) if dc else None},
        "dutySummary": {"bcd": num(s.bcd), "sws": num(s.sws), "igst": num(s.igst),
                        "totalAssessableValue": num(s.total_assessable_value), "totalDuty": num(s.total_duty),
                        "totalAmount": num(s.total_amount)},
        "manifest": {"mawbNo": v(mf.mawb_no) if mf else None, "mawbDate": date(mf.mawb_date) if mf else None,
                     "hawbNo": v(mf.hawb_no) if mf else None, "hawbDate": date(mf.hawb_date) if mf else None,
                     "packages": integer(mf.packages) if mf else None,
                     "grossWeightKg": v(mf.gross_weight) if mf else None},
        "payments": [{"srNo": integer(p.sr_no) or i + 1, "challanNo": v(p.challan_no), "paidOn": date(p.paid_on),
                      "amount": num(p.amount)} for i, p in enumerate(p1.payments)] if p1 else [],
        "events": [{"event": v(e.event), "date": date(e.date), "time": v(e.time), "rate": rate_text(e.exchange_rate)}
                   for e in p1.events] if p1 else [],
        "containers": containers,
        "invoices": invoices,
        "supportingDocs": supporting,
        "compliance": compliance,
        "declarations": declarations,
        "signatory": signatory,
    }
