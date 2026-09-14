# Backend reliability and security review

This review covers the separate grading application's Python services, API boundaries, and the browser's session/autosave behavior. The original generator, supplied OCR source, and sample PDFs were not modified.

## Verified boundaries

- Teacher and student authentication uses this application's own SQLite database. Passwords use salted scrypt; opaque session tokens are stored as SHA-256 digests. Cookies are HttpOnly and SameSite Strict. HTTPS deployments must enable Secure cookies.
- A private setup token creates the first teacher only. Students join that teacher's class using a class code. A client-supplied role cannot promote a student.
- Worksheet editing, importing, answer keys, teacher review, and CSV export require teacher authorization. Worksheet and attempt ownership are checked on the server, including page images, original PDFs, and report downloads.
- Student question descriptors omit expected answers, tolerance, and case sensitivity. The server never trusts client-supplied marks or grading keys.
- Attempt creation snapshots the PDF identity, page dimensions, title, questions, marking key, and worksheet revision. Later teacher edits do not change an existing attempt's rubric.
- Answer saves, marking claims, teacher reviews, and reopen actions use SQLite transactions and optimistic versions. Submission is idempotent once claimed. Submitted work cannot be edited unless the teacher reopens it.
- Teacher review audit entries retain both the requested correction and the previous results, including original OCR text, confidence, and source. Reopen records also preserve previous marks and summary.
- Numeric matching preserves signs, decimals, and fractions. Negative or nonfinite marks and marks above the question maximum are rejected. Uncertain handwriting is pending review, with null marks and no final percentage.
- No online inference or paid API is used. The recognition interface receives isolated strokes, question type, and aspect ratio; it does not receive the answer key or printed worksheet background.

## Defects found and corrected during verification

1. Invalid NaN or surrogate-Unicode input made the framework's default validation-error JSON serializer return HTTP 500. Validation responses now omit raw input, normalize error text, and return bounded HTTP 422 details. This also avoids echoing passwords/setup tokens in validation output.
2. Non-ASCII setup/CSRF tokens caused Python's string comparison helper to raise an exception. Token comparisons now use UTF-8 bytes and return HTTP 403 for invalid values.
3. Unbounded waiting for the serialized native PDF engine could occupy the shared request thread pool. PDF import/report admission is now capped at two requests, with HTTP 503 for excess work. Marking also has a separate two-request admission bound.
4. Rotated PDF reports initially used visible-page coordinates with a drawing API that expected unrotated coordinates. A regression verifies normalized ink placement at a known pixel for rotated input and verifies unchanged original bytes. The permissive renderer uses the already displayed, rotation-corrected raster background for reports.
5. Multipart uploads larger than the memory spool threshold used the operating system's default temporary directory. Application lifespan now directs temporary spools into `data/tmp` and restores the prior temporary-directory setting on shutdown.
6. Browser review identified an eight-character password hint against a ten-character API minimum, a 12,000-point stroke limit against the API's 4,000-point limit, missing expired-session transitions, and cross-tab identity handling. These findings were sent to the frontend owner for correction and browser verification.

## PDF implementation and report behavior

The active `app/documents.py` interface delegates to `app/documents_permissive.py`, using PDFium for rendering and ReportLab for generated reports. Runtime services and test fixtures do not require PyMuPDF. All PDFium calls, including object disposal, are protected by one mutex because the library does not permit concurrent calls even on separate documents. [PDFium Python API documentation](https://pypdfium2.readthedocs.io/en/stable/python_api.html)

Import limits are 20 MB, 1–10 pages, and bounded page dimensions. Rendering uses at most 144 DPI and caps the longest page edge at 1,800 pixels. Original downloads remain byte-for-byte identical. Reports contain raster worksheet backgrounds, vector ink/marks, and a searchable results summary; the original worksheet's PDF text/vector objects are not copied into reports. This is an intentional report-quality tradeoff and avoids carrying original PDF scripts, attachments, or interactive actions into generated reports. [ReportLab drawing API](https://docs.reportlab.com/reportlab/userguide/ch2_graphics/)

## Repeatable checks

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_api.py -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_documents_permissive.py -v
```

The API suite covers all six supplied PDFs, import deduplication and renamed-file matching, explicit publication, typed grading, tracing review, session/cookie/CSRF behavior, student and teacher ownership, private-key filtering, version conflicts, rubric snapshots, OCR input separation, audit evidence, restart recovery, PDF integrity/geometry, CSV escaping, malformed values, upload spooling, and PDF concurrency admission.

The dedicated permissive-PDF suite covers all six samples, damaged/encrypted/oversized-page-count rejection, all four page rotations, missing-render-cache recovery, pixel-level ink alignment, searchable report marks, and concurrent rendering requests.

Final verification against the active permissive PDF interface: **26 API tests passed** (18.8 seconds) and **5 dedicated PDF tests passed** (3.9 seconds). The test fixtures and assertions also use permissive PDF libraries.

## Operational limits

- Run one application worker. Startup moves interrupted marking attempts to teacher review; it must not race with a second live worker processing the same database.
- Native PDF parsing/rendering runs in this application's process. Size/page/pixel limits and concurrency bounds are useful protections, but they are not a hard CPU deadline or a substitute for process/container isolation when accepting adversarial PDFs at public scale.
- Handwriting recognition remains fallible. The included small OCR diagnostic is not a calibrated classroom accuracy benchmark, and no universal or zero-error grading claim is warranted.
- The supplied sample rubrics are derived drafts, not client-approved answer keys. Teacher confirmation is required before publication. Tracing quality and method/workings marks require teacher judgment.
- Browser automation verifies logic and simulated pointers; real Apple Pencil/iPad Safari palm rejection, school networking, shared-device logout, and orientation changes still need device acceptance testing.
- Built-in report text fonts use a Latin-1 fallback for unsupported characters. Original worksheet scripts/fonts remain visually preserved in page backgrounds; unsupported student names/feedback in generated report text require a future embedded Unicode report font.

The review and tests provide concrete coverage of the implemented behavior. They are not a penetration test or a promise that every malformed PDF or handwriting style can be handled without error.
