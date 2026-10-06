"""LLM-facing schemas.

Design rules
- Every extracted value is an `Ev` (value + verbatim quote). Numbers are kept as the
  *printed string* so there is no float drift and the evidence check is exact.
  Conversion to Decimal happens later, in code (checks.py).
- Optional printed-blank fields are `Ev | None` (None = blank on the page, never "0").
"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field, model_validator


class Val(BaseModel):
    """Lean evidence value (no quote) for the many additional fields: same checks and scoring as `Ev`, fewer tokens."""
    value: str = Field(description="Value exactly as printed on the page. No reformatting, "
                                   "no added thousands separators, no unit conversion.")


class Ev(Val):
    quote: str = Field(default="", description="Short verbatim snippet (<=60 chars) near the value.")


# ---------------------------------------------------------------- Part I
class InvoiceRef(BaseModel):
    sno: Ev
    invoice_no: Ev
    amount: Ev
    currency: Ev


class SummaryPage(BaseModel):
    """Part I - BILL OF ENTRY SUMMARY (page 1)."""
    port_code: Ev
    be_no: Ev
    be_date: Ev = Field(description="As printed, e.g. 14/02/2026")
    total_invoices: Ev = Field(description="'Nos' row, INV column in the page header")
    total_items: Ev = Field(description="'Nos' row, ITEM column in the page header")
    bcd: Ev | None = Field(None, description="C. DUTY SUMMARY 1.BCD")
    acd: Val | None = Field(None, description="C. DUTY SUMMARY 2.ACD")
    sws: Ev | None = Field(None, description="C. DUTY SUMMARY 3.SWS")
    nccd: Val | None = Field(None, description="C. DUTY SUMMARY 4.NCCD")
    add: Val | None = Field(None, description="C. DUTY SUMMARY 5.ADD")
    cvd: Val | None = Field(None, description="C. DUTY SUMMARY 6.CVD")
    igst: Ev | None = Field(None, description="C. DUTY SUMMARY 7.IGST")
    g_cess: Val | None = Field(None, description="C. DUTY SUMMARY 8.G.CESS")
    sg: Val | None = Field(None, description="C. DUTY SUMMARY 9.SG")
    saed: Val | None = Field(None, description="C. DUTY SUMMARY 10.SAED")
    gsia: Val | None = Field(None, description="C. DUTY SUMMARY 11.GSIA")
    tta: Val | None = Field(None, description="C. DUTY SUMMARY 12.TTA")
    health: Val | None = Field(None, description="C. DUTY SUMMARY 13.HEALTH")
    interest: Val | None = Field(None, description="C. DUTY SUMMARY 15.INT")
    penalty: Val | None = Field(None, description="C. DUTY SUMMARY 16.PNLTY")
    fine: Val | None = Field(None, description="C. DUTY SUMMARY 17.FINE")
    total_assessable_value: Ev = Field(description="C. DUTY SUMMARY 18.TOT.ASS VAL")
    total_duty: Ev = Field(description="C. DUTY SUMMARY 14.TOTAL DUTY")
    total_amount: Ev = Field(description="C. DUTY SUMMARY 19.TOT. AMOUNT")
    challan_amount: Ev = Field(description="F. PAYMENT DETAILS 4.AMOUNT(Rs.)")
    exchange_rates: list[Ev] = Field(description="Every line in H. PROCESSING DETAILS 'EXCHANGE RATE' "
                                                 "except 'INR=INR', verbatim, e.g. '100 JPY=58.65INR' "
                                                 "or '1 EUR=89.9INR'. NOTE: the rate may be per 100 units.")
    invoices: list[InvoiceRef] = Field(description="I. INVOICE DETAILS - SUMMARY rows")


# ---------------------------------------------------------------- Part II
class ItemLine(BaseModel):
    sno: Ev
    cth: Ev
    description: Ev
    unit_price: Ev
    quantity: Ev
    uqc: Ev
    amount: Ev


class InvoiceHeader(BaseModel):
    """Only present on the FIRST page of each invoice (has B/C/D sections)."""
    inv_value: Ev = Field(description="C. VALUATION 1.INV VALUE")
    freight: Ev | None = Field(None, description="C. VALUATION 2.FREIGHT")
    insurance: Ev | None = Field(None, description="C. VALUATION 3.INSURANCE, keep the % sign if printed")
    invoice_currency: Ev = Field(description="14.Cur - FIRST value (invoice currency)")
    freight_currency: Ev | None = Field(None, description="14.Cur - SECOND value (freight currency)")
    incoterm: Ev | None = Field(None, description="15.Term e.g. FOB")
    c_and_b: Val | None = Field(None, description="D. COST & SERVICES 1.C&B")
    coc: Val | None = Field(None, description="D. COST & SERVICES 2.CoC")
    cop: Val | None = Field(None, description="D. COST & SERVICES 3.CoP")
    hnd_chg: Val | None = Field(None, description="D. COST & SERVICES 4.HND CHG")
    g_and_s: Val | None = Field(None, description="D. COST & SERVICES 5.G&S")
    doc_ch: Val | None = Field(None, description="D. COST & SERVICES 6.DOC. CH")
    coo: Val | None = Field(None, description="D. COST & SERVICES 7.COO")
    r_and_lf: Val | None = Field(None, description="D. COST & SERVICES 8.R & LF")
    oth_cost: Val | None = Field(None, description="D. COST & SERVICES 9.OTH COST")
    ld_uld: Val | None = Field(None, description="D. COST & SERVICES 10.LD / ULD")
    ws: Val | None = Field(None, description="D. COST & SERVICES 11.WS")
    otc: Val | None = Field(None, description="D. COST & SERVICES 12.OTC")
    misc_charge: Ev | None = Field(None, description="D. COST & SERVICES 13.MISC CHARGE")
    assessable_value: Ev = Field(description="D. COST & SERVICES 14.ASS. VALUE")


class InvoicePage(BaseModel):
    """One page of Part II. Continuation pages have header=None."""
    invoice_sno: Ev = Field(description="A. INVOICE 1.S.NO")
    invoice_no: Ev = Field(description="A. INVOICE 2.INVOICE NO")
    header: InvoiceHeader | None = None
    items: list[ItemLine] = Field(description="Every row of E. ITEM DETAILS on this page, in order")


# ---------------------------------------------------------------- Part III
B_CODES = "BCD, CVD_05, SWS, SAD, IGST, G.CESS, ADD, CVD, SG, T.VALUE"
C_CODES = "SP EXD, CHCESS, TTA, CESS, CAIDC, EAIDC, CUS EDC, CUS HEC, NCD, AGGR"
CA_CODES = "OTHCUS, OTHCVD, PETR CUS, INFRA CES, CUS CVD"


class DutyCell(BaseModel):
    """One column of an item's duty matrix (B. ITEM DUTY, C. OTHER DUTIES or C. OTHER DUTIES - A)."""
    code: str = Field(description="The column heading without its number, e.g. 'BCD', 'CVD_05', 'G.CESS', 'SP EXD'")
    notn_no: Val | None = Field(None, description="'Notn No.' row of this column, null if blank")
    notn_sno: Val | None = Field(None, description="'Notn SNo.' row of this column, null if blank")
    rate: Val | None = Field(None, description="'Rate' row of this column, null if blank")
    amount: Val | None = Field(None, description="'Amount' row of this column, null if blank")
    duty_fg: Val | None = Field(None, description="'Duty Fg' row of this column, null if blank")

    @model_validator(mode="after")
    def _canonical(self):
        self.code = re.sub(r"[^A-Z0-9]", "", self.code.upper())          # 'G.CESS' -> 'GCESS', 'CVD_05' -> 'CVD05'
        return self


# old flat fields (used by the checks and by saved outputs) -> (column code, row)
_LEGACY_DUTY = {"bcd_rate": ("BCD", "rate"), "bcd_amount": ("BCD", "amount"), "sws_amount": ("SWS", "amount"),
                "igst_rate": ("IGST", "rate"), "igst_amount": ("IGST", "amount")}


class DutyItem(BaseModel):
    """Part III - one item block: A. ITEM DETAILS (fields 1-30), B. ITEM DUTY, C. OTHER DUTIES, C. OTHER DUTIES - A."""
    invsno: Ev = Field(description="1.INVSNO")
    itemsn: Ev = Field(description="2.ITEMSN")
    cth: Ev = Field(description="3.CTH")
    ceth: Val | None = Field(None, description="4.CETH")
    description: Val | None = Field(None, description="5.ITEM DESCRIPTION")
    fs: Val | None = Field(None, description="6.FS")
    pq: Val | None = Field(None, description="7.PQ")
    dc: Val | None = Field(None, description="8.DC")
    wc: Val | None = Field(None, description="9.WC")
    aq: Val | None = Field(None, description="10.AQ")
    upi: Val | None = Field(None, description="11.UPI")
    coo: Val | None = Field(None, description="12.COO")
    c_qty: Val | None = Field(None, description="13.C.QTY")
    c_uqc: Val | None = Field(None, description="14.C.UQC")
    s_qty: Val | None = Field(None, description="15.S.QTY")
    s_uqc: Val | None = Field(None, description="16.S.UQC")
    sch: Val | None = Field(None, description="17.SCH")
    stnd_pr: Val | None = Field(None, description="18.STND/PR")
    rsp: Val | None = Field(None, description="19.RSP")
    reimp: Val | None = Field(None, description="20.REIMP")
    prov: Val | None = Field(None, description="21.PROV")
    end_use: Val | None = Field(None, description="22.END USE")
    prodn: Val | None = Field(None, description="23.PRODN")
    cntrl: Val | None = Field(None, description="24.CNTRL")
    qualfr: Val | None = Field(None, description="25.QUALFR")
    contnt: Val | None = Field(None, description="26.CONTNT")
    stmnt: Val | None = Field(None, description="27.STMNT")
    sup_docs: Val | None = Field(None, description="28.SUP DOCS")
    assess_value: Ev = Field(description="29.ASSESS VALUE")
    total_duty: Ev = Field(description="30. TOTAL DUTY")
    item_duty: list[DutyCell] = Field(default_factory=list, description=f"B. ITEM DUTY columns ({B_CODES}); only columns "
                                      "with at least one non-blank cell, in printed order")
    other_duties: list[DutyCell] = Field(default_factory=list, description=f"C. OTHER DUTIES columns ({C_CODES}); only columns "
                                         "with at least one non-blank cell")
    other_duties_a: list[DutyCell] = Field(default_factory=list, description=f"C. OTHER DUTIES - A columns ({CA_CODES}); only "
                                           "columns with at least one non-blank cell")

    @model_validator(mode="before")
    @classmethod
    def _legacy_fields(cls, data):
        """Accept the old flat bcd_/sws_/igst_ fields (tests, saved outputs) and turn them into B. ITEM DUTY columns."""
        if isinstance(data, dict) and any(k in data for k in _LEGACY_DUTY) and "item_duty" not in data:
            data, cells = dict(data), {}
            for key, (code, row) in _LEGACY_DUTY.items():
                val = data.pop(key, None)
                if val is not None:
                    cells.setdefault(code, {"code": code})[row] = val
            data["item_duty"] = list(cells.values())
        return data

    # --- the legacy names stay readable (and assignable) so checks.py and the tests keep working
    def _cell(self, code: str, create: bool = False):
        for c in self.item_duty:
            if c.code == code:
                return c
        if create:
            c = DutyCell(code=code)
            self.item_duty.append(c)
            return c
        return None

    def _get(self, code: str, row: str):
        c = self._cell(code)
        return getattr(c, row) if c else None

    def _set(self, code: str, row: str, val):
        setattr(self._cell(code, create=True), row, val)

    bcd_rate = property(lambda s: s._get("BCD", "rate"), lambda s, v: s._set("BCD", "rate", v))
    bcd_amount = property(lambda s: s._get("BCD", "amount"), lambda s, v: s._set("BCD", "amount", v))
    sws_amount = property(lambda s: s._get("SWS", "amount"), lambda s, v: s._set("SWS", "amount", v))
    igst_rate = property(lambda s: s._get("IGST", "rate"), lambda s, v: s._set("IGST", "rate", v))
    igst_amount = property(lambda s: s._get("IGST", "amount"), lambda s, v: s._set("IGST", "amount", v))


class DutyPage(BaseModel):
    items: list[DutyItem] = Field(description="Every item block on this page (usually 3, or 2 on BE2-style pages)")


# ---------------------------------------------------------------- Assembled
class BoeExtraction(BaseModel):
    summary: SummaryPage
    invoice_pages: list[InvoicePage]
    duty_items: list[DutyItem]
    page_of: dict[str, int] = Field(default_factory=dict, description="path prefix -> PDF page number")


def flatten(obj, prefix: str = "") -> dict[str, Val]:
    """Return {dotted.path: Ev} for every evidence field inside obj."""
    out: dict[str, Ev] = {}
    if isinstance(obj, Val):
        out[prefix] = obj
    elif isinstance(obj, BaseModel):
        for name in type(obj).model_fields:
            child = getattr(obj, name)
            out.update(flatten(child, f"{prefix}.{name}" if prefix else name))
    elif isinstance(obj, list):
        for i, x in enumerate(obj):
            out.update(flatten(x, f"{prefix}[{i}]"))
    return out
