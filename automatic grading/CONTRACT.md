# Automatic grading implementation contract

This application is isolated from the existing generator and OCR source. All code, runtime data, model downloads, tests and documentation belong under this directory. PDF files are imported by byte content and SHA-256; originals are never edited. No paid APIs or external inference services are used.

## Architecture and ownership

- `app/server.py`, `app/database.py`, `app/auth.py`: FastAPI API, SQLite and role/session authorization.
- `app/documents.py`, `app/documents_permissive.py`, `app/grading.py`, `app/ocr.py`, `app/schemas.py`: PDFium/ReportLab rendering/reports, strict scoring, free local recognition (GLM-OCR with a PaddleOCR-VL second opinion), validation.
- `app/paper.py`: printed-worksheet uploads: page alignment to the original render, wrong-worksheet rejection, removal of printing, isolation of new marks and circled-option detection.
- `app/samples.py`: hash-bound draft sample presets requiring teacher confirmation.
- `static/index.html`, `static/app.js`, `static/styles.css`, `static/ink.js`, `static/session.js`: dependency-free browser client, pointer/stylus canvas and stale-session response guard. `static/brand` holds the GeniusBees logo and favicon, byte-identical to the worksheet generator's.
- `tools/`, `tests/`, `docs/`, deployment files: standalone setup and verification.

Coordinates always use page-relative numbers 0..1. A question is `{id,label,page,rect:{x,y,w,h},kind,expected,points,tolerance,case_sensitive,options}`. Page is zero-based. Kinds: `number`, `text`, `choice`, `manual`. Expected is a list of accepted strings (never substring/fuzzy matching). Options are `{value,label,rect?}`. Manual is for tracing/drawing or free responses requiring judgment. Students never receive expected, tolerance, or case_sensitive. Teacher must explicitly confirm keys before publishing. All six bundled sample presets import as unpublished drafts requiring confirmation.

An answer is `{text,strokes}`. Text is used for typed or selected answers; any handwriting is represented by `strokes:[{points:[{x,y,p}],width}]` normalized within the question's rectangle. `p` is pressure 0..1. Width is normalized to region width. Client must clear the alternative modality when switching (do not mix typed text and handwriting). A teacher review is `{question_id,awarded,feedback,recognized_text?}`. Result per question: `{question_id,label,awarded,max_points,status,recognized_text,feedback,source,confidence}`. Status is `correct`, `incorrect`, `partial`, `pending_review`. Pending marks are null, never zero. Summary `{earned,total,pending,graded,total_questions,percentage,final}`; percentage is null until all marks final. `earned` is confirmed points only. Blank answer without ink is zero. Local recognition never receives expected answers or printed worksheet content. A handwritten reading earns marks only when GLM-OCR's reading is complete, well formed, has minimum token probability of at least 0.90 and matches the key. It is marked wrong (zero) only when GLM-OCR is at least 0.95, PaddleOCR-VL independently reads the same value at at least 0.75, and the reading is not a near miss: a difference only in spacing or punctuation, or, for text answers, one letter. The second model runs only for such differing readings and also never receives the key. For paper answers it reads the untouched photo of the same area rather than the isolated marks, so a mark-isolation error cannot be repeated by both models. Everything else (models unavailable, errors, uncertainty, disagreement, near misses) remains pending. Do not claim model probabilities are calibrated accuracy.

A printed-worksheet submission (`submission_mode` `paper`) stores the original uploads and each aligned page. Per question, evidence is `hidden` (not fully in the photo: pending), `blank` (no new marks: zero, except manual questions stay pending), `faint` (pending) or `ink` (isolated marks, read as above). Choice questions on paper use marks on the printed option areas: one clear mark is scored, none is zero, several or unclear marks are pending. Result `source` adds `paper` and `paper-choice`. Attempt objects add `submission_mode` (`online`|`paper`) and `paper` (`null` or `{uploaded_at,uploaded_by_role,files,pages:[{index,visible}]}`).

## API (all JSON responses except file routes)

Base `/api`. Errors use `{detail: string}` or standard validation details. Cookies authenticate; mutations require `X-CSRF-Token` from `/session`. Login/register/bootstrap are CSRF-exempt but enforce origin policy. Cookie HttpOnly, SameSite strict; Secure in production. Request bodies are limited to 64 MB.

- `GET /health`: `{ok,ocr:{available,configured,cross_check,provider,engines,message},setup_required}` (no secrets).
- `GET /session`: `{user:null|{id,name,username,role,class_code?},csrf_token}`.
- `POST /bootstrap` `{token,name,username,password}` => session. One first teacher, requires secret printed by `run.py` or configured env; never expose token via HTTP.
- `POST /login` `{username,password}` => session.
- `POST /register` `{name,username,password,class_code}` => student session, linked to teacher by class code.
- `POST /logout` => `{ok:true}`.
- `GET /worksheets` => `{worksheets:[{id,title,published,revision,question_count,total_points,pages,attempt?}],class_code?}`. Teachers see own; students see teacher's published work. Attempt optional summary.
- `GET /samples` => `{samples:[{filename,title,question_count,notes}]}` teacher only.
- `GET /students` => `{students:[{id,name,username}]}` teacher only, own class.
- `POST /samples/import` `{filename}` => worksheet object, not published. Idempotent per owner+hash.
- `POST /worksheets/upload` multipart `file`, `title` => worksheet object. Arbitrary PDF supported; unknown files start with no answer fields; teacher draws them.
- `GET /worksheets/{id}` => worksheet `{id,title,published,revision,pages:[{width,height}],questions,notes}` with private keys filtered for student.
- `GET /worksheets/{id}/pages/{page}.png` => PNG after authorization.
- `GET /worksheets/{id}/pdf` => original PDF after authorization.
- `PUT /worksheets/{id}` `{title,questions,published,keys_confirmed,revision}` => worksheet. Ownership, schema, version check; cannot publish empty/unconfirmed keys.
- `POST /worksheets/{id}/attempts` `{}` => latest existing student attempt, or first new attempt. Snapshot private grading key at start; never trust client rubric. Opening a worksheet does not implicitly create another submission.
- `GET /attempts/{id}` => `{id,worksheet_id,student_name,status,version,submission_mode,paper,answers,questions,results,summary,title,pages,attempt_number,previous_attempt_id,latest_attempt_id,worksheet_published}`. Questions filtered for student, full for teacher. Attempt status `draft`, `grading`, `review`, `graded`.
- `PUT /attempts/{id}/answers` `{version,answers:{question_id:answer}}` => full attempt. Draft only, optimistic version. Full answer set replaces prior; validate IDs and sizes.
- `POST /attempts/{id}/submit` `{version}` => full attempt with status `grading`. Claim atomically; one background worker grades the stored answers with local OCR (tests mark inline). Idempotent once submitted. After a restart, `grading` attempts resume; after three interrupted tries they become `review` with pending marks, never zero.
- `POST /attempts/{id}/paper` multipart `files` (1–10 PDF/JPEG/PNG/WebP files, 20 MB each, 60 MB total) and form `version` => full attempt (`grading`). Student's own draft only. Every worksheet page must be found in the upload (order-tolerant) and the worksheet's own printing must be present; otherwise 422 and the draft is unchanged. Saved online answers are kept but not graded.
- `POST /worksheets/{id}/paper` multipart `files`, form `student_id`, optional `replace_draft` => attempt (201). Teacher owner of a published worksheet; student in their class. Uses the student's empty draft, or a draft with saved answers only when `replace_draft=true`; otherwise creates the next numbered attempt with the current published rubric. 409 while the latest attempt is being marked.
- `GET /attempts/{id}/paper/pages/{page}.png` => aligned uploaded page. `GET /attempts/{id}/paper/answers/{question_id}.png` => the isolated handwriting used for a number/text answer. Attempt authorization applies to both.
- `POST /attempts/{id}/retry` `{version}` => new blank numbered student attempt, or an existing newer draft after repeated requests. Own student only, from `review`/`graded`, worksheet must remain published. Previous answers/results/marks remain unchanged; a new retry snapshots the current published rubric. Only one `draft`/`grading` attempt per student+worksheet. A stale request cannot branch an older completed chain.
- `GET /attempts` => `{attempts:[...summaries...]}` teacher sees their pupils, student their own.
- `POST /attempts/{id}/review` `{version,reviews:[...]}` => full attempt. Teacher owner only; bounds-check marks, append audit records; recalculate totals.
- `POST /attempts/{id}/reopen` `{version}` => full attempt. Teacher only and latest attempt only; clear its marks and return draft; preserve strokes. A reopened paper attempt returns as an online draft; its upload stays on record and in the audit entry. An older submission remains reviewable but cannot be reopened after a newer retry exists.
- `GET /attempts/{id}/report.pdf` => annotated PDF with ink, result regions, score summary page; paper attempts use the aligned uploaded pages as backgrounds; auth enforced.
- `GET /results.csv` => teacher-owned marks, including all attempts, their numbers/IDs and submission type; protect spreadsheet formula injection.

Legacy databases are upgraded at application lifespan startup, not on module import. Before replacing the old one-attempt uniqueness constraint, a verified SQLite backup snapshot is retained under the selected data directory's `backups` folder. The schema rebuild is transactional, preserves all existing IDs/records and checks foreign-key relationships before commit. On failure the migration rolls back. Existing attempts become attempt 1. Use `run.py`, or `uvicorn app.server:create_app --factory --workers 1`; importing `app.server` does not construct a global app.

## Service interfaces used by server

- `documents.import_pdf(content:bytes, directory:Path) -> dict` returns `{sha256,pages,filename}`; stored as `directory/<sha256>.pdf` plus pages `directory/<sha256>-<index>.png`.
- `documents.report_pdf(pdf_path:Path, attempt:dict) -> bytes`.
- `samples.list_samples() -> list[dict]`; `samples.load_sample(filename:str) -> tuple[bytes,dict]`, preset `{title,questions,notes}`.
- `schemas.WorksheetUpdate`, `schemas.AnswersUpdate`, `schemas.ReviewUpdate` Pydantic request models; server may define auth models itself.
- `grading.grade_answers(questions:list, answers:dict, recognizer=None, image_recognizer=None, paper=None, budget_seconds=90) -> dict` returns `{results,summary}`. Default recognizers come from the ocr module. `paper(question)` supplies printed-worksheet evidence instead of answers. OCR runs only on isolated student marks, never on printed glyphs.
- `grading.summarize(results:list) -> dict`.
- `ocr.status() -> dict`; `ocr.recognize(strokes, kind, aspect_ratio=3.0)` and `ocr.recognize_image(image, kind, confirm_image=None)` return `{text,confidence,reliable,certain,exact_agreement,reason,source,readings}` plus, when reliable, a `confirm()` callable that runs the second model on `confirm_image` (paper) or the same image (online ink). Free local models only: pinned revisions and SHA-256, safetensors, no remote code. No student images or keys sent off-server. `tools/download_model.py` installs and verifies models outside runtime.
- `paper.load_pages(uploads)`, `paper.match_pages(references, photos)`, `paper.question_evidence(reference, alignment, question)` and `paper.save_alignment`/`load_alignment` produce printed-worksheet evidence.

## UX

Teacher: setup/login, class join code, import samples/PDF, upload a student's printed worksheet, worksheet editor with draw/add/move/resize/delete answer areas, edit answers/points/kinds/options, explicit confirm/publish, results and pending review with preserved ink, CSV/PDF reports.

Student: join class/login, assigned library, full worksheet with interactive answer regions and choice circles, optional upload of a photographed or scanned printed copy, writing pad for stylus with undo/eraser/clear and optional typing, finger scroll default/pencil ink, server autosave with visible state, explicit submit confirmation, marks including provisional/pending status and feedback. Keyboard access and tablet responsive layout required. Local drafts user+attempt scoped; clear on logout. Handle 409 save conflicts without overwriting unseen work.

No universal handwriting/perfect accuracy promises. Tracing quality/manual answers must receive teacher marks. Number recognition is strict and conservative; correct answer must not bias recognition. No paid API credentials or legacy login dependencies.
