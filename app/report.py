"""Build a PDF report of a Bill of Entry's extracted data (the viewer's document shape)."""
from __future__ import annotations

import io
import os
from decimal import Decimal
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)

BLUE, BLUE_PALE, LINE, INK, SOFT = (colors.HexColor(c) for c in ("#133C84", "#DCE7F5", "#D9E7F3", "#122237", "#5C7089"))

FONT, FONT_B = "Helvetica", "Helvetica-Bold"
for reg, bold in ((r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
                  ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")):
    if os.path.exists(reg) and os.path.exists(bold):
        pdfmetrics.registerFont(TTFont("BoeSans", reg))
        pdfmetrics.registerFont(TTFont("BoeSans-Bold", bold))
        FONT, FONT_B = "BoeSans", "BoeSans-Bold"
        break

ST = {
    "title": ParagraphStyle("title", fontName=FONT_B, fontSize=17, textColor=BLUE, leading=21, spaceAfter=2),
    "sub": ParagraphStyle("sub", fontName=FONT, fontSize=9, textColor=SOFT, leading=12),
    "h1": ParagraphStyle("h1", fontName=FONT_B, fontSize=12.5, textColor=colors.white, leading=16, backColor=BLUE,
                         borderPadding=(4, 6, 4, 6), spaceBefore=14, spaceAfter=8),
    "h2": ParagraphStyle("h2", fontName=FONT_B, fontSize=10.5, textColor=BLUE, leading=14, spaceBefore=8, spaceAfter=4),
    "lab": ParagraphStyle("lab", fontName=FONT, fontSize=8.5, textColor=SOFT, leading=11),
    "val": ParagraphStyle("val", fontName=FONT, fontSize=8.5, textColor=INK, leading=11),
    "th": ParagraphStyle("th", fontName=FONT_B, fontSize=7.8, textColor=INK, leading=10),
    "td": ParagraphStyle("td", fontName=FONT, fontSize=7.8, textColor=INK, leading=10),
    "tdr": ParagraphStyle("tdr", fontName=FONT, fontSize=7.8, textColor=INK, leading=10, alignment=TA_RIGHT),
    "thr": ParagraphStyle("thr", fontName=FONT_B, fontSize=7.8, textColor=INK, leading=10, alignment=TA_RIGHT),
    "note": ParagraphStyle("note", fontName=FONT, fontSize=8, textColor=SOFT, leading=11),
}


def t(x) -> str:
    return "—" if x is None or x == "" else escape(str(x))


def money(n, cur: str | None = None) -> str:
    if n is None or n == "":
        return "—"
    try:
        s = f"{float(n):,.2f}"
    except (TypeError, ValueError):
        return t(n)
    return f"{s} {cur}" if cur else s


def p(text, style="val"):
    return Paragraph(text, ST[style])


def sheet(rows: list[tuple[str, str]], width: float):
    data = [[p(escape(a), "lab"), p(b if b.startswith("<") or b == "—" else b, "val")] for a, b in rows]
    tb = Table(data, colWidths=[width * 0.32, width * 0.68])
    tb.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
                            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                            ("BOX", (0, 0), (-1, -1), 0.6, LINE)]))
    return tb


def grid(head: list[str], rows: list[list[str]], widths: list[float], right: set[int] = frozenset(), foot=None):
    def cell(v, i, header=False):
        style = ("thr" if i in right else "th") if header else ("tdr" if i in right else "td")
        return p(v, style)
    data = [[cell(h, i, True) for i, h in enumerate(head)]] + [[cell(v, i) for i, v in enumerate(r)] for r in rows]
    if foot:
        data.append([Paragraph(f"<b>{v}</b>", ST["tdr" if i in right else "td"]) for i, v in enumerate(foot)])
    tb = Table(data, colWidths=widths, repeatRows=1)
    style = [("BACKGROUND", (0, 0), (-1, 0), BLUE_PALE), ("GRID", (0, 0), (-1, -1), 0.4, LINE),
             ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 2.5),
             ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]
    if foot:
        style.append(("BACKGROUND", (0, -1), (-1, -1), BLUE_PALE))
    tb.setStyle(TableStyle(style))
    return tb


def lines(a):
    return "<br/>".join(escape(str(x)) for x in a) if a else "—"


def build_report(doc: dict) -> bytes:
    buf = io.BytesIO()
    W = A4[0] - 30 * mm
    boe, st, dc, ds, mf = (doc.get(k) or {} for k in ("boe", "status", "declarant", "dutySummary", "manifest"))

    def footer(canvas, d):
        canvas.saveState()
        canvas.setFont(FONT, 7.5)
        canvas.setFillColor(SOFT)
        canvas.drawString(15 * mm, 9 * mm, f"BE {boe.get('beNo', '')} · {boe.get('portCode', '')} · extracted data report")
        canvas.drawRightString(A4[0] - 15 * mm, 9 * mm, f"Page {d.page}")
        canvas.restoreState()

    pdf = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=14 * mm,
                            bottomMargin=16 * mm, title=f"Bill of Entry {boe.get('beNo', '')} - extracted data")
    S = []
    S += [p(f"Bill of Entry {t(boe.get('beNo'))}", "title"),
          p(f"{t(boe.get('docType') or 'Bill of Entry')} · Port {t(boe.get('portCode'))} · {t(boe.get('beDate'))}", "sub")]
    q = doc.get("quality")
    src = f"Source: {t(doc.get('sourceFile'))}" if doc.get("sourceFile") else "Sample bill"
    S.append(p(src + (f" · {q['fields']} fields from Parts I–III, {q['failedChecks']} failed cross-checks, "
                      f"{q['needsReview']} need review" if q else ""), "sub"))
    S.append(Spacer(1, 4))

    # ---------------- Part I
    S.append(p("Part I — Bill of Entry summary", "h1"))
    S.append(p("Header", "h2"))
    S.append(sheet([("BE no. / date", f"{t(boe.get('beNo'))} · {t(boe.get('beDate'))}"), ("Port", t(boe.get("port"))),
                    ("BE type / copy", f"{t(boe.get('beType'))} · {t(boe.get('copyType'))}"),
                    ("IEC/Br", t(boe.get("iecBr"))), ("GSTIN/Type", t(boe.get("gstin"))), ("CB code", t(boe.get("cbCode"))),
                    ("Invoices / items / containers", f"{t(boe.get('totalInvoices'))} / {t(boe.get('totalItems'))} / {t(boe.get('totalContainers'))}"),
                    ("Packages / gross weight (kg)", f"{t(boe.get('totalPackages'))} / {t(boe.get('grossWeightKg'))}"),
                    ("Barcode ref", t(boe.get("barcode")))], W))
    S.append(p("A. Status", "h2"))
    S.append(sheet([("1. BE status", t(st.get("beStatus"))), ("2. Mode", t(st.get("mode"))),
                    ("3. Def BE / 4. Kaccha / 5. Sec 48", f"{t(st.get('defBe'))} / {t(st.get('kaccha'))} / {t(st.get('sec48'))}"),
                    ("6. Reimp / 7. Adv BE", f"{t(st.get('reimp'))} / {t(st.get('advBe'))}"),
                    ("8. Assess / 9. Exam / 10. HSS", f"{t(st.get('assess'))} / {t(st.get('exam'))} / {t(st.get('hss'))}"),
                    ("11. First check / 12. Prov-Final", f"{t(st.get('firstCheck'))} / {t(st.get('provFinal'))}"),
                    ("13. Country of origin", t(st.get("countryOfOrigin"))), ("14. Country of consignment", t(st.get("countryOfConsignment"))),
                    ("15. Port of loading", t(st.get("portOfLoading"))), ("16. Port of shipment", t(st.get("portOfShipment")))], W))
    S.append(p("B. Declarant", "h2"))
    S.append(sheet([("1. Importer", t(dc.get("importerName"))), ("Address", t(dc.get("importerAddress"))),
                    ("2. CB name", t(dc.get("cbName"))), ("3. AEO", t(dc.get("aeo"))), ("4. UCR", t(dc.get("ucr"))),
                    ("AD code", t(dc.get("adCode")))], W))
    S.append(p("C. Duty summary", "h2"))
    S.append(sheet([("1. BCD", money(ds.get("bcd"))), ("2. ACD", money(ds.get("acd"))), ("3. SWS", money(ds.get("sws"))),
                    ("4. NCCD", money(ds.get("nccd"))), ("5. ADD", money(ds.get("add"))), ("6. CVD", money(ds.get("cvd"))),
                    ("7. IGST", money(ds.get("igst"))), ("8. G.CESS", money(ds.get("gCess"))), ("9. SG", money(ds.get("sg"))),
                    ("10. SAED", money(ds.get("saed"))), ("11. GSIA", money(ds.get("gsia"))), ("12. TTA", money(ds.get("tta"))),
                    ("13. Health", money(ds.get("health"))), ("14. Total duty", money(ds.get("totalDuty"))),
                    ("15. Interest", money(ds.get("interest"))), ("16. Penalty", money(ds.get("penalty"))), ("17. Fine", money(ds.get("fine"))),
                    ("18. Total assessable value", money(ds.get("totalAssessableValue"))), ("19. Total amount", money(ds.get("totalAmount")))], W))
    S.append(p("D. Manifest", "h2"))
    S.append(sheet([("1. IGM no. / 2. date", f"{t(mf.get('igmNo'))} · {t(mf.get('igmDate'))}"),
                    ("3. INW date", t(mf.get("inwDate"))),
                    ("4. GIGM no. / 5. date", f"{t(mf.get('gigmNo'))} · {t(mf.get('gigmDate'))}"),
                    ("6. MAWB no. / 7. date", f"{t(mf.get('mawbNo'))} · {t(mf.get('mawbDate'))}"),
                    ("8. HAWB no. / 9. date", f"{t(mf.get('hawbNo'))} · {t(mf.get('hawbDate'))}"),
                    ("10. Packages / 11. Gross weight (kg)", f"{t(mf.get('packages'))} / {t(mf.get('grossWeightKg'))}")], W))
    S.append(p("E. Bond details", "h2"))
    if doc.get("bonds"):
        S.append(grid(["Bond no.", "Port", "Bond cd", "Debt amt", "BG amt"],
                      [[t(x.get("bondNo")), t(x.get("port")), t(x.get("bondCd")), money(x.get("debtAmt")), money(x.get("bgAmt"))] for x in doc["bonds"]],
                      [W * .25, W * .2, W * .15, W * .2, W * .2], {3, 4}))
    else:
        S.append(p("None declared." if isinstance(doc.get("bonds"), list) else "Not extracted for this bill.", "note"))
    S.append(p("G. Warehouse details", "h2"))
    if doc.get("warehouse"):
        S.append(grid(["WBE no.", "Date", "WBE site", "WH code"],
                      [[t(x.get("wbeNo")), t(x.get("date")), t(x.get("site")), t(x.get("whCode"))] for x in doc["warehouse"]],
                      [W * .3, W * .25, W * .25, W * .2]))
    else:
        S.append(p("None declared." if isinstance(doc.get("warehouse"), list) else "Not extracted for this bill.", "note"))
    if doc.get("payments"):
        S.append(p("F. Payment", "h2"))
        S.append(grid(["Sr", "Challan no.", "Paid on", "Amount (INR)"],
                      [[t(x.get("srNo")), t(x.get("challanNo")), t(x.get("paidOn")), money(x.get("amount"))] for x in doc["payments"]],
                      [W * .1, W * .35, W * .25, W * .3], {3}))
    if doc.get("events"):
        S.append(p("H. Processing", "h2"))
        S.append(grid(["Event", "Date", "Time", "Exchange rate"],
                      [[t(x.get("event")), t(x.get("date")), t(x.get("time")), t(x.get("rate"))] for x in doc["events"]],
                      [W * .25, W * .25, W * .15, W * .35]))
    S.append(p("J. Containers", "h2"))
    if doc.get("containers"):
        S.append(grid(["Sno", "LCL/FCL", "Truck", "Seal", "Container no."],
                      [[t(c.get("sno")), t(c.get("lclFcl")), t(c.get("truck")), t(c.get("seal")), t(c.get("containerNumber"))] for c in doc["containers"]],
                      [W * .1, W * .15, W * .2, W * .2, W * .35]))
    else:
        S.append(p("None declared.", "note"))

    # ---------------- Part II
    for inv in doc.get("invoices") or []:
        n = len(doc["invoices"])
        S.append(PageBreak())
        S.append(p(f"Part II — Invoice &amp; valuation · Invoice {t(inv.get('sno'))}/{n}", "h1"))
        pt, v, c = inv.get("parties") or {}, inv.get("valuation") or {}, inv.get("cost") or {}
        S.append(p("A. Invoice", "h2"))
        S.append(sheet([("1. S. no.", t(inv.get("sno"))), ("2. Invoice no. / date", f"{t(inv.get('no'))} · {t(inv.get('date'))}"),
                        ("3. Purchase order no. / date", f"{t(inv.get('poNo'))} · {t(inv.get('poDate'))}"),
                        ("4. LC no. / date", f"{t(inv.get('lcNo'))} · {t(inv.get('lcDate'))}"),
                        ("5. Contract no. / date", f"{t(inv.get('contractNo'))} · {t(inv.get('contractDate'))}"),
                        ("6. AD code", t(inv.get("adCode"))),
                        ("Invoice amount", money(inv.get("amount"), inv.get("currency")))], W))
        S.append(p("B. Transacting parties", "h2"))
        S.append(sheet([("Buyer", t(pt.get("buyer"))), ("Seller", t(pt.get("seller"))), ("Supplier", t(pt.get("supplier"))),
                        ("Third party", t(pt.get("thirdParty"))), ("5. AEO", t(pt.get("aeo")))], W))
        S.append(p("C. Valuation", "h2"))
        S.append(sheet([("Invoice value", money(v.get("invoiceValue"), inv.get("currency"))), ("Freight", money(v.get("freight"))),
                        ("Insurance", t(v.get("insurance"))), ("Pay terms", t(v.get("payTerms"))),
                        ("Valuation method", t(v.get("valuationMethod"))), ("Related party", t(v.get("relatedParty"))),
                        ("SVB ch / no / date", f"{t(v.get('svbCh'))} / {t(v.get('svbNo'))} / {t(v.get('svbDate'))}"),
                        ("14. Cur (invoice / freight)", f"{t(inv.get('valuation', {}).get('currency'))} / {t(v.get('freightCurrency'))}"),
                        ("Incoterm", t(v.get("incoterm")))], W))
        S.append(p("D. Cost &amp; services", "h2"))
        S.append(sheet([("1. C&B", money(c.get("cb"))), ("2. CoC", money(c.get("coc"))), ("3. CoP", money(c.get("cop"))),
                        ("4. HND CHG", money(c.get("hndChg"))), ("5. G&S", money(c.get("gs"))), ("6. DOC. CH", money(c.get("docCh"))),
                        ("7. COO", money(c.get("coo"))), ("8. R & LF", money(c.get("rlf"))), ("9. OTH COST", money(c.get("othCost"))),
                        ("10. LD / ULD", money(c.get("ldUld"))), ("11. WS", money(c.get("ws"))), ("12. OTC", money(c.get("otc"))),
                        ("13. Misc. charge", money(c.get("miscCharge"))), ("14. Assessable value", money(c.get("assessValue")))], W))
        items = inv.get("items") or []
        S.append(p(f"E. Item details ({len(items)})", "h2"))
        S.append(grid(["#", "CTH", "Description", "Unit price", "Qty", "Amount"],
                      [[t(i[0]), t(i[1]), t(i[2]), money(i[3]), f"{i[4] if i[4] is not None else '—'} {i[5] or ''}".strip(), money(i[6])]
                       for i in items], [W * .05, W * .12, W * .39, W * .14, W * .12, W * .18], {3, 4, 5}))

    # ---------------- Part III
    have_duties = any((inv.get("duties") for inv in doc.get("invoices") or []))
    if have_duties:
        S.append(PageBreak())
        S.append(p("Part III — Duties", "h1"))
        GROUPS = [("B. Item duty", [("bcd", "BCD"), ("cvd05", "CVD_05"), ("sws", "SWS"), ("sad", "SAD"), ("igst", "IGST"), ("gcess", "G.CESS"),
                                    ("add", "ADD"), ("cvd", "CVD"), ("sg", "SG"), ("tvalue", "T.VALUE")]),
                  ("C. Other duties", [("spexd", "SP EXD"), ("chcess", "CHCESS"), ("tta", "TTA"), ("cess", "CESS"), ("caidc", "CAIDC"),
                                       ("eaidc", "EAIDC"), ("cusedc", "CUS EDC"), ("cushec", "CUS HEC"), ("ncd", "NCD"), ("aggr", "AGGR")]),
                  ("C-A. Other duties - A", [("othcus", "OTHCUS"), ("othcvd", "OTHCVD"), ("petrcus", "PETR CUS"), ("infraces", "INFRA CES"),
                                             ("cuscvd", "CUS CVD")])]
        FLAGS = [("fs", "FS"), ("pq", "PQ"), ("dc", "DC"), ("wc", "WC"), ("aq", "AQ"), ("sch", "SCH"), ("stndPr", "STND/PR"), ("rsp", "RSP"),
                 ("reimp", "REIMP"), ("prov", "PROV"), ("endUse", "END USE"), ("prodn", "PRODN"), ("cntrl", "CNTRL"), ("qualfr", "QUALFR"),
                 ("contnt", "CONTNT"), ("stmnt", "STMNT"), ("supDocs", "SUP DOCS")]
        def raw(v):                                     # a number exactly as it was printed (no 6-digit rounding)
            if v is None:
                return ""
            if isinstance(v, float):
                s_ = format(Decimal(repr(v)), "f")
                return s_.rstrip("0").rstrip(".") if "." in s_ else s_
            return str(v)

        def duty_cell(x, key):
            """rate / amount, with the notification and duty-foregone rows underneath, as printed."""
            r, a_, nn, ns, fg = (x.get(key + k) for k in ("Rate", "Amount", "NotnNo", "NotnSno", "DutyFg"))
            if all(v is None for v in (r, a_, nn, ns, fg)):
                return "—"
            lines = []
            if r is not None or a_ is not None:
                lines.append(escape(f"{raw(r)}% / {raw(a_)}" if r is not None and a_ is not None else
                                    (f"{raw(r)}%" if r is not None else raw(a_))))
            if nn is not None or ns is not None:
                lines.append(escape(f"notn {raw(nn)} {raw(ns)}".strip()))
            if fg is not None:
                lines.append(escape(f"duty fg {raw(fg)}"))
            return "<br/>".join(lines)

        for inv in doc["invoices"]:
            d = inv.get("duties") or {}
            if not d:
                continue
            ks = sorted(d, key=lambda k: int(k) if str(k).isdigit() else 0)
            S.append(p(f"Invoice {t(inv.get('sno'))} — A. Item details", "h2"))
            tot_a = sum(d[k].get("assessValue") or 0 for k in ks)
            tot_d = sum(d[k].get("totalDuty") or 0 for k in ks)
            rows = []
            for k in ks:
                x = d[k]
                flags = " · ".join(f"{lab} {x[key]}" for key, lab in FLAGS if x.get(key) not in (None, ""))
                rows.append([t(k), t(x.get("cth")), t(x.get("ceth")), t(raw(x.get("upi")) or None), t(x.get("coo")),
                             t((raw(x.get("cQty")) + " " + (x.get("cUqc") or "")).strip() or None),
                             t((raw(x.get("sQty")) + " " + (x.get("sUqc") or "")).strip() or None), escape(flags) or "—",
                             money(x.get("assessValue")), money(x.get("totalDuty"))])
            S.append(grid(["Item", "CTH", "CETH", "UPI", "COO", "C.QTY", "S.QTY", "Other fields (6-28)", "Assess value", "Total duty"], rows,
                          [W * .06, W * .11, W * .12, W * .09, W * .06, W * .08, W * .08, W * .14, W * .13, W * .13], {8, 9},
                          foot=["Total", f"{len(ks)} items", "", "", "", "", "", "", money(tot_a), money(tot_d)]))
            for title, cols in GROUPS:
                present = [(key, lab) for key, lab in cols
                           if any(any(d[k].get(key + sfx) is not None for sfx in ("Rate", "Amount", "NotnNo", "NotnSno", "DutyFg")) for k in ks)]
                if not present:
                    continue
                S.append(p(f"Invoice {t(inv.get('sno'))} — {title}", "h2"))
                n = len(present)
                S.append(grid(["Item"] + [lab for _, lab in present], [[t(k)] + [duty_cell(d[k], key) for key, _ in present] for k in ks],
                              [W * .07] + [W * .93 / n] * n))

    # ---------------- Part IV (same order as the PDF: the A-L sections, then supporting docs, containers, invoices)
    S.append(p("Part IV — Additional details", "h1"))
    from viewer_schemas import PART4_SECTIONS
    order = list(PART4_SECTIONS)
    for sec in sorted(doc.get("additional") or [], key=lambda x: order.index(x["code"]) if x.get("code") in order else 99):
        cols = sec.get("columns") or []
        n = max(len(cols), 1)
        S.append(p(t(sec.get('title')), "h2"))
        S.append(grid([escape(c) for c in cols], [[t(c) for c in r] for r in sec.get("rows") or []], [W / n] * n))

    S.append(p("Supporting documents", "h2"))
    sd = doc.get("supportingDocs") or []
    if sd:
        def scope(x):
            return "BE level" if not x.get("inv") else (f"Invoice {x['inv']}" if not x.get("item") else f"Invoice {x['inv']} · item {x['item']}")
        S.append(grid(["Doc code", "Type", "IRN", "ICEGATE id", "Scope", "Place", "Issued", "Expires"],
                      [[t(x.get("type")), t(x.get("docType")), t(x.get("irn")), t(x.get("icegate")), scope(x), t(x.get("place")),
                        t(x.get("date")), t(x.get("expiry"))] for x in sd],
                      [W * .1, W * .07, W * .22, W * .13, W * .15, W * .11, W * .11, W * .11]))
    else:
        S.append(p("None declared.", "note"))

    S.append(p("Container details", "h2"))
    if doc.get("containers"):
        S.append(grid(["Container no.", "Truck", "Seal", "LCL / FCL", "Sno"],
                      [[t(c.get("containerNumber")), t(c.get("truck")), t(c.get("seal")), t(c.get("lclFcl")), t(c.get("sno"))]
                       for c in doc["containers"]], [W * .3, W * .2, W * .2, W * .15, W * .15]))
    else:
        S.append(p("None declared.", "note"))
    S.append(p("Invoice details", "h2"))
    S.append(grid(["S no.", "Invoice no.", "Invoice amount", "Cur"],
                  [[t(i.get("sno")), t(i.get("no")), money(i.get("amount")), t(i.get("currency"))] for i in doc.get("invoices") or []],
                  [W * .12, W * .38, W * .3, W * .2], {2}))

    # ---------------- Part V
    S.append(p("Part V — Other compliances", "h1"))
    c5 = doc.get("compliance")
    if not c5:
        S.append(p("Not extracted for this bill.", "note"))
    else:
        pga = [f"Inv {g.get('inv') or '–'} · Item {g.get('item') or '–'} · {g.get('agency') or '–'} · {g.get('status') or '–'}"
               for g in c5.get("pgaInstructions") or []]
        S.append(sheet([("A. Examination order (RMS)", t(c5.get("examOrder"))), ("B. Examination instructions", lines(c5.get("examInstructions"))),
                        ("B1. PGA instructions", lines(pga)), ("C. Compulsory compliance", lines(c5.get("compliances"))),
                        ("D. AC remarks", lines(c5.get("acRemarks"))), ("E. Examination report", lines(c5.get("examReport"))),
                        ("F. Superintendent comments", lines(c5.get("superintendentComments"))),
                        ("OOC no. / date", f"{t(c5.get('oocNo'))} / {t(c5.get('oocDate'))}")], W))

    # ---------------- Part VI
    S.append(p("Part VI — Declaration", "h1"))
    decl = doc.get("declarations") or []
    if decl:
        S.append(sheet([(f"Declaration for {x.get('for')}", t(x.get("text"))) for x in decl], W))
    sg = doc.get("signatory") or {}
    S.append(p("Authorized signatory", "h2"))
    S.append(sheet([("CHA name", t(sg.get("chaName"))), ("Date", t(sg.get("date"))), ("Place", t(sg.get("place")))], W))

    pdf.build(S, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
