# Extraction-only gold evaluation (isolated)

Read-only evaluation of the **current** production extraction path:

`pdf_parser → document_intelligence → extraction_engine → engineering_tokens`

Does **not** modify production code, flags, models, prediction, takeoff, or geometry.

Artifacts live under `artifacts/`. Do not wire this into the app.
