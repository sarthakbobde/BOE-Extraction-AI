"""Where things live on disk. The data folder (uploaded bills, sample PDFs, resume cache) is git-ignored."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]                       # repository root
DATA = Path(os.environ.get("BOE_DATA_DIR") or ROOT / "data")     # override with BOE_DATA_DIR
UPLOADS = DATA / "uploads"                                       # <id>.json (extracted bill) + <id>.pdf (original)
CACHE = UPLOADS / ".cache"                                       # per-page results of an unfinished extraction
SAMPLES = DATA / "samples"                                       # D1.pdf, D2.pdf for the two built-in sample bills
STATIC = Path(__file__).resolve().parent / "web" / "static"      # the web page
