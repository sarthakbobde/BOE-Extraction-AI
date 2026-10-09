"""Extra schemas for the sections the viewer shows but the core pipeline does not extract.

All values are the printed strings (or None when blank). These are not evidence-gated; the
viewer labels them as extracted-but-not-cross-checked.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

S = str | None


class Doubt(BaseModel):
    """A value the model is NOT fully sure about. Values that are not listed are treated as read with high confidence."""
    field: str = Field(description="Which value, written as the instructions say")
    level: Literal["medium", "low"] = Field(description="'medium' = some doubt, 'low' = a guess")


class Part1Header(BaseModel):
    be_type: S = Field(None, description="BE Type in the page header, e.g. H")
    iec_br: S = Field(None, description="IEC/Br in the page header")
    copy_type: S = Field(None, description="Copy label printed in the header, e.g. FIRST COPY")
    gstin_type: S = Field(None, description="GSTIN/TYPE in the page header")
    cb_code: S = Field(None, description="CB CODE in the page header")
    doc_type: S = Field(None, description="Document title, e.g. BILL OF ENTRY FOR HOME CONSUMPTION")
    port_name: S = Field(None, description="Text printed after 'PORT :' in the header, if any")
    total_containers: S = Field(None, description="'Nos' row, CONT column")
    total_packages: S = Field(None, description="'Nos' row, PKG column")
    gross_weight: S = Field(None, description="'Nos' row, G.WT (KGS)")
    barcode_ref: S = Field(None, description="Barcode reference printed near the header, e.g. BE0140220261441")


class Status(BaseModel):
    """Part I - A. STATUS"""
    be_status: S = None
    mode: S = Field(None, description="2.MODE e.g. Air / Sea / Land")
    def_be: S = Field(None, description="3.DEF BE")
    kaccha: S = Field(None, description="4.KACHA")
    sec_48: S = Field(None, description="5.SEC 48")
    reimp: S = Field(None, description="6.REIMP")
    adv_be: S = Field(None, description="7.ADV BE")
    assess: S = Field(None, description="8.ASSESS")
    exam: S = Field(None, description="9.EXAM")
    hss: S = Field(None, description="10.HSS")
    first_check: S = Field(None, description="11.FIRST CHECK")
    prov_final: S = Field(None, description="12.PROV/FINAL")
    country_of_origin: S = Field(None, description="13.COUNTRY OF ORIGIN, in the case it is printed (e.g. Japan)")
    country_of_consignment: S = Field(None, description="14.COUNTRY OF CONSIGNMENT")
    port_of_loading: S = Field(None, description="15.PORT OF LOADING")
    port_of_shipment: S = Field(None, description="16.PORT OF SHIPMENT")


class Declarant(BaseModel):
    importer_name: S = Field(None, description="B.DECLARANT 1.IMPORTER NAME (first line only)")
    importer_address: S = Field(None, description="Remaining address lines of 1.IMPORTER NAME & ADDRESS, joined with '; '")
    cb_name: S = Field(None, description="2.CB NAME")
    aeo: S = Field(None, description="3.AEO")
    ucr: S = Field(None, description="4.UCR")
    ad_code: S = Field(None, description="AD CODE")


class Manifest(BaseModel):
    igm_no: S = Field(None, description="D.MANIFEST 1.IGM NO")
    igm_date: S = Field(None, description="2.IGM DATE")
    inw_date: S = Field(None, description="3.INW DATE")
    gigm_no: S = Field(None, description="4.GIGMNO")
    gigm_date: S = Field(None, description="5.GIGMDT")
    mawb_no: S = Field(None, description="D.MANIFEST 6.MAWB NO (or the master document number)")
    mawb_date: S = Field(None, description="7.DATE")
    hawb_no: S = Field(None, description="8.HAWB NO")
    hawb_date: S = Field(None, description="9.DATE")
    packages: S = Field(None, description="10.PKG")
    gross_weight: S = Field(None, description="11.GW")


class Bond(BaseModel):
    bond_no: S = Field(None, description="E. BOND DETAILS 1.BOND NO.")
    port: S = Field(None, description="2.PORT")
    bond_cd: S = Field(None, description="3.BOND CD")
    debt_amt: S = Field(None, description="4.DEBT AMT")
    bg_amt: S = Field(None, description="5.BG AMT")


class Warehouse(BaseModel):
    wbe_no: S = Field(None, description="G. WH 1.WBE NO.")
    date: S = Field(None, description="2.DATE")
    site: S = Field(None, description="3.WBE SITE")
    wh_code: S = Field(None, description="4.WH CODE")


class Payment(BaseModel):
    sr_no: S = None
    challan_no: S = None
    paid_on: S = None
    amount: S = None


class ProcessingEvent(BaseModel):
    event: S = Field(None, description="Submission / Assessment / Examination / OOC / Finalisation ...")
    date: S = None
    time: S = None
    exchange_rate: S = Field(None, description="EXCHANGE RATE printed on that row, e.g. 'INR=INR'")


class Container(BaseModel):
    sno: S = None
    lcl_fcl: S = None
    truck: S = None
    seal: S = None
    container_number: S = None


class Part1Details(BaseModel):
    """Everything on Part I that the core SummaryPage does not capture."""
    header: Part1Header
    status: Status
    declarant: Declarant
    manifest: Manifest
    bonds: list[Bond] = Field(default_factory=list, description="E. BOND DETAILS rows (empty when the section is blank)")
    payments: list[Payment] = Field(default_factory=list, description="F. PAYMENT DETAILS rows")
    warehouse: list[Warehouse] = Field(default_factory=list, description="G. WH rows (empty when the section is blank)")
    events: list[ProcessingEvent] = Field(default_factory=list, description="H. PROCESSING DETAILS rows with a date/time filled in")
    containers: list[Container] = Field(default_factory=list, description="J. CONTAINER DETAILS rows on this page")
    ooc_no: S = Field(None, description="H. PROCESSING DETAILS 'OOC NO.', null if blank")
    ooc_date: S = Field(None, description="H. PROCESSING DETAILS 'OOC DATE', null if blank")
    doubts: list[Doubt] = Field(default_factory=list, description="Only values you are not fully sure about")


class InvoiceDetails(BaseModel):
    """Part II, first page of an invoice (sections A-D)."""
    invoice_sno: S = None
    invoice_no: S = None
    invoice_date: S = Field(None, description="Date printed next to the invoice number")
    purchase_order_no: S = Field(None, description="A. 3.PURCHASE ORDER NO (the number part)")
    purchase_order_date: S = Field(None, description="3.PURCHASE ORDER ... DT (the date part)")
    lc_no: S = Field(None, description="4.LC NO (the number part)")
    lc_date: S = Field(None, description="4.LC ... DATE (the date part)")
    contract_no: S = Field(None, description="5.CONTRACT NO (the number part)")
    contract_date: S = Field(None, description="5.CONTRACT ... DATE (the date part)")
    ad_code: S = Field(None, description="6. AD CODE")
    aeo: S = Field(None, description="B. 5.AEO")
    buyer: S = Field(None, description="B. 1.BUYER'S NAME & ADDRESS, lines joined with ', '")
    seller: S = Field(None, description="2.SELLER'S NAME & ADDRESS, null if blank")
    supplier: S = Field(None, description="Supplier / exporter name & address in section B, null if blank")
    third_party: S = Field(None, description="4.THIRD PARTY NAME & ADDRESS, null if blank")
    hss: S = Field(None, description="C. 4.HSS")
    loading: S = Field(None, description="C. 5.LOADING")
    commission: S = Field(None, description="C. 6.COMMN")
    pay_terms: S = Field(None, description="C. 7.PAY TERMS")
    valuation_method: S = Field(None, description="C. 8.VALUATION METHOD")
    related_party: S = Field(None, description="C. 9.RELTD")
    svb_ch: S = Field(None, description="C. 10.SVB CH")
    svb_no: S = Field(None, description="C. 11.SVB NO")
    svb_date: S = Field(None, description="C. 12.DATE")
    loa: S = Field(None, description="C. 13 LOA")
    doubts: list[Doubt] = Field(default_factory=list, description="Only values you are not fully sure about")


class SupportingDoc(BaseModel):
    invsno: S = Field(None, description="1.INVSN")
    itmsno: S = Field(None, description="2.ITMSNO (0 = whole invoice / whole BE)")
    doc_type: S = Field(None, description="3.TYP")
    icegate_id: S = Field(None, description="4.ICEGATE ID")
    irn: S = Field(None, description="5.IRN")
    doc_code: S = Field(None, description="6.DOC CODE")
    issue_place: S = Field(None, description="7.ISSUE PLACE")
    issue_date: S = Field(None, description="8.ISSUE DT")
    expiry_date: S = Field(None, description="9.EXP DT")


# Part IV sections other than supporting documents, containers and the invoice list.
# The printed section LETTERS differ between BOE form versions (e.g. supporting documents are "M." on the 2026 form
# and "L." on the 2025 form), so sections are identified by TITLE. Column order is the printed header order; the
# model returns cells in exactly this order.
PART4_SECTIONS: dict[str, tuple[str, list[str]]] = {
    "svb": ("SVB details", ["Inv sno", "Item sno", "Ref no", "Ref date", "Port code", "Lab", "P/F", "Load date", "P/F"]),
    "previous_be": ("Previous BEs", ["Inv sno", "Item sno", "BE no", "BE date", "Port code", "Unit price", "Currency"]),
    "reimport": ("Re-import after export", ["Inv sno", "Item sno", "Notn no", "Sl no", "Freight", "Insurance", "Duty",
                                            "SB no", "SB date", "Port code", "S inv", "S item no"]),
    "manufacturer": ("Manufacturer / producer / grower", ["Inv sno", "Item sno", "Type", "Manufacturer code",
                                                         "Source country", "Transit country", "Address"]),
    "accessory": ("Accessory status", ["Inv sno", "Item sno", "Accessory item details"]),
    "licence": ("Licence details", ["Inv sno", "Item sno", "Lic sl no", "Lic no", "Lic date", "Code", "Port",
                                    "Debit value", "Qty", "UQC", "Debit duty"]),
    "scheme_notification": ("Scheme notification & duty foregone", ["Inv sno", "Item sno", "Exmp re", "Scheme notn",
                                                                      "Sch notn sl no", "BCD rate", "CVD rate",
                                                                      "BCD amt fg", "Oth amt fg"]),
    "certificate": ("Certificate details", ["Certificate number", "Date", "Type"]),
    "hss": ("HSS details", ["PRC level", "IEC", "Branch sl no"]),
    "sw_declaration": ("Single window declaration", ["Inv sno", "Item sno", "Info type", "Qualifier", "Info code",
                                                     "Info text", "Info measure", "UQC"]),
    "sw_constituents": ("Single window - constituents", ["Inv sno", "Item sno", "C sno", "Name", "Code", "Percentage",
                                                         "Yield pct", "Ingredient"]),
    "sw_control": ("Single window - control", ["Inv sno", "Item sno", "Control type", "Location", "Start date",
                                               "End date", "Result code", "Result text"]),
}


class Part4Row(BaseModel):
    cells: list[S] = Field(description="One entry per column, in the exact column order given for the section; "
                                       "null for a blank cell")


class Part4Section(BaseModel):
    code: str = Field(description="Section key exactly as listed in the prompt, e.g. 'svb' or 'sw_declaration'")
    rows: list[Part4Row] = Field(default_factory=list)


class Part4Page(BaseModel):
    """Part IV - ADDITIONAL DETAILS: supporting documents, container details and the other sections."""
    supporting_docs: list[SupportingDoc] = Field(default_factory=list)
    containers: list[Container] = Field(default_factory=list)
    sections: list[Part4Section] = Field(default_factory=list, description="Only sections that have at least one "
                                                                         "printed data row on this page")
    doubts: list[Doubt] = Field(default_factory=list, description="Only cells in `sections` you are not fully sure about")


class Declaration(BaseModel):
    for_: str = Field(description="The 'N/M' after 'Declaration for', e.g. '1/0'")
    text: str = Field(description="Declaration text, whitespace normalised")


class Part6Page(BaseModel):
    declarations: list[Declaration] = Field(default_factory=list)
    cha_name: S = Field(None, description="B. AUTHORIZED SIGNATORY CHA NAME")
    signed_date: S = Field(None, description="DATE next to the signatory, if filled")
    signed_place: S = Field(None, description="PLACE next to the signatory, if filled")


class PgaInstruction(BaseModel):
    inv_no: S = None
    item_no: S = None
    agency: S = None
    status: S = None


class Part5Page(BaseModel):
    """Part V - OTHER COMPLIANCES. Every list is empty when the section is blank on the page."""
    exam_order: S = Field(None, description="A. EXAMINATION ORDER RMS text, null if blank")
    exam_order_a1: S = Field(None, description="A1. EXAMINATION ORDER text, null if blank")
    exam_instructions: list[str] = Field(default_factory=list, description="B. EXAMINATION INSTRUCTIONS, one entry per line")
    pga_instructions: list[PgaInstruction] = Field(default_factory=list, description="B1. PGA EXAMINATION INSTRUCTIONS rows")
    compliances: list[str] = Field(default_factory=list, description="C. COMPULSORY COMPLIANCE, one entry per line")
    ac_remarks: list[str] = Field(default_factory=list, description="D. AC REMARKS, one entry per line")
    exam_report: list[str] = Field(default_factory=list, description="E. EXAMINATION REPORT, one entry per line")
    superintendent_comments: list[str] = Field(default_factory=list, description="F. SUPERINTENDENT COMMENTS, one entry per line")
    ooc_no: S = Field(None, description="OOC No, null if blank")
    ooc_date: S = Field(None, description="OOC Date, null if blank")
