# Verification record and launch gate

Date: 2026-09-14. Application development changes are confined to `automatic grading`; the later user-requested demonstration assets are in the separate `sample-worksheets/student-written-demos` folder. Existing generator, intern OCR source and original six PDFs remain unchanged. This record distinguishes passing software checks from unproven real-classroom OCR accuracy.

## Paper uploads and two-model handwriting reading: current verification

Latest complete run, after the final code change: **127 Python tests passed** in 97.3 seconds, **22 JavaScript tests passed**, the **16-check browser workflow passed**, the **15-check student retry/writing workflow passed**, and the new **11-check paper-upload browser workflow passed**, with no browser JavaScript errors. Both handwriting models passed installation verification against their pinned weights SHA-256: GLM-OCR (526 tensors) and PaddleOCR-VL-1.5 (620 tensors).

- Paper pipeline (`tests/test_paper.py`, 8 tests): synthetic phone photos with perspective, uneven light, blur, noise and JPEG compression align to the original page. The 10 written answer areas are found as ink and the 10 empty ones as blank. Isolated marks overlap the pen strokes, not the printing. A photo of a different GeniusBees worksheet is refused. Also covered: page count, out-of-order pages, PDF scans, EXIF rotation, transparent PNGs, unreadable/GIF/tiny/oversized files, evidence storage, and circled, blank and double-marked options.
- Wrong-worksheet check: all 30 pairings of the six samples, which share one header and footer, scored at most 0.45 printed-tile presence. The six real photos of the right worksheets scored 0.75–1.00. Pages are accepted at 0.60 or more, with a median presence of at least 0.70.
- The 12 synthetic filled demo PDFs, uploaded as paper, all aligned with about 0.15 px error. Every blank answer was detected and every circled choice was read correctly.
- Paper API (`tests/test_paper_api.py`, 7 tests): student uploads are marked from isolated writing and the recognizer never receives keys; correct, confirmed-wrong and uncertain readings; blanks score zero; paper page, isolated-writing and report downloads are authorized; a wrong worksheet or page count leaves the draft unchanged; permissions, CSRF and versions; teacher uploads create numbered attempts, refuse to replace an online draft with saved answers unless confirmed, and refuse while marking or for unpublished worksheets; the background queue marks submissions; restarts resume marking and send repeated failures to review; an existing database gains the new columns without changing rows.
- Recognition and grading rules (`tests/test_ocr.py`, `tests/test_grading.py`): model readiness and integrity checks; the second model runs only when grading asks, on the untouched photo for paper answers; a single-model installation never marks answers wrong; environment settings cannot lower thresholds below their floors; punctuation-only differences, one-letter differences in words and capital-letter differences never become automatic zeros.
- Browser (`tools/paper_upload_smoke.cjs`): GeniusBees logo and favicon, student upload dialog, background marking of a photographed page, zero for empty boxes, aligned paper page, answer crops and isolated writing, no re-upload after hand-in, teacher upload for a student, numbered history and "Paper upload" in the CSV.
- The real-model evaluation found a shared-error case and led to three fixes. A photographed "TEDDY BEAR" whose faint pencil R was partly lost during mark isolation was read as "TEDDY BEAK" by both models. It now goes to teacher review. See [OCR evaluation](OCR-EVALUATION.md) for the model benchmark and the full pipeline results.

These software checks prove the rules and workflows. They do not prove accuracy on your pupils' handwriting, pencils or phone cameras; see the launch gate below.

## Student retries, writing-pad capture and OCR fidelity (earlier update)

Run at that time: **103 Python tests passed** in 32.873 seconds, **22 JavaScript tests passed**, the existing **16-check browser workflow passed**, and the new **15-check student retry/writing workflow passed**. The local OCR packages are installed and model verification passed for **478 tensors**. The missing-dependency failures in the historical guide follow-up below are resolved.

- Student **Try again** creates a blank numbered attempt from review/graded work, with all prior ink, marks, rubric snapshots and review records retained. Fifteen dedicated API/migration tests cover authorization, CSRF, concurrent retries, draft reuse, current-key snapshots, withdrawn worksheets, latest-only teacher reopening, numbered CSV history, legacy schema preservation, verified backups, rollback and import isolation.
- First stationary selection/focus contacts no longer save phantom ink. First real drags and later intentional decimal dots remain. Browser checks inspect actual empty canvas pixels and saved API answers, not only screenshots. No previously saved student dot was automatically deleted.
- OCR and PDF stroke rendering now use the browser's pressure formula and endpoint-averaged pressure. The old OCR multiplier made ordinary mouse/touchpad ink roughly 43% thicker before rounding; this could distort small loops. Six OCR regressions verify fidelity, preserving singleton marks, and specific uncertainty feedback. Two report tests check attempt identity and pressure/dot preservation.
- The new browser script covers 15 scenarios, including retry cancellation, retry while an earlier attempt awaits review, unchanged previous evidence, latest-attempt navigation, a typed **16/16** second attempt, numbered history and unavailable/withdrawn actions. Report: `artifacts/student-retry-runs/1789385765981/result.json`. The original 16-check flow still finishes its intentionally wrong final answer at **15/16**, including autosave, offline recovery, conflicts and logout races.
- A read-only, anonymized inspection confirmed singleton-stroke contamination in an existing submission. Separate offline checks on three visually transcribed handwritten fields showed a symbol-reading improvement from faithful rendering, but **all three still required review before and after**. No worksheet key or student identity was passed to recognition, no handwriting was uploaded, and no original submission was changed. Small diagnostic examples are not an accuracy benchmark.
- A square-padding experiment worsened readings and was rejected. The installed English text-line recognizer remains weak on isolated/widely spaced handwritten digits. Agreement and confidence gates were not lowered; review means uncertainty, not proof of an incorrect answer.
- Blank-gap compression also failed to improve automatic qualification (0/3 anonymous fields and 0/6 synthetic fixtures). A separate 26kB official MNIST digit-model diagnostic improved some first transcriptions but qualified 0/9 under a five-view conservative check; it also demonstrated high single-view confidence on non-digit symbols. Neither experiment was integrated. MNIST dependencies/model remain isolated under ignored artifacts; no runtime requirement was added.
- Browser-faithful rendering is a fidelity correction, **not a demonstrated general accuracy improvement**: the old synthetic digit-3 automatic acceptance no longer reproduces with the corrected rendering. The pipeline diagnostic now distinguishes `matching_fixture_auto_qualified` from passing review/marking safeguards, with two regression tests. A safe pending mark is not counted as a successful automatic transcription.

Read [what to do next](../WHAT-TO-DO-NEXT.md) for the safe server restart, automatic backed-up schema upgrade, clean-attempt dot check and real-device acceptance test. Existing classroom migration is performed on the user's next server startup, not by these isolated tests.

## Historical testing-guide and demo follow-up

The earlier follow-up added [the complete testing guide](../TESTING-FROM-START-TO-FINISH.md), 12 explicitly synthetic filled PDFs, 12 matching digital-ink fixtures, a generation helper and a local student-API replay helper. No completed-PDF submission grader was added. The demo ink is constructed test data, not real student handwriting or an accuracy benchmark.

- At that time the Python run had **78 tests, 76 passed, 1 failure and 1 error** in 23.479 seconds. Missing `numpy` caused both unsuccessful OCR tests. That was not an all-green run; the current run above supersedes it.
- At that time the isolated `.venv` also lacked `torch`, `transformers` and `safetensors`. The packages are now installed, as verified in the current update. No optional packages or environment settings were changed during that earlier documentation-only follow-up.
- All **21 newly added tests** passed: 17 replay-helper safety/contract checks, one actual API integration workflow, and three demo-asset/overwrite checks. The real API test uses an isolated temporary classroom and an injected unavailable recognizer; it verifies draft save, refusal to overwrite, explicit replacement/submission, pending marks, teacher access and PDF export without touching a running classroom.
- All **13 JavaScript tests** and the **16-check browser workflow** passed again. Browser marking/review finished at 15/16 with no uncaught browser errors. These checks deliberately do not require real OCR.
- All 12 fixtures validate against their original sample layouts; demo PDF labels, page counts and fingerprints are checked. The six original SHA-256 fingerprints still match. `git diff --exit-code` reports no tracked generator changes.

The results below remain a historical record of the initial implementation. Refer to the current verification above for the latest suite and dependency status.

## Reproducible checks

From this folder:

```powershell
.\.venv\Scripts\python -m unittest discover -s tests -v
node --test tests/ink.test.mjs tests/session.test.mjs
node tools/browser_smoke.cjs
node tools/student_retry_smoke.cjs
node tools/paper_upload_smoke.cjs
.\.venv\Scripts\python tools/preview_regions.py
.\.venv\Scripts\python tools/download_model.py --verify-only
```

`browser_smoke.cjs` uses the existing backend's installed Puppeteer without modifying it. It starts/stops its own local server on port 8017, creates disposable test accounts and stores each test database under `artifacts/browser-runs`. It deliberately configures a missing OCR model so review-path tests are deterministic. It refuses to run over an existing server on that port. Do not adapt it to a production URL.

## Automated coverage

Earlier implementation verification: **57 Python tests passed** (22.3 seconds) against the adopted PDFium/ReportLab implementation in the OCR-enabled environment. The JavaScript suites passed all **13 tests** (9 ink and 4 session-response regressions). The **16-check browser workflow** also passed against the adopted backend with no uncaught JavaScript errors, including a deliberately delayed authenticated response delivered after logout.

- Python API tests exercise real PDF imports for all six samples, renamed-content hash matching, draft/publication confirmation, valid/invalid input, original-file integrity, reports, teacher/student ownership, private keys, immutable rubric snapshots, autosave versions, idempotent submit, server-side marking, review/partial marks/audit, reopening and interrupted-job recovery.
- Security regressions cover cross-origin/CSRF rejection, non-ASCII secret input, invalid non-finite values and malformed Unicode returning controlled errors, spreadsheet formula escaping, request limits, PDF processing backpressure and session revocation.
- Scoring tests reject substring matches (`2` is not `12`), preserve negatives/decimal/fraction meaning, handle exact text and explicit tolerances, keep OCR errors/mismatches pending, enforce total OCR scheduling budget, and prove the recognizer never receives the answer key.
- OCR unit tests use controlled model doubles for readiness, offline flags, bounded rendering, uncertainty gates and failure cleanup. They do not establish model accuracy.
- Nine JavaScript ink tests cover normalized coordinates/pressure, orientation/DPI redraw, finger-scroll gating, read-only behavior, coalesced samples/cancellation, stroke/answer size limits, erasing and undo.
- Four session-generation regressions ensure late reads/saves cannot restore an earlier account after logout, expiration, account change or same-account re-login. The final browser test holds a real authenticated response until after logout and confirms that the sign-in screen remains in place.
- Browser acceptance passes teacher setup, sample import/publication, student registration, 15 typed answers plus a pressure-bearing digital pencil stroke, autosave/reload, pending handwriting review, teacher marking, PDF export, touch selection, offline recovery/reconnection, stale-version conflict protection, responsive phone width and logout. No uncaught browser JavaScript errors were recorded.

The browser fixture deliberately writes a `7` for the final `2 + 9` answer. Fifteen typed answers receive 15 confirmed marks; the handwritten answer remains pending, not an OCR-generated zero. After a teacher confirms that answer is wrong, the final result is **15/16 = 93.75%**. This verifies the scoring/review workflow, not handwriting recognition accuracy.

Screenshots and machine-readable results are generated under `artifacts/browser`; annotated draft key previews are under `artifacts/region-previews`. These files are ignored by Git and contain test data, not real pupils.

## Earlier TrOCR model evaluation (historical)

Superseded by [OCR evaluation](OCR-EVALUATION.md). The pinned local TrOCR safetensors model was downloaded and verified, then exercised without external inference. Eight selected **older scanned** handwriting crops were independently transcribed for a small diagnostic check. Two first transcriptions matched their numerical labels; **zero of eight** passed the conservative automatic-marking gate. All remained pending. This is not a representative accuracy benchmark and does not establish digital-pencil performance.

See [OCR evaluation](OCR-EVALUATION.md) for the scan and digital-stroke results, timings and reproduction details. A probability such as `0.98` is a model screening threshold, not “98% classroom accuracy.” The model must not be sold as a validated unattended examiner on this evidence.

Six constructed digital-stroke examples were also tested: one qualified for automatic comparison. A real offline pipeline check then verified that the same qualifying `3` ink receives **2/2 against key 3**, but remains **pending against key 4**. These small synthetic checks prove the model-to-marking path works; they are not representative student accuracy measurements.

## Required before live launch

- A teacher checks/approves each rubric and mark allocation, including the six derived sample keys.
- Test real Apple Pencil/Safari and Android stylus hardware: first stroke, palm contact, two-finger scrolling, eraser, orientation changes, backgrounding, network interruption and long sessions. Chromium viewport/Pointer Event tests do not replace this.
- Photograph and scan real completed worksheets with the phones and scanners the school will use. Confirm alignment, blank detection and circled options, and that a photo of the wrong worksheet is refused.
- Collect representative labelled student handwriting, online and on paper, including incorrect answers, and measure false acceptance and review workload with `tools/evaluate_handwriting.py --labels`. Review any automatically accepted mark during the pilot. Choose a better locally validated recognizer or training approach if the measured result is unsuitable; do not merely lower thresholds.
- Build/run the container on the actual host, confirm HTTPS/cookies/origin configuration, test simultaneous classroom submissions and set capacity limits. Docker/DNS/certificates were not available for execution in this workspace.
- Confirm operator access, password recovery, enrollment policy, privacy/consent, retention, encryption and a tested backup restore. This is a small-classroom single-process deployment, not a distributed exam platform.
- Verify PDF report text for the languages required by the client. Original worksheet script is preserved visually, but generated non-Latin report labels may require embedded fonts/shaping.

Until these gates pass, treat the result as a working, tested **pilot with teacher-supervised marking**, not a claim that arbitrary handwritten worksheets can be graded perfectly without review.
