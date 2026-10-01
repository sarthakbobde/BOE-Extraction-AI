"""Run: pytest -q
Golden data transcribed from the real BE 7526371 (INDEL4, 14/02/2026) you uploaded.
The point: prove the deterministic layer accepts a correct extraction and
catches realistic LLM mistakes (digit swap, wrong row, dropped item, wrong column).
"""
import copy

from checks import evidence_issues, parse_rates, run_all_checks
from schemas import (BoeExtraction, DutyItem, Ev, InvoiceHeader, InvoicePage,
                     InvoiceRef, ItemLine, SummaryPage)


def ev(v):
    return Ev(value=str(v), quote=str(v))


# (unit_price, qty, amount)  Part II, invoice BYA48607
ITEMS = [
    ("14482.49", "64", "926879.36"), ("14482.49", "2", "28964.98"), ("14425.53", "1", "14425.53"),
    ("14463.49", "3", "43390.47"), ("14425.53", "2", "28851.06"), ("14425.53", "1", "14425.53"),
    ("14425.53", "2", "28851.06"), ("14425.53", "2", "28851.06"), ("14425.53", "1", "14425.53"),
    ("14425.53", "1", "14425.53"), ("14425.53", "1", "14425.53"), ("14425.53", "1", "14425.53"),
    ("14594.86", "2", "29189.72"), ("14752.33", "3", "44256.99"), ("15165.73", "9", "136491.57"),
    ("14482.49", "94", "1361354.06"), ("14482.49", "8", "115859.92"), ("14444.53", "2", "28889.06"),
    ("14463.49", "4", "57853.96"), ("14425.53", "6", "86553.18"), ("14425.53", "3", "43276.59"),
    ("14594.86", "7", "102164.02"), ("14752.33", "4", "59009.32"), ("14752.33", "5", "73761.65"),
]
# (assess_value, total_duty, bcd_amt, sws, igst)  Part III
DUTIES = [
    ("563345.29", "211085.5", "84501.8", "8450.2", "118133.5"), ("17604.54", "6596.5", "2640.7", "264.1", "3691.7"),
    ("8767.65", "3285.2", "1315.1", "131.5", "1838.6"), ("26372.17", "9881.6", "3955.8", "395.6", "5530.2"),
    ("17535.3", "6570.5", "2630.3", "263", "3677.2"), ("8767.65", "3285.2", "1315.1", "131.5", "1838.6"),
    ("17535.3", "6570.5", "2630.3", "263", "3677.2"), ("17535.3", "6570.5", "2630.3", "263", "3677.2"),
    ("8767.65", "3285.2", "1315.1", "131.5", "1838.6"), ("8767.65", "3285.2", "1315.1", "131.5", "1838.6"),
    ("8767.65", "3285.2", "1315.1", "131.5", "1838.6"), ("8767.65", "3285.2", "1315.1", "131.5", "1838.6"),
    ("17741.13", "6647.6", "2661.2", "266.1", "3720.3"), ("26898.83", "10079", "4034.8", "403.5", "5640.7"),
    ("82957.81", "31084.4", "12443.7", "1244.4", "17396.3"), ("827413.39", "310031.8", "124112", "12411.2", "173508.6"),
    ("70418.16", "26385.7", "10562.7", "1056.3", "14766.7"), ("17558.4", "6579.2", "2633.8", "263.4", "3682"),
    ("35162.89", "13175.5", "5274.4", "527.4", "7373.7"), ("52605.9", "19711.5", "7890.9", "789.1", "11031.5"),
    ("26302.95", "9855.6", "3945.4", "394.5", "5515.7"), ("62093.97", "23266.6", "9314.1", "931.4", "13021.1"),
    ("35865.1", "13438.7", "5379.8", "538", "7520.9"), ("44831.38", "16798.3", "6724.7", "672.5", "9401.1"),
]


def golden() -> BoeExtraction:
    summary = SummaryPage(
        port_code=ev("INDEL4"), be_no=ev("7526371"), be_date=ev("14/02/2026"),
        total_invoices=ev("1"), total_items=ev("24"),
        bcd=ev("301857.3"), sws=ev("30185.7"), igst=ev("421997"),
        total_assessable_value=ev("2012384"), total_duty=ev("754040"), total_amount=ev("754040"),
        challan_amount=ev("754040"), exchange_rates=[ev("100 JPY=58.65INR")],
        invoices=[InvoiceRef(sno=ev("1"), invoice_no=ev("BYA48607"), amount=ev("3311001.21"), currency=ev("JPY"))],
    )
    header = InvoiceHeader(inv_value=ev("3311001.21"), freight=ev("118650"), insurance=ev(".046%"),
                           invoice_currency=ev("JPY"), freight_currency=ev("JPY"), incoterm=ev("FOB"),
                           misc_charge=None, assessable_value=ev("2012383.71"))
    items = [ItemLine(sno=ev(i + 1), cth=ev("87089900"), description=ev("SPEEDOMETER ASSY. COMB"),
                      unit_price=ev(p), quantity=ev(q), uqc=ev("NOS"), amount=ev(a))
             for i, (p, q, a) in enumerate(ITEMS)]
    duties = [DutyItem(invsno=ev("1"), itemsn=ev(i + 1), cth=ev("87089900"), assess_value=ev(av), total_duty=ev(td),
                       bcd_rate=ev("15"), bcd_amount=ev(b), sws_amount=ev(s), igst_rate=ev("18"), igst_amount=ev(ig))
              for i, (av, td, b, s, ig) in enumerate(DUTIES)]
    return BoeExtraction(summary=summary, duty_items=duties,
                         invoice_pages=[InvoicePage(invoice_sno=ev("1"), invoice_no=ev("BYA48607"), header=header, items=items)])


def checks_of(ex):
    return {i.check for i in run_all_checks(ex)}


# ---------------------------------------------------------------- positive
def test_golden_passes_every_check():
    assert run_all_checks(golden()) == []


def test_be1_valuation_with_misc_and_freight_in_other_currency():
    """BE1 invoice 813591: EUR invoice, USD freight, misc charge, 0.0708% insurance."""
    ex = golden()
    ex.summary.exchange_rates = [ev("1 EUR=89.9INR"), ev("1 USD=87.1INR")]
    h = ex.invoice_pages[0].header
    h.inv_value, h.freight, h.insurance = ev("19694.73"), ev("479.43"), ev(".0708%")
    h.invoice_currency, h.freight_currency, h.misc_charge, h.assessable_value = ev("EUR"), ev("USD"), ev("286.93"), ev("1839381.39")
    from checks import check_valuation
    assert check_valuation(ex) == []


def test_parse_rates_per_100():
    assert parse_rates(["100 JPY=58.65INR"])["JPY"] == __import__("decimal").Decimal("0.5865")


# ---------------------------------------------------------------- negative (realistic LLM mistakes)
def test_digit_swap_in_amount():
    ex = golden(); ex.invoice_pages[0].items[3].amount = ev("43390.74")
    assert {"item_arith", "invoice_total"} <= checks_of(ex)


def test_wrong_quantity():
    ex = golden(); ex.invoice_pages[0].items[15].quantity = ev("84")
    issues = run_all_checks(ex)
    assert any("items[15].quantity" in p for i in issues for p in i.paths)


def test_dropped_item():
    ex = golden(); ex.invoice_pages[0].items.pop(5)
    assert {"count", "invoice_total"} <= checks_of(ex)


def test_igst_taken_from_wrong_column():
    ex = golden(); ex.duty_items[0].igst_amount = ev("8450.2")  # read SWS column instead
    assert "duty_igst" in checks_of(ex) and "duty_total" in checks_of(ex)


def test_decimal_point_slip_in_assess_value():
    ex = golden(); ex.duty_items[14].assess_value = ev("8295.78")
    assert {"av_ratio", "duty_bcd"} <= checks_of(ex)


def test_rows_swapped_between_part2_and_part3():
    ex = golden()  # model mislabels item numbers: block 1 and block 16 get each other's ITEMSN
    ex.duty_items[0].itemsn, ex.duty_items[15].itemsn = ev("16"), ev("1")
    assert "av_ratio" in checks_of(ex)


def test_wrong_currency_rate_unit():
    ex = golden(); ex.summary.exchange_rates = [ev("1 JPY=58.65INR")]
    assert "valuation" in checks_of(ex)


def test_challan_mismatch():
    ex = golden(); ex.summary.challan_amount = ev("745040")
    assert "challan" in checks_of(ex)


# ---------------------------------------------------------------- evidence
def test_evidence_found_and_missing():
    page = "BYA48607  14482.490000  64.000000  926879.36  NOS"
    ok = ItemLine(sno=ev("1"), cth=ev("87089900"), description=ev("x"), unit_price=ev("14482.49"),
                  quantity=ev("64"), uqc=ev("NOS"), amount=ev("926879.36"))
    bad = copy.deepcopy(ok); bad.amount = ev("926879.63")
    miss = {i.paths[0] for i in evidence_issues(bad, page)}
    assert "amount" in miss and "unit_price" not in miss and "quantity" not in miss and "uqc" not in miss
