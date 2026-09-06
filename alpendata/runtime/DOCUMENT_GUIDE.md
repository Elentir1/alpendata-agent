# Creating and editing workplace documents

These are local capabilities of your private workspace. No installation or API key is required from the user. Work inside `/state/workspace`. Do not send a document, upload to SharePoint, or claim a download exists without the corresponding authorized tool result.

## Choose the appropriate workflow

Use the original editable format requested by the user: DOCX, XLSX or PPTX. PDF is a separate fixed-layout output. Keep tables, slide text and spreadsheet values editable. Follow a supplied template when one is available; do not replace it with a starter layout. Preserve the user's language, units, dates and actual source facts. Never fill missing client facts with invented details.

The installed Python libraries are `docx`, `openpyxl`, `pptx`, `reportlab` and `pypdf`. Always invoke `/opt/venv/bin/python`: the terminal's login shell may select a different system Python. Do not install packages. LibreOffice, `pdfinfo`, `pdftotext` and `pdftoppm` are available locally. DejaVu Sans regular/bold are in `/usr/share/fonts/truetype/dejavu/`. These tools run without network access.

For a straightforward new document, an optional starter builder takes JSON:

```sh
/opt/venv/bin/python /opt/hermes/alpendata/runtime/document_builder.py specification.json output.docx
```

Use a new output filename; existing files are never overwritten. A successful builder result confirms creation only. Read/check/render the result before publishing. For a template, chart, native slide table or other specific layout, use the installed libraries directly rather than flattening or discarding requested content to fit this helper.

## Word or PDF starter

The JSON accepts `title`, optional `subtitle`, and `sections`. Each section has optional `heading`, `paragraphs` (plain strings), `columns` and `rows` (a rectangular table of strings). Only include facts that the user supplied or your authorized tools retrieved.

```json
{"title":"Session preparation","sections":[{"heading":"Objectives","paragraphs":["Discuss the objectives agreed with the client."]},{"heading":"Agenda","columns":["Topic","Duration"],"rows":[["Progress since the last session","15 minutes"],["Next actions","15 minutes"]]}]}
```

The same structure produces DOCX or PDF according to the output suffix. The PDF escapes plain input text and embeds the font. Long documents flow across pages and table headers repeat. Very wide or tall tables need a deliberate layout with the direct library; do not shrink a large table until it becomes unreadable.

## Excel starter

Use `title` and `sheets`. Each sheet needs `name`, `columns`, rectangular `rows`, and optional numeric `widths` (one width per column). Values retain their numeric/boolean/text types. Plain strings beginning with `=` remain text. Calculations require an explicit object `{"formula":"=SUM(B2:B3)","number_format":"0.0"}`. Use formulas for derived values and label units clearly. Do not replace unknown amounts with zero.

```json
{"title":"Session follow-up","sheets":[{"name":"Sessions","columns":["Session","Hours"],"rows":[["Preparation",1.5],["Coaching",2],["Total",{"formula":"=SUM(B2:B3)","number_format":"0.0"}]],"widths":[36,18]}]}
```

Openpyxl writes formulas but does not calculate them. Recalculate a copy with LibreOffice, reopen it with `openpyxl.load_workbook(..., data_only=True)` and check expected results. Keep formulas in the delivered editable workbook, check they are retained with `data_only=False`, and check print layout. Rows with long wrapped text may need explicit row heights before delivery. Never report a successful calculation based only on a formula string.

## PowerPoint starter

Use `title` and `slides`; each slide has `title` and optional `paragraphs`. There is no automatic cover. Text remains native and editable, on a 16:9 canvas. The helper rejects text that exceeds its simple layout rather than dropping words or silently shrinking the font. Preserve a requested slide count; shorten copy where appropriate, or design a different layout with `python-pptx`.

```json
{"title":"Coaching workshop","slides":[{"title":"Workshop objectives","paragraphs":["Review the team's current priorities.","Agree on practical actions for the coming week."]},{"title":"Next session","paragraphs":["Review the actions and the difficulties encountered."]}]}
```

## Read, render, verify

Read DOCX paragraphs/tables with `docx.Document`, XLSX values and formulas with `openpyxl.load_workbook`, PPTX slide text/tables with `pptx.Presentation`, and PDF text/pages with `pypdf.PdfReader`. Compare titles, sections, values, tables and slide/page counts with the request. For edits, preserve the original and save a new version. Confirm the library supports the features you must preserve before re-saving a complex document.

Render Office files to PDF with a unique temporary LibreOffice profile and a separate output directory. For example, in Python use `tempfile.TemporaryDirectory()` for the profile and `subprocess.run` with an argument list, `timeout=60`, and `check=True`:

```text
/usr/bin/libreoffice -env:UserInstallation=file:///tmp/UNIQUE_PROFILE --headless --convert-to pdf --outdir /state/workspace/review /state/workspace/output.docx
```

Never reuse the literal `UNIQUE_PROFILE`; generate a unique path for each invocation. Inspect the actual output file because LibreOffice may exit successfully without producing it. Use a separate output directory when recalculating XLSX (`--convert-to xlsx`). Check for formula errors and compare known totals after recalculation. Use `pdfinfo`, `pdftotext -layout`, and `pdftoppm -scale-to 1600 -png` for layout inspection. Correct clipping, excessive density or blank pages; do not call visual quality verified if you could only inspect extracted text.

## Publish only completed files

Call `alpendata_publish_document` with the final relative path after checking the file. Publish each requested editable original and only the extra PDFs the user needs. Do not publish temporary previews, specifications, scripts or every intermediate version. Confirm which files were produced, and state any remaining issue relevant to their use. The tool's receipt makes the real download appear in the chat.
