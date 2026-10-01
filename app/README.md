# BOE Viewer with PDF upload

```
cd boe/app
..\files2\.venv\Scripts\python server.py        # then open http://127.0.0.1:8765
```

- **Upload BOE PDF** (button or drag & drop on the home page) sends the PDF to the local server, which runs the
  pipeline in `../files2` plus extra extractors for the other sections (`viewer_schemas.py`), maps the result to the
  viewer's data shape (`to_viewer.py`) and saves it under `uploads/`. Uploaded bills appear in the list next to the two
  built-in ones, with an "Uploaded" badge and a "remove" link.
- **Gemini key**: if none is saved in the browser and `GEMINI_API_KEY` is not set for the server, the page asks for one.
  It is kept in browser localStorage and sent per request; the server never writes it to disk or logs it. A rejected key
  re-opens the prompt. The "AI key" button changes or removes it.
- **Models**: `EXECUTOR_MODEL` (default `gemini-3.8-flash`) and `EVALUATOR_MODEL` (default `gemini-3.1-pro-preview`)
  environment variables. The evaluator only runs when the checkbox in the upload dialog is ticked.
- Uploaded bills show a banner with the field count, failed cross-checks and fields needing review. Item detail pages
  also show the Part III duty figures for uploaded bills.
- Opening `boe_viewer.html` directly as a file still works for the two built-in bills; upload needs the server.
