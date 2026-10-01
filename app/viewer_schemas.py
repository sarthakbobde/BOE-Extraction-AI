"""Extra schemas for the sections the viewer shows but the core pipeline does not extract.

All values are the printed strings (or None when blank). These are not evidence-gated; the
viewer labels them as extracted-but-not-cross-checked.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

S = str | None


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
    ad_code: S = Field(None, description="AD CODE")


class Manifest(BaseModel):
    mawb_no: S = Field(None, description="D.MANIFEST 6.MAWB NO (or the master document number)")
    mawb_date: S = Field(None, description="7.DATE")
    hawb_no: S = Field(None, description="8.HAWB NO")
    hawb_date: S = Field(None, description="9.DATE")
    packages: S = Field(None, description="10.PKG")
    gross_weight: S = Field(None, description="11.GW")


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
    payments: list[Payment] = Field(default_factory=list, description="F. PAYMENT DETAILS rows")
    events: list[ProcessingEvent] = Field(default_factory=list, description="H. PROCESSING DETAILS rows with a date/time filled in")
    containers: list[Container] = Field(default_factory=list, description="J. CONTAINER DETAILS rows on this page")


class InvoiceDetails(BaseModel):
    """Part II, first page of an invoice (sections A-D)."""
    invoice_sno: S = None
    invoice_no: S = None
    invoice_date: S = Field(None, description="Date printed next to the invoice number")
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


# Part IV sections other than M (supporting documents), N (containers) and O (invoice list, already in Part I).
# Column order is the printed header order; the model returns cells in exactly this order.
PART4_SECTIONS: dict[str, tuple[str, list[str]]] = {
    "A": ("SVB details", ["Inv sno", "Item sno", "Ref no", "Ref date", "Port code", "Lab", "P/F", "Load date", "P/F"]),
    "B": ("Previous BEs", ["Inv sno", "Item sno", "BE no", "BE date", "Port code", "Unit price", "Currency"]),
    "C": ("Re-import after export", ["Inv sno", "Item sno", "Notn no", "Sl no", "Freight", "Insurance", "Duty", "SB no",
                                     "SB date", "Port code", "S inv", "S item no"]),
    "D": ("Manufacturer / producer / grower", ["Inv sno", "Item sno", "Type", "Manufacturer code", "Source country",
                                              "Transit country", "Address"]),
    "E": ("Accessory status", ["Inv sno", "Item sno", "Accessory item details"]),
    "F": ("Licence details", ["Inv sno", "Item sno", "Lic sl no", "Lic no", "Lic date", "Code", "Port", "Debit value",
                              "Qty", "UQC", "Debit duty"]),
    "G": ("Scheme notification & duty foregone", ["Inv sno", "Item sno", "Exmp re", "Scheme notn", "Sch notn sl no",
                                                  "BCD rate", "CVD rate", "BCD amt fg", "Oth amt fg"]),
    "H": ("Certificate details", ["Certificate number", "Date", "Type"]),
    "I": ("HSS details", ["PRC level", "IEC", "Branch sl no"]),
    "J": ("Single window declaration", ["Inv sno", "Item sno", "Info type", "Qualifier", "Info code", "Info text",
                                        "Info measure", "UQC"]),
    "K": ("Single window - constituents", ["Inv sno", "Item sno", "C sno", "Name", "Code", "Percentage", "Yield pct",
                                           "Ingredient"]),
    "L": ("Single window - control", ["Inv sno", "Item sno", "Control type", "Location", "Start date", "End date",
                                      "Result code", "Result text"]),
}


class Part4Row(BaseModel):
    cells: list[S] = Field(description="One entry per column, in the exact column order given for the section; "
                                       "null for a blank cell")


class Part4Section(BaseModel):
    code: str = Field(description="Section letter, one of A-L")
    rows: list[Part4Row] = Field(default_factory=list)


class Part4Page(BaseModel):
    """Part IV - ADDITIONAL DETAILS: M. SUPPORTING DOCUMENTS, N. CONTAINER DETAILS and sections A-L."""
    supporting_docs: list[SupportingDoc] = Field(default_factory=list)
    containers: list[Container] = Field(default_factory=list)
    sections: list[Part4Section] = Field(default_factory=list, description="Only sections A-L that have at least one "
                                                                         "printed data row on this page")


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
    exam_order: S = Field(None, description="A./A1. EXAMINATION ORDER text (e.g. RMS order), null if blank")
    exam_instructions: list[str] = Field(default_factory=list, description="B. EXAMINATION INSTRUCTIONS, one entry per line")
    pga_instructions: list[PgaInstruction] = Field(default_factory=list, description="B1. PGA EXAMINATION INSTRUCTIONS rows")
    compliances: list[str] = Field(default_factory=list, description="C. COMPULSORY COMPLIANCE, one entry per line")
    ac_remarks: list[str] = Field(default_factory=list, description="D. AC REMARKS, one entry per line")
    exam_report: list[str] = Field(default_factory=list, description="E. EXAMINATION REPORT, one entry per line")
    superintendent_comments: list[str] = Field(default_factory=list, description="F. SUPERINTENDENT COMMENTS, one entry per line")
    ooc_no: S = Field(None, description="OOC No, null if blank")
    ooc_date: S = Field(None, description="OOC Date, null if blank")
