# Existing generator: architecture, file map and integration decision

This review covers the first-party source/configuration files, supplied OCR experiment, and six sample PDFs. Dependency installations (`node_modules`), Git internals and binary model weights are classified as artifacts, not represented as hand-audited application source. Secrets are not reproduced. The generator and intern directories are unchanged.

## How the current system actually works

```text
Staff login
  -> dashboard / English or Sinhala upload
  -> HTML content wrapped in branded template
  -> full-document iframe editing + Zustand draft/history
  -> current HTML export
  -> Express authenticated generate-pdf route
  -> Puppeteer font/asset preparation + scale-to-fit
  -> US Letter PDF with header, footer and copyright
```

The important architectural distinction is that this is an **HTML document editor**, not a database of semantic questions. The active edited document is `draftHTML`. The project also contains a structured block parsing/rendering layer, but a grading integration must not assume every active worksheet is represented by those blocks. Selection identifiers used while editing are not stable assessment question identifiers.

The English and Sinhala wrappers are responsible for the branded shell. The canvas edits the real document inside an iframe; toolbar/property tools act on selections and sync edits into the store. Undo/redo and multi-tab recovery are browser state concerns. The PDF service takes an HTML string, embeds local branding, prepares fonts, measures overflow and applies Letter export sizing. It does not calculate answers or annotate an assessment rubric.

The backend also contains MySQL metadata and S3 save/load/delete functionality. Existing UI paths include local HTML saving and disabled/limited cloud library functionality; the presence of S3 endpoints is not proof that a teacher/student assignment workflow already exists.

## Root and backend files

| File/folder | Role and relevant observations |
| --- | --- |
| `README.md` | Existing project introduction; verify descriptions against current implementation. |
| `package.json`, `package-lock.json` | Root tooling/dependency resolution. Separate frontend/backend package manifests define the actual apps. |
| `.gitignore` | Existing exclusions; left untouched. The new portal has its own nested ignore file. |
| `convert.js` | Standalone conversion helper, not the student assessment service. |
| `Worksheet-Template.pdf` | Branded reference PDF; contains layout, not marking data. |
| `backend/index.js` | Express application, middleware and route mounting. |
| `backend/package.json`, `package-lock.json` | Node ES-module backend dependencies and lock. |
| `backend/.env.example` | Database/auth/storage configuration names. Never copy real secrets to the new portal. |
| `backend/README.md` | Backend setup notes. |
| `backend/services/db.js` | MySQL pool/schema concerns; existing generator records are distinct from student submissions. |
| `backend/services/pdfGenerator.js` | Shared Puppeteer lifecycle, local image embedding, font preparation, measurement and Letter PDF rendering. |
| `backend/routes/worksheetRoutes.js` | Authenticated PDF generation, S3 HTML/PDF pair operations and worksheet metadata. Not a rubric/attempt API. |
| `backend/routes/authRoutes.js` | Staff registration/login/password-reset workflow. Current email allowlist targets specific staff addresses. |
| `backend/middleware/authMiddleware.js` | JWT-based generator authorization. No classroom student/teacher role model. |

## Frontend shell, state and engines

| File | Role |
| --- | --- |
| `frontend/package.json`, `package-lock.json` | React 19/Vite 5 and editor dependencies including Zustand/Tailwind; lockfile records resolved dependencies. |
| `frontend/index.html`, `src/main.jsx` | Browser mount and React entry. |
| `frontend/vite.config.js` | Development/build configuration and backend-facing development behavior. |
| `frontend/tailwind.config.js`, `postcss.config.js`, `src/index.css` | Utility styling configuration and global/custom editor styles. |
| `frontend/README.md` | Frontend notes. |
| `frontend/worksheet-template.html` | Standalone HTML template/reference; runtime English/Sinhala wrapper modules also implement template behavior. |
| `src/App.jsx` | Store-driven view switching, auth initialization and editor unload/recovery handling; not a conventional URL router. |
| `src/store/authStore.js` | Generator session/JWT state and authentication requests. |
| `src/store/worksheetStore.js` | Worksheet metadata, current/original HTML, selections, blocks, editing actions, history and per-tab persistence. Session storage isolates active tabs; local storage holds recovery registry/backups. |
| `src/engine/templateWrapper.js` | English branded document wrapping/unwrapping and template-specific behavior. |
| `src/engine/sinhalaTemplateWrapper.js` | Sinhala wrapper, script/font/layout handling, unwrapping. |
| `src/engine/htmlParser.js` | Imported HTML parsing and block metadata extraction. |
| `src/engine/detectionEngine.js` | Heuristic block/type recognition, not dependable semantic problem understanding. |
| `src/engine/exportEngine.js` | JSON/HTML block export/import and reconstruction fallback. Does not provide answer keys. |
| `src/utils/constants.js` | Shared editor block types, limits and constants. |
| `src/utils/helpers.js` | General IDs, value/DOM/download helpers. |

## Every first-party component group

| Component file(s), relative to `frontend/src/components` | Responsibility |
| --- | --- |
| `Auth/AuthPage.jsx` | Existing staff authentication forms. |
| `Dashboard/Dashboard.jsx` | Main staff landing, new/open/recovery entry points. |
| `UploadScreen/UploadScreen.jsx` | English content ingestion and template/editor handoff. |
| `UploadScreen/SinhalaUploadScreen.jsx` | Sinhala content ingestion and wrapper handoff. |
| `Editor/EditorLayout.jsx` | Editor composition: toolbar, canvas and property/code/export panels. |
| `Toolbar/Toolbar.jsx` | Editing commands and save/export entry points; current-document operations must use current draft. |
| `Canvas/Canvas.jsx` | Full HTML iframe and document editing/selection synchronization; central active editing surface. |
| `Canvas/SelectionManager.jsx` | Selection/interaction support for the block-oriented editor layer. |
| `Canvas/BlockWrapper.jsx` | Block positioning/selection wrapper. |
| `Canvas/BlockRenderer.jsx` | Dispatch to block-specific React renderers. |
| `Blocks/TextBlock.jsx` | Text block presentation/editing. |
| `Blocks/ImageBlock.jsx` | Image block presentation. |
| `Blocks/EquationBlock.jsx` | Equation-like content presentation; not mathematical evaluation. |
| `Blocks/QuestionCardBlock.jsx` | Question-card visual structure. |
| `Blocks/OptionBadge.jsx` | Option-label presentation; not an approved multiple-choice key. |
| `Blocks/ContainerBlock.jsx` | Group/container representation. |
| `Blocks/GenericBlock.jsx` | Fallback block representation. |
| `Blocks/HTMLPreviewBlock.jsx` | HTML preview representation. |
| `PropertyPanel/PropertyPanel.jsx` | Selection property panel orchestration. |
| `PropertyPanel/ContentFields.jsx` | Text/content properties. |
| `PropertyPanel/StyleFields.jsx` | Typography/style properties. |
| `PropertyPanel/PositionFields.jsx` | Position/dimension properties. |
| `PropertyPanel/ColorPicker.jsx` | Reusable color input. |
| `CodeViewer/CodeViewer.jsx` | HTML/source viewing/editing tooling. |
| `ExportModal/ExportModal.jsx` | Export preview and final HTML/PDF preparation. Includes layout-specific export behavior. |

`frontend/public` contains branding/static art: `logo.jpg`, `gb-logo.jpg`, `gb-favicon.jpg`, `image.png`, `favicon.svg`, `icons.svg`, `watermark.svg`; `assets/illustrations` contains `hero_illustration.webp`, `how_it_works.webp`, `ai_mascot.webp`. These are presentation assets, not recognition training data. Existing `node_modules` and lockfiles should not be manually edited.

## Coding style and maintenance implications

- JavaScript uses ES modules, camelCase functions/state and PascalCase React components; components are primarily functional with hooks. Tailwind utilities coexist with large custom/template CSS.
- Zustand stores carry significant business/UI state. Rich HTML strings and direct iframe/DOM mutation coexist with declarative React. A new feature must understand which document representation is authoritative.
- Large modules and sectioned explanatory comments show iterative feature work. The English/Sinhala wrappers and client/server export logic share concepts but duplicate some layout rules, creating drift risk.
- Express async route handlers generally use try/catch and JSON errors; persistence crosses MySQL metadata, S3 files and browser recovery storage.
- The current identity and worksheet metadata are for generator staff. Printed worksheet IDs are display labels, not secure identities or globally trustworthy assessment keys.
- There is no supplied automated acceptance suite proving the new assessment requirements, and the old OCR experiment is a separate prototype. New tests therefore belong with the isolated service.

## Why the intern's system is not a drop-in integration

See `LEGACY-OCR-AUDIT.md` for the file-level audit. The intern implemented photo upload/cropping, manually configured answer boxes/lines and short-answer experiments against different example images. The active recognition path uses external paid services; local detector weight files do not mean the application already has a working free handwriting reader. The prototype lacks student identity, stylus strokes, protected keys, attempt snapshots, grade review and reliable error semantics. Its substring and normalization behavior can award incorrect marks.

Reuse the **idea** of normalized answer regions and separating extraction from scoring; do not import its server or copy its unsafe correctness rules. Existing eight legacy JSON templates are not applied to the six new PDFs.

## New architecture and integration boundary

```text
Existing generator -> exported PDF (unchanged)
                         |
              teacher imports + confirms key
                         |
            published worksheet + page regions
                         |
          authenticated student attempt snapshot
                         |
  saved typed/choice/vector-ink answers  or  uploaded paper photo/scan
                         |          (aligned to the PDF; printing removed)
       offline recognition of student marks only (optional)
                         |
            strict scoring / pending teacher review
                         |
            confirmed marks + CSV/PDF evidence
```

The new service runs on its own port/domain, database and cookies. It uses a PDF hash, internal worksheet UUID and immutable answer-key snapshot. Neither the PDF header nor editable client fields can impersonate a student or supply a score. All source, model artifacts and runtime data are under `automatic grading`.

The new files divide concerns explicitly: `server.py` is authorization/workflow orchestration; `database.py` owns transactions/schema; `auth.py` owns passwords/sessions/CSRF; `schemas.py` bounds untrusted input; `documents.py` exposes the PDF interface implemented by `documents_permissive.py` using PDFium/ReportLab; `samples.py` binds reviewed regions to known bytes; `ocr.py` handles only recognition (GLM-OCR, with PaddleOCR-VL as a second opinion) and never receives the key; `paper.py` aligns uploaded paper pages and isolates new marks; `grading.py` compares answers and totals confirmed marks. The dependency-free static client keeps the portal deployable without changing the generator's Node toolchain.

Future same-sign-on, assignment scheduling, additional worksheet semantics, multi-class administration or a direct “Send to classroom” generator button would be separate authorized changes. They are not silently patched into the original tool here.
