"""Local server for the BOE viewer: serves the page and runs PDF extraction.

    python server.py [--port 8765]

The Gemini key comes from the browser (X-Gemini-Key header, kept in the browser's localStorage) or from the
GEMINI_API_KEY environment variable. It is never written to disk or logged.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

import extract_service as svc
from report import build_report

HERE = os.path.dirname(os.path.abspath(__file__))
UPLOADS = os.path.join(HERE, "uploads")
MAX_MB = int(os.environ.get("MAX_UPLOAD_MB", "300"))      # largest PDF accepted (default 300 MB)
MAX_BYTES = MAX_MB * 1024 * 1024
CHUNK = 1024 * 1024


def read_body(rfile, length: int) -> bytes:
    """Read a large request body in 1 MB chunks (avoids one huge blocking read)."""
    buf = bytearray()
    while len(buf) < length:
        chunk = rfile.read(min(CHUNK, length - len(buf)))
        if not chunk:
            raise ConnectionError("Upload was interrupted.")
        buf.extend(chunk)
    return bytes(buf)
ID_RE = re.compile(r"^[0-9a-f]{12}$")
JOBS: dict[str, dict] = {}
LOCK = threading.Lock()


def save_doc(doc: dict) -> str:
    os.makedirs(UPLOADS, exist_ok=True)
    ident = (doc["boe"]["portCode"], doc["boe"]["beNo"], doc["boe"]["beDate"])
    for name in os.listdir(UPLOADS):                       # re-uploading the same BE replaces it
        if name.endswith(".json"):
            try:
                old = json.load(open(os.path.join(UPLOADS, name), encoding="utf-8"))
                if (old["boe"]["portCode"], old["boe"]["beNo"], old["boe"]["beDate"]) == ident:
                    os.remove(os.path.join(UPLOADS, name))
            except Exception:  # noqa: BLE001
                pass
    doc_id = uuid.uuid4().hex[:12]
    doc["id"] = doc_id
    doc["uploadedAt"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(os.path.join(UPLOADS, doc_id + ".json"), "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False)
    return doc_id


EDIT_DENY_TOP = {"id", "label", "short", "sourceFile", "uploaded", "quality", "conf", "edits", "uploadedAt"}
KEY_RE = re.compile(r"^[A-Za-z0-9_]+$")


def _locate(doc: dict, path: str):
    """Walk a dotted path to (container, key). Only existing data may be changed (a missing dict key may be created)."""
    toks = path.split(".")
    if not path or toks[0] in EDIT_DENY_TOP or any(not t for t in toks):
        raise ValueError("That field cannot be edited.")
    o = doc
    for k in toks[:-1]:
        o = o[int(k)] if isinstance(o, list) else o[k]
    last = toks[-1]
    if isinstance(o, list):
        key = int(last)
        if not 0 <= key < len(o):
            raise ValueError("No such row.")
        return o, key
    if isinstance(o, dict):
        if not KEY_RE.match(last):
            raise ValueError("Bad field name.")
        return o, last
    raise ValueError("That field cannot be edited.")


def apply_edit(doc_id: str, path: str, value, revert: bool) -> dict:
    fp = os.path.join(UPLOADS, doc_id + ".json")
    with LOCK:
        doc = json.load(open(fp, encoding="utf-8"))
        try:
            box, key = _locate(doc, path)
        except (KeyError, IndexError, ValueError, TypeError) as e:
            raise ValueError(str(e) or "That field cannot be edited.")
        edits, conf = doc.setdefault("edits", {}), doc.setdefault("conf", {})
        current = box[key] if (isinstance(box, list) or key in box) else None
        if isinstance(current, (dict, list)):
            raise ValueError("That field cannot be edited.")
        if revert:
            rec = edits.pop(path, None)
            if rec is None:
                raise ValueError("Nothing to revert.")
            box[key] = rec["orig"]
            if rec.get("origConf") is None:
                conf.pop(path, None)
            else:
                conf[path] = rec["origConf"]
        else:
            if value is not None and (isinstance(value, bool) or not isinstance(value, (str, int, float))):
                raise ValueError("Value must be text or a number.")
            if isinstance(value, str) and len(value) > 5000:
                raise ValueError("Value is too long.")
            rec = edits.get(path) or {"orig": current, "origConf": conf.get(path)}
            box[key] = value
            if value == rec["orig"]:                       # edited back to the extracted value
                edits.pop(path, None)
                if rec.get("origConf") is None:
                    conf.pop(path, None)
                else:
                    conf[path] = rec["origConf"]
            else:
                rec["at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                edits[path] = rec
                conf[path] = {"s": 1.0, "b": "edited", "r": []}
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False)
        return {"ok": True, "conf": conf.get(path), "edit": edits.get(path)}


def list_docs() -> list[dict]:
    out = []
    if os.path.isdir(UPLOADS):
        for name in sorted(os.listdir(UPLOADS)):
            if ID_RE.match(name[:-5]) and name.endswith(".json"):
                try:
                    out.append(json.load(open(os.path.join(UPLOADS, name), encoding="utf-8")))
                except Exception:  # noqa: BLE001
                    pass
    return sorted(out, key=lambda d: d.get("uploadedAt", ""), reverse=True)


def run_job(job_id: str, pdf: bytes, filename: str, key: str, with_eval: bool):
    def progress(done, total, msg, cost):          # cost: per-call events + totals (see cost.py)
        with LOCK:
            JOBS[job_id].update(done=done, total=total, message=msg, cost=cost)

    try:
        doc = asyncio.run(svc.extract(pdf, filename, key, with_eval, progress))
        doc_id = save_doc(doc)
        with LOCK:
            JOBS[job_id].update(status="done", doc=doc, docId=doc_id)
    except svc.ExtractionError as e:
        with LOCK:
            JOBS[job_id].update(status="error", code=e.code, error=str(e))
    except Exception as e:  # noqa: BLE001
        msg = str(e).replace(key, "***") if key else str(e)
        with LOCK:
            JOBS[job_id].update(status="error", code="failed", error="Extraction failed: " + msg[:400])


class Handler(BaseHTTPRequestHandler):
    server_version = "BoeViewer/1.0"

    def log_message(self, fmt, *args):  # never log headers/keys
        pass

    # ---- helpers
    def send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        host = self.headers.get("Host", "")
        return origin in (f"http://{host}",)

    # ---- routes
    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html", "/boe_viewer.html"):
            body = open(os.path.join(HERE, "boe_viewer.html"), "rb").read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/config":
            self.send_json({"serverKey": bool(os.environ.get("GEMINI_API_KEY")),
                            "executorModel": svc.EXECUTOR_MODEL, "evaluatorModel": svc.EVALUATOR_MODEL,
                            "maxUploadMb": MAX_MB, "maxPages": svc.MAX_PAGES})
        elif path == "/api/docs":
            self.send_json(list_docs())
        elif path.startswith("/api/jobs/"):
            with LOCK:
                job = JOBS.get(path.rsplit("/", 1)[-1])
                job = dict(job) if job else None
            if job is None:
                return self.send_json({"error": "unknown job"}, 404)
            self.send_json(job)
        else:
            self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/check-key":
            if not self.origin_ok():
                return self.send_json({"error": "bad origin"}, 403)
            return self.send_json(svc.check_key(self.headers.get("X-Gemini-Key", "").strip()))
        m = re.match(r"^/api/docs/([0-9a-f]{12})/edit$", path)
        if m:
            if not self.origin_ok():
                return self.send_json({"error": "bad origin"}, 403)
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > 200_000:
                return self.send_json({"error": "bad size"}, 413)
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                result = apply_edit(m.group(1), str(body.get("path", "")), body.get("value"), bool(body.get("revert")))
            except FileNotFoundError:
                return self.send_json({"error": "Unknown bill."}, 404)
            except (ValueError, json.JSONDecodeError) as e:
                return self.send_json({"error": str(e)[:200]}, 400)
            return self.send_json(result)
        if path == "/api/report":
            if not self.origin_ok():
                return self.send_json({"error": "bad origin"}, 403)
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > 8 * 1024 * 1024:
                return self.send_json({"error": "bad size"}, 413)
            try:
                doc = json.loads(self.rfile.read(length).decode("utf-8"))
                assert isinstance(doc, dict) and isinstance(doc.get("boe"), dict)
                body = build_report(doc)
            except Exception as e:  # noqa: BLE001
                return self.send_json({"error": "Could not build the report: " + str(e)[:200]}, 400)
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if path != "/api/extract":
            return self.send_json({"error": "not found"}, 404)
        if not self.origin_ok():
            return self.send_json({"error": "bad origin"}, 403)
        key = self.headers.get("X-Gemini-Key", "").strip() or os.environ.get("GEMINI_API_KEY", "")
        if not key:
            return self.send_json({"code": "no_key", "error": "No AI Key provided."}, 400)
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BYTES:
            return self.send_json({"code": "too_big", "error": f"PDF must be between 1 byte and {MAX_MB} MB."}, 413)
        try:
            pdf = read_body(self.rfile, length)
        except ConnectionError as e:
            return self.send_json({"code": "interrupted", "error": str(e)}, 400)
        if not pdf.startswith(b"%PDF"):
            return self.send_json({"code": "bad_pdf", "error": "That file is not a PDF."}, 400)
        filename = unquote(self.headers.get("X-Filename", "upload.pdf"))[:200]
        with_eval = self.headers.get("X-Eval", "0") == "1"
        job_id = uuid.uuid4().hex[:12]
        with LOCK:
            for k in [k for k, j in JOBS.items() if time.time() - j["created"] > 3600]:
                del JOBS[k]
            JOBS[job_id] = {"status": "running", "done": 0, "total": 0, "message": "Starting", "created": time.time()}
        threading.Thread(target=run_job, args=(job_id, pdf, filename, key, with_eval), daemon=True).start()
        self.send_json({"jobId": job_id})

    def do_DELETE(self):
        m = re.match(r"^/api/docs/([0-9a-f]{12})$", urlparse(self.path).path)
        if not m or not self.origin_ok():
            return self.send_json({"error": "not found"}, 404)
        try:
            os.remove(os.path.join(UPLOADS, m.group(1) + ".json"))
        except FileNotFoundError:
            pass
        self.send_json({"ok": True})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    print(f"BOE viewer on http://127.0.0.1:{args.port}  (models: {svc.EXECUTOR_MODEL} / {svc.EVALUATOR_MODEL}; limits: {MAX_MB} MB, {svc.MAX_PAGES} pages)")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
