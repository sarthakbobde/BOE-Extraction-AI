"""Build a PDF report of a Bill of Entry's extracted data (the viewer's document shape)."""
from __future__ import annotations

import io
import os
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
    S.append(sheet([("BE status", t(st.get("beStatus"))), ("Mode", t(st.get("mode"))), ("Assess / Exam / HSS", f"{t(st.get('assess'))} / {t(st.get('exam'))} / {t(st.get('hss'))}"),
                    ("First check / Prov-Final", f"{t(st.get('firstCheck'))} / {t(st.get('provFinal'))}"),
                    ("Country of origin", t(st.get("countryOfOrigin"))), ("Country of consignment", t(st.get("countryOfConsignment"))),
                    ("Port of loading", t(st.get("portOfLoading"))), ("Port of shipment", t(st.get("portOfShipment")))], W))
    S.append(p("B. Declarant", "h2"))
    S.append(sheet([("Importer", t(dc.get("importerName"))), ("Address", t(dc.get("importerAddress"))),
                    ("CB name", t(dc.get("cbName"))), ("AD code", t(dc.get("adCode")))], W))
    S.append(p("C. Duty summary", "h2"))
    S.append(sheet([("BCD", money(ds.get("bcd"))), ("SWS", money(ds.get("sws"))), ("IGST", money(ds.get("igst"))),
                    ("Total assessable value", money(ds.get("totalAssessableValue"))), ("Total duty", money(ds.get("totalDuty"))),
                    ("Total amount", money(ds.get("totalAmount")))], W))
    S.append(p("D. Manifest", "h2"))
    S.append(sheet([("MAWB no. / date", f"{t(mf.get('mawbNo'))} · {t(mf.get('mawbDate'))}"),
                    ("HAWB no. / date", f"{t(mf.get('hawbNo'))} · {t(mf.get('hawbDate'))}"),
                    ("Packages / gross weight (kg)", f"{t(mf.get('packages'))} / {t(mf.get('grossWeightKg'))}")], W))
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
        S.append(sheet([("Invoice no. / date", f"{t(inv.get('no'))} · {t(inv.get('date'))}"),
                        ("Invoice amount", money(inv.get("amount"), inv.get("currency")))], W))
        S.append(p("B. Transacting parties", "h2"))
        S.append(sheet([("Buyer", t(pt.get("buyer"))), ("Seller", t(pt.get("seller"))), ("Supplier", t(pt.get("supplier"))),
                        ("Third party", t(pt.get("thirdParty")))], W))
        S.append(p("C. Valuation", "h2"))
        S.append(sheet([("Invoice value", money(v.get("invoiceValue"), inv.get("currency"))), ("Freight", money(v.get("freight"))),
                        ("Insurance", t(v.get("insurance"))), ("Pay terms", t(v.get("payTerms"))),
                        ("Valuation method", t(v.get("valuationMethod"))), ("Related party", t(v.get("relatedParty"))),
                        ("SVB ch / no / date", f"{t(v.get('svbCh'))} / {t(v.get('svbNo'))} / {t(v.get('svbDate'))}"),
                        ("Incoterm", t(v.get("incoterm")))], W))
        S.append(p("D. Cost &amp; services", "h2"))
        S.append(sheet([("Misc. charge", money(c.get("miscCharge"))), ("Assessable value", money(c.get("assessValue")))], W))
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
        for inv in doc["invoices"]:
            d = inv.get("duties") or {}
            if not d:
                continue
            ks = sorted(d, key=lambda k: int(k) if str(k).isdigit() else 0)
            tot = {"a": 0.0, "b": 0.0, "s": 0.0, "i": 0.0, "d": 0.0}
            rows = []
            rate = lambda r: "" if r is None else f"{r:g}%"  # noqa: E731
            for k in ks:
                x = d[k]
                tot["a"] += x.get("assessValue") or 0
                tot["b"] += x.get("bcdAmount") or 0
                tot["s"] += x.get("swsAmount") or 0
                tot["i"] += x.get("igstAmount") or 0
                tot["d"] += x.get("totalDuty") or 0
                rows.append([t(k), t(x.get("cth")), money(x.get("assessValue")), rate(x.get("bcdRate")), money(x.get("bcdAmount")),
                             money(x.get("swsAmount")), rate(x.get("igstRate")), money(x.get("igstAmount")), money(x.get("totalDuty"))])
            S.append(p(f"Invoice {t(inv.get('sno'))} — item duties", "h2"))
            S.append(grid(["Item", "CTH", "Assess value", "BCD %", "BCD", "SWS", "IGST %", "IGST", "Total duty"], rows,
                          [W * .06, W * .11, W * .15, W * .08, W * .12, W * .1, W * .08, W * .14, W * .16], {2, 3, 4, 5, 6, 7, 8},
                          foot=["Total", f"{len(ks)} items", money(tot["a"]), "", money(tot["b"]), money(tot["s"]), "", money(tot["i"]), money(tot["d"])]))

    # ---------------- Part IV
    S.append(p("Part IV — Supporting documents", "h1"))
    sd = doc.get("supportingDocs") or []
    if sd:
        def scope(x):
            return "BE level" if not x.get("inv") else (f"Invoice {x['inv']}" if not x.get("item") else f"Invoice {x['inv']} · item {x['item']}")
        S.append(grid(["Doc code", "IRN", "ICEGATE id", "Scope", "Place", "Date"],
                      [[t(x.get("type")), t(x.get("irn")), t(x.get("icegate")), scope(x), t(x.get("place")), t(x.get("date"))] for x in sd],
                      [W * .12, W * .26, W * .16, W * .18, W * .14, W * .14]))
    else:
        S.append(p("None declared.", "note"))

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
