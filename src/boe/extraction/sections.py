"""Which letter each Part IV section carries in a given PDF.

The Bill of Entry form changed between versions: e.g. supporting documents are "L." on the 2025 form and "M."
on the 2026 form (which also gained a "G. Scheme notification" section). So letters are read from the PDF text,
and sections are identified by their TITLE.
"""
from __future__ import annotations

import re

# key -> pattern on the printed title; checked in order (constituents/control before the plain declaration)
PART4_TITLES: list[tuple[str, str]] = [
    ("svb", r"^SVB"),
    ("previous_be", r"^PREVIOUS BE"),
    ("reimport", r"^RE-IMPORT"),
    ("manufacturer", r"MANUFACTURER"),
    ("accessory", r"^ACCESSORY"),
    ("licence", r"^LICENCE"),
    ("scheme_notification", r"^SCHEME NOTIFICATION"),
    ("certificate", r"^CERTIFICATE"),
    ("hss", r"^HSS"),
    ("sw_constituents", r"CONSTITUENTS"),
    ("sw_control", r"CONTROL"),
    ("sw_declaration", r"^SINGLE WINDOW DECLARATION$"),
    ("supporting", r"^SUPPORTING DOCUMENTS"),
    ("containers", r"^CONTAINER DETAILS"),
    ("invoices", r"^INVOICE DETAILS"),
]
_HEAD = re.compile(r"^([A-Z])\.\s*(.+?)\s*[\*#]*$")


def part4_letters(page_texts: list[str]) -> dict[str, str]:
    """{section key: printed letter} from the Part IV pages' text, e.g. {'svb': 'A', ..., 'supporting': 'M'}."""
    out: dict[str, str] = {}
    for text in page_texts:
        flat = re.sub(r"\s+", " ", text)
        if "PART - IV - ADDITIONAL DETAILS" not in flat:
            continue
        for line in text.splitlines():
            m = _HEAD.match(line.strip())
            if not m:
                continue
            title = re.sub(r"\s+", " ", m.group(2).upper()).strip()
            for key, pat in PART4_TITLES:
                if re.search(pat, title):
                    out.setdefault(key, m.group(1))
                    break
    return out
