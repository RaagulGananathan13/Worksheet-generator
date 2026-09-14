# Legacy OCR audit

Inspected 2026-09-14. The original generator, `OCR/`, sample PDFs, and credentials
were not modified or used to call external inference services. This report is
about the delivered source, not a claim of production OCR accuracy.

## Integration decision

The intern built a FastAPI prototype for marking uploaded worksheet images.
Teachers first detect rectangles/lines and enter an answer key. A later image
upload is cropped by those coordinates and each crop goes to OpenAI vision.
The prototype has no pupil login, assignments, digital handwriting capture,
autosave, reliable grading history, or teacher correction workflow.

Reuse the idea of normalized answer regions and explicit teacher keys. Keep the
old application as a reference; do not import it into the new runtime. Its stored
templates belong to older screenshot layouts and cannot locate answers in newly
generated branded PDFs. The new application binds regions to the imported PDF's
SHA-256 and records isolated digital ink, which avoids camera alignment entirely.
No paid OCR providers or old secrets are used by the new application.

## File and folder map

All paths in this section are relative to `OCR/Grading worksheet/Grading worksheet`.

| Path | What it contains |
| --- | --- |
| `main.py` | 2,087-line FastAPI app, four template/grading routes, older generic grading APIs, static/upload/debug mounts. |
| `main_crop.py` | Independent port-8004 green-border cropper. |
| `main_ocr.py` | Independent port-8002 OCR demo wired to the nonfunctional Grok adapter. |
| `app/services/answer_box_service.py` | Green/orange contour detection; normalized rectangular fields; exact case-insensitive comparison. |
| `app/services/dotted_line_service.py` | Threshold/dilation/Canny/Hough detection of horizontal guide lines; JSON templates. |
| `app/services/blank_line_service.py` | Thin-wide contour detection for underscore and orange solid lines. |
| `app/services/sa_service.py` | Duplicated box detector; short-answer templates; keyword, semantic and character-similarity credit. |
| `app/services/gpt_ocr_service.py` | Active paid OpenAI vision adapter, default `gpt-4o`. |
| `app/services/grok_ocr_service.py` | Returns an unsupported-image stub; unreachable HTTP code points to Groq. |
| `app/services/rapidapi_ocr_service.py` | Older Pen-to-Print adapter and preprocessing; unused by main grading. |
| `ai_enhancer.py`, `text_post_processor.py` | Entire implementations commented out. |
| `app/utils/image_utils.py` | Enhancement, deskew, ORB/RANSAC perspective alignment, coordinate helpers; unused by active grading. |
| `app/utils/border_detector.py` | Green-border detector/cropper; unused by active grading. |
| `app/config.py`, `app/utils/config.py`, `config_utils.py` | Three overlapping configuration systems with inconsistent defaults. |
| `app/utils/file_utils.py` | Upload validation and cleanup code entirely commented out. |
| `app/utils/logger.py`, `response_utils.py` | General logging and response helpers, inconsistently used. |
| `templates/answer_box_creator.html`, `dotted_line_setup.html`, `blank_line_setup.html`, `sa_setup.html` | Teacher image upload, detection, deletion of bad regions, and answer entry. |
| `templates/unified_grader.html` | Image upload and result overlays, no live student ink. |
| `templates/index.html`, `gpt_ocr_test.html`, `crop_ui.html` | Separate OCR/crop demonstration pages. |
| `static/styles.css` | Bootstrap orange/Poppins theme overrides. |
| `data/` | Eight legacy template JSON files and PNGs; extra debug images. |
| `models/` | `craft_mlt_25k.pth`, `english_g2.pth`; no active code loads them. |
| `uploads/`, `debug/`, `temp/` | Original submissions, diagnostic crops, transient files. |
| `.venv/`, `.idea/`, `.pytest_cache/`, `__pycache__/` | Copied environment/editor/cache artifacts, not authored product functionality. |
| `.env` | Provider credential entries; values were not exposed, copied or used. |
| `requirements.txt` | FastAPI, OpenCV, NumPy, Pillow, OpenAI, Torch, pandas, fuzzy matching; several unused dependencies, no lockfile. |
| `.gitignore`, `README.md` | Ignore rules and prototype setup documentation; claims do not always match active behavior. |
| `app/__init__.py`, service/utility `__init__.py` | Package markers. |

## Persisted data and algorithms

Two answer-box templates have 9 and 8 questions; blank-line templates have 6 and
4; dotted-line templates have 6 and 5; short-answer templates have one each. The
PNGs use older green page borders and orange answer outlines.

- Boxes store `questions[].expected_answer`, absolute `position` and normalized
  `relative_position` using `x,y,width,height`, plus `image_dimensions`.
- Dotted templates use `questions[].expected_answer` and normalized line endpoints
  `x,y,x2,y2`. The grader adds fixed 70px top and 20px bottom crop padding.
- Blank templates use `lines[].expectedAnswer` and absolute `x,y,width,height`.
  Dimensions are reread from the original PNG during grading.
- Short answers use `boxes[].answer`, comma-separated `keywords`, normalized
  rectangles, and a separate `model_answers` dictionary.

Color detection selects HSV green/orange contours and filters rectangularity,
area, convexity and aspect ratio. Dotted detection joins nearby dark pixels then
uses Hough lines. Its Y-only deduplication drops distinct same-row regions. Blank
detection identifies thin wide connected components. These are setup suggestions,
not sufficient proof that a region represents a question.

## Correctness problems with evidence

1. `gpt_ocr_service.py:55-56` requests Latin letters/digits and discards punctuation,
   decimal points, minus signs, fractions and operators. It cannot support the
   required broader math/Sinhala workload as written.
2. `gpt_ocr_service.py:15,77-80` fabricates successful confidence as `1.0`; failures
   become empty strings. Most grading paths turn failures into wrong answers.
3. `main.py:1473,1772` uses substring inclusion for dotted/blank answers: expected
   `2` accepts `12`, and `cat` accepts `caterpillar`.
4. `answer_box_service.py:483` accepts blank OCR for an empty answer key. Other
   flows skip missing keys and invalid regions, silently shrinking denominators.
5. `sa_service.py:471,556-581` prefers keyword substrings. `main.py:2013` adds 0.20
   to similarity; approximately 55% keyword coverage can reach full-credit 0.75.
   Negation and contradictions are not reliably understood. Semantic comparison
   is normally bypassed when explicit or auto-extracted keywords are present.
6. `sa_service.py:636` falls back to character similarity, which does not establish
   meaning or numerical correctness. Weights/rubrics are inconsistent by flow.
7. Grading reads crops containing worksheet printing; there is no separate ink
   layer or blank-template subtraction. Printed content can affect recognition.
8. ORB/RANSAC helpers exist but no active grading path calls them. Independent X/Y
   scaling cannot fix rotation, changed cropping, camera perspective or translation.
9. `main.py:375` uses undefined `UPLOADS_DIR`; `main.py:833` uses unimported `Response`.
10. Duplicate GET answer-template routes conflict. The first expects `boxes` while
    saves contain `questions`; image retrieval expects `image_data` while saves use
    `image_path`. `/unified-setup` refers to missing `unified_setup.html`.
11. `main_ocr.py` mounts missing `templates/static`; `dotted_line_service.py:409`
    uses unimported `shutil`; `blank_line_service.py:150` uses `h` before assignment;
    `image_utils.py:10` imports `imutils`, absent from requirements.
12. Several IDs have second-resolution timestamps and may collide. Detector UI
    parameters are not consistently honored by hard-coded active thresholds.

## Security and operations

There is no authentication/ownership enforcement. APIs expose keys and student
images. Client filenames/template IDs are joined to filesystem paths without
containment checks; generic template failure cleanup recursively deletes the
derived directory (`main.py:158,215`). Upload validation is mostly disabled, with
no enforced byte/pixel budget, quota or worker queue. Blocking OCR/OpenCV calls run
inside async handlers. Results and user text enter HTML through `innerHTML`.
Retention and logging are unsuitable for private student work. Credentials were
included in the handoff (`OPENAI_API_KEY`, `RAPIDAPI_KEY`, `GROK_API_KEY`); replace
them before ever redeploying the old project. No secret values are recorded here.

## Free local replacement limits

The first replacement used TrOCR, which proved too weak on children's digits. The
September 2026 update uses GLM-OCR (MIT) with PaddleOCR-VL-1.5 (Apache-2.0) as an
independent second opinion, both offline; see `OCR-EVALUATION.md`. They do not
establish suitability for Sinhala, multiline essays, mathematical notation or
tracing. Those cases need teacher review or typed/structured answers. Model scores
and agreement are screening signals, not guarantees. Representative classroom
handwriting must be evaluated before accepting automatic marks in live classes.

## What the paper-upload update reused

- **Idea, re-implemented:** `app/utils/image_utils.py` contained an unused ORB and
  homography photo aligner. `app/paper.py` implements alignment with SIFT, MAGSAC and
  ECC refinement, and adds what the prototype lacked: rejection of a different
  worksheet (all GeniusBees pages share a header and footer), visible-area checks,
  removal of printing by comparison with the original page, and blank/faint detection.
- **Idea, re-implemented:** normalized answer regions, as before.
- **Data, read-only:** the photographed sheets and blank templates in
  `OCR/test cases (2)` measure the paper pipeline in `tools/evaluate_handwriting.py`.
- **Not reused:** the paid OpenAI/RapidAPI/Grok adapters, colour-box detectors,
  substring and similarity scoring, EasyOCR weights and the prototype server.

Sources: [GLM-OCR model card](https://huggingface.co/zai-org/GLM-OCR),
[PaddleOCR-VL-1.5 model card](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.5),
[Microsoft TrOCR model card](https://huggingface.co/microsoft/trocr-base-handwritten) (former reader),
[official Transformers TrOCR documentation](https://huggingface.co/docs/transformers/model_doc/trocr),
[official model-download documentation](https://huggingface.co/docs/huggingface_hub/guides/download).
