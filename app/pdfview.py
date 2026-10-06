"""Page rendering and text search for the side-by-side source-PDF viewer (PyMuPDF)."""
from __future__ import annotations

import threading

import pymupdf

_LOCK = threading.Lock()          # PyMuPDF documents are not thread-safe
_CACHE: dict[str, tuple[float, pymupdf.Document]] = {}


def _open(path: str) -> pymupdf.Document:
    import os
    mtime = os.path.getmtime(path)
    hit = _CACHE.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    if len(_CACHE) >= 8:
        _CACHE.clear()
    doc = pymupdf.open(path)
    _CACHE[path] = (mtime, doc)
    return doc


def drop(path: str) -> None:
    with _LOCK:
        hit = _CACHE.pop(path, None)
        if hit:
            hit[1].close()


def page_count(path: str) -> int:
    with _LOCK:
        return len(_open(path))


def page_sizes(path: str) -> list[list[float]]:
    """[[width, height], ...] in points, so the viewer can lay out every page before its image loads."""
    with _LOCK:
        return [[round(p.rect.width, 1), round(p.rect.height, 1)] for p in _open(path)]


def render_page(path: str, number: int, width: int) -> bytes:
    """PNG of 1-based page `number`, `width` pixels wide."""
    with _LOCK:
        doc = _open(path)
        if not 1 <= number <= len(doc):
            raise ValueError("No such page.")
        page = doc[number - 1]
        scale = max(0.2, min(width / page.rect.width, 4.0))
        return page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).tobytes("png")


def find(path: str, pages: list[int], variants: list[str]) -> dict:
    """First page (in the order given) holding any variant, with the match boxes as fractions of the page size."""
    with _LOCK:
        doc = _open(path)
        for n in pages:
            if not 1 <= n <= len(doc):
                continue
            page = doc[n - 1]
            w, h = page.rect.width, page.rect.height
            for v in variants:
                v = v.strip()
                if not v:
                    continue
                rects = page.search_for(v)[:30]
                if rects:
                    return {"page": n, "q": v, "rects": [[round(r.x0 / w, 5), round(r.y0 / h, 5),
                                                          round(r.x1 / w, 5), round(r.y1 / h, 5)] for r in rects]}
    return {"page": None, "rects": []}
