"""LLM-facing schemas.

Design rules
- Every extracted value is an `Ev` (value + verbatim quote). Numbers are kept as the
  *printed string* so there is no float drift and the evidence check is exact.
  Conversion to Decimal happens later, in code (checks.py).
- Optional printed-blank fields are `Ev | None` (None = blank on the page, never "0").
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class Ev(BaseModel):
    value: str = Field(description="Value exactly as printed on the page. No reformatting, "
                                   "no added thousands separators, no unit conversion.")
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
    sws: Ev | None = Field(None, description="C. DUTY SUMMARY 3.SWS")
    igst: Ev | None = Field(None, description="C. DUTY SUMMARY 7.IGST")
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
    misc_charge: Ev | None = Field(None, description="D. COST & SERVICES 13.MISC CHARGE")
    assessable_value: Ev = Field(description="D. COST & SERVICES 14.ASS. VALUE")


class InvoicePage(BaseModel):
    """One page of Part II. Continuation pages have header=None."""
    invoice_sno: Ev = Field(description="A. INVOICE 1.S.NO")
    invoice_no: Ev = Field(description="A. INVOICE 2.INVOICE NO")
    header: InvoiceHeader | None = None
    items: list[ItemLine] = Field(description="Every row of E. ITEM DETAILS on this page, in order")


# ---------------------------------------------------------------- Part III
class DutyItem(BaseModel):
    invsno: Ev = Field(description="1.INVSNO")
    itemsn: Ev = Field(description="2.ITEMSN")
    cth: Ev
    assess_value: Ev = Field(description="29.ASSESS VALUE")
    total_duty: Ev = Field(description="30. TOTAL DUTY")
    bcd_rate: Ev | None = Field(None, description="B. ITEM DUTY, Rate row, 1.BCD column")
    bcd_amount: Ev | None = Field(None, description="B. ITEM DUTY, Amount row, 1.BCD column")
    sws_amount: Ev | None = Field(None, description="B. ITEM DUTY, Amount row, 3.SWS column")
    igst_rate: Ev | None = Field(None, description="B. ITEM DUTY, Rate row, 5.IGST column")
    igst_amount: Ev | None = Field(None, description="B. ITEM DUTY, Amount row, 5.IGST column")


class DutyPage(BaseModel):
    items: list[DutyItem] = Field(description="Every item block on this page (usually 3, or 2 on BE2-style pages)")


# ---------------------------------------------------------------- Assembled
class BoeExtraction(BaseModel):
    summary: SummaryPage
    invoice_pages: list[InvoicePage]
    duty_items: list[DutyItem]
    page_of: dict[str, int] = Field(default_factory=dict, description="path prefix -> PDF page number")


def flatten(obj, prefix: str = "") -> dict[str, Ev]:
    """Return {dotted.path: Ev} for every evidence field inside obj."""
    out: dict[str, Ev] = {}
    if isinstance(obj, Ev):
        out[prefix] = obj
    elif isinstance(obj, BaseModel):
        for name in type(obj).model_fields:
            child = getattr(obj, name)
            out.update(flatten(child, f"{prefix}.{name}" if prefix else name))
    elif isinstance(obj, list):
        for i, x in enumerate(obj):
            out.update(flatten(x, f"{prefix}[{i}]"))
    return out
