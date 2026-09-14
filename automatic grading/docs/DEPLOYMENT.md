# Self-hosting and operations

## Scope and costs

There are no paid OCR APIs, no OpenAI/Grok/RapidAPI credentials, no external recognition requests and no dependency on the intern's `.env`. A one-time public model download accesses Hugging Face; actual student inference is local/offline. Hosting, electricity, domain registration, backups and server capacity still have costs.

Start with a small pilot. Plan for a 4-core CPU with **16 GB RAM** and at least 20 GB of free storage: a **planning estimate, not a capacity guarantee**. On the 4-core development laptop with both models loaded, the marking process used about 7 GB of working memory (8.3 GB peak, about 11 GB committed). GLM-OCR and PaddleOCR-VL weights take 4.6 GB on disk; the Python/torch image, caches and uploaded paper evidence use more. On that laptop GLM-OCR took roughly 1–10 seconds per handwritten answer and PaddleOCR-VL roughly 10–25 seconds for each answer that needed a second opinion; the first submission after a restart also loads the models. Submissions are queued: one background worker marks one attempt at a time while the site stays usable. This is not a distributed grading queue; time a real class and add CPU if the queue is too slow.

Use exactly **one application worker/process**. Startup resumes interrupted `grading` attempts; after three interrupted tries an attempt goes to teacher review with pending marks, never zero. Multiple independent workers sharing this database could mistake another worker's active job for interrupted work. Do not use `--workers 4` or deploy multiple replicas without implementing coordinated jobs and a shared database/file store.

Each attempt has a 30-minute handwriting budget; answers not read in time wait for the teacher. Typed and selection answers always receive deterministic marks. Model thread count is `OCR_CPU_THREADS` (default 4; the Compose file sets 2). Confidence floors are `OCR_MIN_CONFIDENCE` (0.90), `OCR_CERTAIN_CONFIDENCE` (0.95) and `OCR_CONFIRM_CONFIDENCE` (0.75); values below their built-in minimums are ignored.

## Windows/private network

Follow README setup. For environment configuration in PowerShell:

```powershell
$env:AG_BOOTSTRAP_TOKEN = 'use-your-own-long-random-secret'
$env:OCR_CPU_THREADS = '2'
.\.venv\Scripts\python run.py --host 0.0.0.0 --port 8001
```

`run.py` reads process environment variables; it does not automatically load `.env`. The `.env.example` file is primarily for Docker Compose. Local HTTP must leave `AG_SECURE_COOKIES` unset/0; a secure-only cookie cannot authenticate over ordinary LAN HTTP. Real student use should move to HTTPS, not publicly expose this development port.

## Docker Compose + HTTPS

The Docker files are supplied deployment configuration. Docker is unavailable in the development workspace, so an image build, DNS and certificate issuance must still be tested on the hosting machine.

1. Install Docker with Compose on your host. Place the `automatic grading` directory there, plus its sibling `sample-worksheets` if using the preset gallery. You may instead upload PDFs through the teacher UI; set/adjust the read-only sample mount accordingly.
2. Copy `.env.example` to `.env` using your editor. Replace the domain with a DNS name pointing to this server, and choose a unique random bootstrap token of at least 32 characters. Keep this file private.
3. Allow inbound TCP 80/443. Do not expose port 8001 or the data volume publicly.
4. From `automatic grading`, run:

```sh
docker compose build
docker compose run --rm grading python tools/download_model.py
docker compose up -d
docker compose logs --tail=50 grading
```

Caddy obtains/manages HTTPS for the configured domain and proxies to the private application port. The named `grading-data` volume persists the database, PDFs and local model across container replacement. The sample PDF mount is read-only. The app container runs as UID 10001 with dropped Linux capabilities; if substituting a host bind mount for the named data volume, arrange filesystem ownership for that UID.

The service sets secure cookies and the explicit public allowed origin. Caddy terminates TLS; origin validation must accept the configured HTTPS origin even when the upstream connection uses HTTP. No cross-origin frontend is needed.

For stronger network privacy, pre-download the model then deny application egress at your firewall while allowing the proxy's certificate traffic. Python model loading uses local-only flags regardless. The browser uses only same-origin scripts, fonts and resources.

## Identity and permissions

- One initial teacher is created with the setup token. Registration never lets a browser choose its role. Students join a teacher with the class code.
- Sessions use random opaque cookies, server-side hashed token storage, 12-hour expiry, HttpOnly, SameSite=strict and production Secure. Passwords use salted scrypt. State-changing authenticated routes require a CSRF token.
- Every worksheet, PDF/page, attempt, report and export is authorized. Students cannot read expected answers or another student's submission.
- Do not share a teacher login with students. Treat the class code as an enrollment invitation, not a teacher credential.
- Additional teachers or password recovery are operator-only tasks on the host:

```sh
python tools/manage_users.py add-teacher teacher2 --name "Second Teacher"
python tools/manage_users.py reset-password student1
```

Passwords are prompted without echo, not accepted as command-line arguments. Resetting revokes that user's existing sessions. Inside Docker use `docker compose exec grading python tools/manage_users.py ...`. The CLI deliberately has no bulk delete/reset database option.

## Data, backups and recovery

Keep the entire `data` directory/volume private. `grading.sqlite3` stores identities, sessions, rubric snapshots, answers, marks and review audit records. `documents` stores immutable original PDFs and rendered pages. `submissions` stores uploaded paper photos/scans and their aligned pages: this is student data. `models` holds optional free weights; cache data can be recreated, but do not mistake student data for disposable cache.

The student-retry update upgrades the old one-attempt database schema automatically on the next server startup. Stop the old server normally before starting updated code. A verified SQLite backup, including committed WAL data, is created under the selected data directory's `backups/before-attempt-history-*.sqlite3` before the transactional migration. Existing accounts, attempt IDs, answers, marks and review audit records are preserved; old submissions become attempt 1. The migration is idempotent and rolls back if verification fails. Keep this backup private and retain your normal full-data backup as well. Do not delete the database or create a new classroom for this upgrade. The later paper-upload update only adds three attempt columns (`submission_mode`, `paper`, `grading_tries`) at startup, without changing existing rows.

The supplied `run.py` remains the normal entry point. If using Uvicorn directly, use `uvicorn app.server:create_app --factory --workers 1` and your host/port settings; there is no module-level `app` instance.

For a simple consistent backup, schedule downtime, stop the application container/process, and copy/archive the **whole data volume/directory** to encrypted backup storage using your hosting backup system. SQLite uses WAL: copying only the `.sqlite3` file while the process is writing is not a safe backup. Alternatively use SQLite's online backup API with a coordinated document backup. Test restoration into a separate private environment before relying on backups.

Do not run `docker compose down -v` unless you explicitly intend to delete your stored classroom data. The supplied workflows never require that command. Do not expose filesystem or SQL admin tools publicly.

Limit operating-system access to the data and log directories. Use disk encryption/backups appropriate for student records. The application has no automated retention deletion policy; the institution must choose retention and consent/parental requirements before launch. A logout clears that account's local recovery copies in the browser; shared devices should always log out and use separate browser profiles where feasible.

## Accuracy and acceptance

No answer-key model can replace teacher confirmation for arbitrary worksheet types. Collect teacher-approved keys and a representative set of actual student handwriting on the intended iPads/tablets. Measure both false accepted answers and review rate; a model token probability is not an empirical accuracy percentage. Do not lower `OCR_MIN_CONFIDENCE` simply to make the dashboard look more automatic.

The local models are general document OCR models, used here for short English words and numbers. They are not validated for Sinhala handwriting, essays, arbitrary mathematical notation or tracing quality. Paper photos must show the whole page flat and in focus; a photo of a different worksheet is refused. Uploads are limited to 10 files, 20 MB each and 64 MB per request, which the supplied Caddyfile matches. Text and numeric typed input remain available; subjective answers use manual rubrics. A correctly recognized answer matching a wrong teacher key is still graded incorrectly, which is why publication confirmation is mandatory.

The PDF report preserves the worksheet appearance using a 144-DPI rendered background (capped at 1800 pixels), with vector ink/marks and searchable summary text. Original PDF downloads remain byte-identical. The report does not copy original PDF JavaScript, attachments or interactive actions. Its generated text currently uses a basic Latin font; non-Latin names/feedback can show replacement characters even though UTF-8 values remain intact in the browser/database/CSV. Verify this before deploying in a Sinhala-language class; appropriate embedded Unicode fonts/shaping are a separate enhancement.

## Dependencies, licenses and official references

- [GLM-OCR model card](https://huggingface.co/zai-org/GLM-OCR) (MIT) and [PaddleOCR-VL-1.5 model card](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.5) (Apache-2.0). Both load through Transformers from local files with `trust_remote_code=False`.
- [OpenCV license](https://opencv.org/license/) (Apache-2.0); OpenCV aligns uploaded paper photos.
- [pypdfium2 licensing](https://github.com/pypdfium2-team/pypdfium2#licensing) describes the renderer and bundled third-party notices; [ReportLab package information](https://pypi.org/project/reportlab/4.4.7/) identifies its BSD-licensed PDF toolkit. The final app, preview tools and tests do not depend on PyMuPDF. Preserve all required notices when distributing dependencies.
- [PDFium thread-safety guidance](https://pypdfium2.readthedocs.io/en/stable/python_api.html#incompatibility-with-threading) requires serialization. This application guards native PDF engine calls with a shared lock and limits admission to PDF processing operations.
- [FastAPI release package](https://pypi.org/project/fastapi/0.135.1/), [Uvicorn release package](https://pypi.org/project/uvicorn/0.41.0/) and [multipart package](https://pypi.org/project/python-multipart/0.0.22/) are pinned in requirements and exercised locally. Review security advisories and rebuild/test before public deployment; a version pin is not a promise of permanent security.
- [Caddy reverse proxy documentation](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy) and [automatic HTTPS documentation](https://caddyserver.com/docs/automatic-https) cover the supplied proxy pattern.

Preserve required dependency/model copyright and license notices in distributions. The client must own/have rights to the worksheet artwork it publishes. No existing worksheet/artwork licensing was changed.
