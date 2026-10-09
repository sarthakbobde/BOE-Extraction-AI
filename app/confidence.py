"""Per-field confidence for the viewer.

Three sources, all keyed by the viewer's dotted data path (e.g. "invoices.0.valuation.freight"):
  * pipeline scores (Parts I-III): evidence gate + cross-checks + optional evaluator + the model's own doubt
  * text match (everything else): does the value literally appear in the PDF text layer?
  * the model's own rating ("model"): values too generic to find in the PDF text (flags, zeros, small numbers)
    get High unless the model listed them as doubts; any doubt (medium/low) also caps the scores above.

A score is {"s": 0..1, "b": "checked" | "text" | "model" | "edited", "r": [reasons]}. The UI shows High (>= 0.8),
Medium (>= 0.5) or Low. Blank values and structural labels carry no score and no rating.
"""
from __future__ import annotations

import re
import sys
import os
from datetime import datetime
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "files2"))
from checks import numbers_on_page  # noqa: E402

REVIEW_BELOW = 0.8
MODEL_HIGH = 0.9                                 # a generic value the model read with confidence
MODEL_CAP = {"medium": 0.7, "low": 0.4}          # the model's own doubt: Medium / Low
TOP_SKIP = {"id", "label", "short", "sourceFile", "uploaded", "quality", "conf", "edits", "uploadedAt",
            "hasPdf", "pageCount", "pageMap", "sectionLetters", "schema", "rated"}
LEAF_SKIP = {"sno", "srNo", "inv", "item", "for", "columns", "title", "code"}
TOKEN = re.compile(r"[A-Z0-9]+")
DATE_FORMATS = ("%d-%b-%Y",)
DATE_VARIANTS = ("%d/%m/%Y", "%d-%m-%Y", "%d-%b-%y", "%d-%b-%Y", "%d.%m.%Y", "%d/%m/%y")


def _leaves(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not path and k in TOP_SKIP:
                continue
            if k in LEAF_SKIP:                       # structural keys, incl. table column headings (a list)
                continue
            yield from _leaves(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _leaves(v, f"{path}.{i}")
    else:
        yield path, obj


def _parse_date(s: str):
    for f in DATE_FORMATS:
        try:
            return datetime.strptime(s, f)
        except ValueError:
            pass
    return None


class Scorer:
    def __init__(self, full_text: str):
        up = re.sub(r"\s+", " ", full_text.upper())
        self.text = up
        self.tokens = set(TOKEN.findall(up))
        self.compact = re.sub(r"[^A-Z0-9]", "", up)          # lets a value that wraps across lines still match
        self.numbers = numbers_on_page(full_text)

    def number(self, v) -> tuple[float, list[str]] | None:
        if v == 0 or (isinstance(v, int) and abs(v) < 10):
            return None                                    # too generic to say anything
        try:
            d = Decimal(str(v))
        except Exception:  # noqa: BLE001
            return None
        if d in self.numbers:                              # Decimal('14482.49') == Decimal('14482.490000')
            return 0.9, []
        return 0.45, ["number not found in the PDF text"]

    def string(self, s: str) -> tuple[float, list[str]] | None:
        s = s.strip()
        if not s:
            return None
        dt = _parse_date(s)
        if dt:
            if any(dt.strftime(f).upper() in self.text for f in DATE_VARIANTS):
                return 0.9, []
            return 0.45, ["date not found in the PDF text"]
        compact = re.sub(r"[^A-Z0-9]", "", s.upper())
        if len(compact) >= 6 and compact in self.compact:
            return 0.9, []
        toks = [t for t in TOKEN.findall(s.upper()) if len(t) >= 2]
        if not toks:
            return None                                    # single-letter flags etc.: nothing meaningful to match
        cov = sum(t in self.tokens for t in toks) / len(toks)
        if cov >= 0.999:
            return 0.9, []
        return round(0.4 + 0.5 * cov, 2), [f"only {round(cov * 100)}% of the words appear in the PDF text"]


def score_doc(doc: dict, full_text: str) -> dict[str, dict]:
    sc = Scorer(full_text)
    out: dict[str, dict] = {}
    for path, v in _leaves(doc):
        if v is None or isinstance(v, bool):
            continue
        if path.startswith("invoices.") and re.search(r"\.items\.\d+\.0$", path):
            continue                                       # item serial number
        if isinstance(v, str) and not v.strip():
            continue                                       # blank: nothing was extracted, so nothing to rate
        if isinstance(v, (int, float)):
            r = sc.number(v)
        elif isinstance(v, str):
            r = sc.string(v)
        else:
            r = None
        if r:
            out[path] = {"s": r[0], "b": "text", "r": r[1]}
        else:                                              # too generic to find in the PDF text: the model's own word
            out[path] = {"s": MODEL_HIGH, "b": "model", "r": []}
    return out


def apply_doubts(conf: dict[str, dict], doubts: list[tuple[str, str]]) -> None:
    """Lower a field's score to Medium / Low where the model said it was unsure (never raises a score)."""
    for path, level in doubts:
        cap = MODEL_CAP.get(level)
        if cap is None:
            continue
        note = f"AI is not fully sure ({level})"
        cur = conf.get(path)
        if cur is None:
            conf[path] = {"s": cap, "b": "model", "r": [note]}
        elif cur["s"] > cap:
            conf[path] = {**cur, "s": cap, "r": list(cur["r"]) + [note]}


def resolves(doc: dict, path: str) -> bool:
    o = doc
    for k in path.split("."):
        try:
            o = o[int(k)] if isinstance(o, list) else o[k]
        except (KeyError, IndexError, ValueError, TypeError):
            return False
    return True
