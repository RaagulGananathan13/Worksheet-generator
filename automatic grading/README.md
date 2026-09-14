# GeniusBees online worksheets

A separate student/teacher portal for the PDFs produced by the existing worksheet generator. Nothing in `frontend`, `backend`, `OCR` or the supplied PDFs needs to change. The integration boundary is the exported PDF, not the generator's internal DOM or its staff login. The portal shows the same GeniusBees logo and favicon as the generator.

**First time testing?** Follow [Testing from start to finish](TESTING-FROM-START-TO-FINISH.md). It covers setup, both ways of answering (online and printed paper), marks, exports and troubleshooting.

**Updating an existing classroom?** Follow [What to do next](WHAT-TO-DO-NEXT.md) to restart safely, install the new handwriting models and test paper uploads.

## What is implemented

- Teacher setup, student class-code registration, secure password hashing and private cookie sessions.
- Import the six supplied samples, or upload another PDF (up to 20 MB, 10 pages).
- Teacher-defined answer regions, accepted answers, number tolerance, points and explicit rubric confirmation before publication.
- **Two ways to answer.**
  - *Online:* the PDF page as background with pressure-aware pencil/mouse ink, optional finger writing, eraser, undo, typing and tap-to-choose options.
  - *On paper:* print the worksheet, write on it, then upload a photo or scan (PDF, JPG or PNG). A student uploads inside their own attempt; a teacher can upload for any student in the class. The page is aligned to the original, a different worksheet is rejected, the printing is removed and only the student's new marks are read. Circled or ticked printed options are detected without reading them.
- **Free local handwriting reading.** GLM-OCR reads every handwritten answer. When a confident reading differs from the answer key, PaddleOCR-VL, a separately trained model, reads the answer again. No paid API or cloud service is used, and the models never receive the answer key.
- **Marking rules.** Typed and tapped answers are compared exactly. Handwriting is marked correct when the confident reading matches the key. It is marked wrong only when both models independently read the same clearly different answer with high confidence. Uncertain, disputed or near-miss readings (a stray dot, or a word one letter away from the key) wait for the teacher, never an automatic zero. For paper answers the second model reads the original photo, so both models cannot inherit the same image-cleaning mistake. Blank answers receive zero.
- Background marking queue (a submission shows "being marked" and updates when done), versioned autosave, account-scoped local recovery, immutable rubric snapshots, **Try again** attempts with full history, teacher corrections with audit records, CSV exports and annotated PDF reports. Paper attempts show the student's own page in the report.

This is **not** a universal, error-free handwriting examiner. Handwriting recognition can be wrong. The cross-check makes an automatic zero require strong agreement, but no model can guarantee it. Tracing, drawings and free-form writing always need a teacher. A score is provisional until every question has a mark. Measure accuracy on your own pupils' writing before relying on unattended marks: see [handwriting evaluation](docs/OCR-EVALUATION.md).

## Windows: run locally

Use Python 3.13. From PowerShell (replace `C:\path\to` with the folder where you cloned or copied the repository):

```powershell
cd 'C:\path\to\Worksheet-generator\automatic grading'
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python run.py
```

Open `http://127.0.0.1:8001`. Copy the first-teacher setup token **from your local console** into the setup form, create the teacher, then use the displayed class code to register students in another browser/session. Passwords require at least 10 characters. Existing generator accounts are intentionally separate.

The application works without handwriting models installed: students can still write, type, choose, upload paper and submit; handwritten answers then wait for the teacher. To enable free local handwriting reading:

```powershell
.\.venv\Scripts\python -m pip install -r requirements-ocr.txt
.\.venv\Scripts\python tools/download_model.py
```

The one-time download is about 4.6 GB (GLM-OCR 2.65 GB and PaddleOCR-VL 1.92 GB), fetched in resumable pieces from pinned revisions and checked against pinned SHA-256 fingerprints. Everything stays inside this folder. Recognition then runs offline on your own CPU: there is no per-page charge, but hosting, storage and electricity still cost money. The first handwritten submission after a restart loads the models and takes longer. `tools/download_model.py --verify-only` re-checks installed files without network access. Models are not stored in Git: each computer downloads them once.

For an iPad on the same private network, start with `run.py --host 0.0.0.0` and open your computer's LAN IP on port 8001. Only allow this through the firewall on a trusted private network. Use HTTPS for a real deployment. Actual Apple Pencil/Safari hardware acceptance is still required before classroom launch.

## Teacher workflow

1. Import a sample or upload a blank exported generator PDF. The original header/footer/page size stays in the background.
2. Review every answer region and label. For a new layout, draw regions and enter the answer key. Automatic layout/key guessing is deliberately not trusted.
3. Select `number`, exact accepted `text`, `choice`, or `manual`. Add accepted variants and points. Number tolerance is absolute and defaults to zero. Use manual marking for reasoning, drawings, tracing and method marks.
4. Confirm that the answers and marks are correct, then publish. Students in the class can start it online, or print it with **Print / PDF**.
5. For paper worksheets collected in class, open **Student results → Upload a paper worksheet**, choose the worksheet and student, and upload the photo or scan.
6. Review pending answers against the student's ink or paper, award marks and feedback, then export results. **Return for another try** reopens the latest attempt; students can instead choose **Try again** for a new blank attempt that keeps all previous results.

The sample presets contain 82 answer regions: 77 automatic-capable answers and five manual tracing tasks. They are **derived drafts, not teacher-approved keys**. Their exact PDF SHA-256 hashes prevent a changed document from receiving a stale preset. See [sample details](docs/SAMPLES.md).

## Hosting

See [deployment and operations](docs/DEPLOYMENT.md). The included Docker Compose setup uses one application process with one background marking worker, a persistent SQLite/data volume, CPU handwriting models and a Caddy HTTPS proxy. A modest classroom pilot is the intended starting deployment, not a horizontally scaled examination service.

PDF processing uses PDFium/pypdfium2 and ReportLab; photo alignment uses OpenCV. Original PDF downloads stay byte-identical. Preserve the libraries' and models' license notices: GLM-OCR is MIT licensed and PaddleOCR-VL is Apache-2.0 licensed.

## Verification and documentation

```powershell
.\.venv\Scripts\python -m unittest discover -s tests -v
node --test tests/ink.test.mjs tests/session.test.mjs
node tools/browser_smoke.cjs
node tools/student_retry_smoke.cjs
node tools/paper_upload_smoke.cjs
.\.venv\Scripts\python tools/evaluate_handwriting.py --photos
.\.venv\Scripts\python tools/evaluate_handwriting.py --demos --limit 30 --output artifacts/handwriting-evaluation-demos.json
.\.venv\Scripts\python tools/preview_regions.py
```

- [Existing project architecture and file map](docs/PROJECT-ANALYSIS.md)
- [Intern OCR audit and what was reused](docs/LEGACY-OCR-AUDIT.md)
- [Handwriting model selection and evaluation](docs/OCR-EVALUATION.md)
- [Sample rubrics](docs/SAMPLES.md)
- [API and data contract](CONTRACT.md)
- [Deployment, security and backups](docs/DEPLOYMENT.md)
- [Verification record and launch checklist](docs/VERIFICATION.md)

Runtime records live in `data/grading.sqlite3`, imported worksheets in `data/documents`, uploaded paper evidence in `data/submissions` and models in `data/models`. Keep the entire data directory/volume private and backed up. Do not expose it as a web directory or commit it to Git. This application deliberately provides no bulk deletion endpoint.
