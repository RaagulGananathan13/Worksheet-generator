<div align="center">
  <img src="frontend/public/gb-logo.jpg" alt="GeniusBees Logo" width="220"/>
  <h1>🐝 GeniusBees Worksheet Generator & Classroom</h1>
  <p><strong>Create branded worksheets, then let students answer them online or on paper and get them marked.</strong></p>

  <p>
    <img src="https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB" alt="React" />
    <img src="https://img.shields.io/badge/Vite-B73BFE?style=for-the-badge&logo=vite&logoColor=FFD62E" alt="Vite" />
    <img src="https://img.shields.io/badge/Express-000000?style=for-the-badge&logo=express&logoColor=white" alt="Express" />
    <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
    <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI" />
  </p>
</div>

## What is in this repository

The repository holds two independent applications. The only link between them is the worksheet PDF: the editor exports it, the classroom imports it.

| Folder | What it is | Built with | Run it when you want to… |
| --- | --- | --- | --- |
| `frontend/` | **Worksheet editor**: upload English or Sinhala worksheet HTML, edit it visually, export PDFs | React, Vite, Tailwind, Zustand | create or edit worksheets |
| `backend/` | **Editor API**: staff login, PDF export with Puppeteer, AWS S3 save/load, MySQL | Node.js, Express | use the editor |
| `automatic grading/` | **Classroom**: teachers publish worksheet PDFs; students answer on a tablet or upload a photo/scan of the printed page; free local handwriting reading marks answers, with teacher review for anything uncertain | Python, FastAPI, SQLite, OpenCV, local OCR models | mark student work |
| `sample-worksheets/` | Six exported sample worksheets and 12 synthetic filled test copies | PDF | test the classroom |
| `OCR/` | Earlier intern prototype, kept for reference and its photographed test sheets. It is not run. | — | nothing |

## Before you start

| You need | For | Check |
| --- | --- | --- |
| [Git](https://git-scm.com/) | getting the code | `git --version` |
| [Node.js](https://nodejs.org/) **22.12 or newer** (includes npm) | editor frontend and backend (Puppeteer 25 needs it) | `node --version` |
| [MySQL](https://dev.mysql.com/downloads/) 8 server | editor backend accounts and worksheet records | `mysql --version` |
| An AWS account and S3 bucket | *optional*: the editor's cloud save/library | — |
| [Python](https://www.python.org/downloads/) **3.13** | classroom | `python --version` (Windows: `py -3.13 --version`) |
| About 6 GB free disk and **16 GB RAM** | *optional*: the classroom's handwriting models | — |

## 1. Get the code

```bash
git clone https://github.com/RaagulGananathan13/Worksheet-generator.git
cd Worksheet-generator
```

**Windows tip:** clone into a short folder path, such as `C:\dev\Worksheet-generator` or your Desktop. Windows limits file paths to 260 characters, and a very deeply nested folder can make `pip install` fail with "The filename or extension is too long" and the classroom tests fail with "The system cannot find the path specified".

Things that are deliberately **not** in Git, so every computer creates its own:

- `.env` files with passwords and keys. Copy them from the `.env.example` files.
- `node_modules/` and Python `.venv/` folders. The install steps create them.
- `automatic grading/data/`: the classroom database, uploaded student papers and the downloaded handwriting models. A fresh clone therefore starts with an **empty classroom**, and the models are downloaded once per computer.

## 2. Run the worksheet editor

### Backend (API on port 3001)

```bash
cd backend
npm install
```

`npm install` also downloads the Chrome build that Puppeteer uses for PDF export.

Create `backend/.env` from the example (Windows: `copy .env.example .env`; macOS/Linux: `cp .env.example .env`), then edit it:

- `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`: your MySQL server. The database and tables are created automatically on first start.
- `JWT_SECRET`: a long random value.
- `AWS_REGION`, `AWS_S3_BUCKET`, `AWS_S3_KEY_PREFIX`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`: only needed for saving worksheets to S3.

```bash
npm run dev
```

It should print `Connected to MySQL database` and `Worksheet backend listening on http://localhost:3001`.

### Frontend (editor on port 5173)

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The frontend forwards `/api` calls to the backend on port 3001, so keep both running.

**Creating an account:** sign-up only accepts emails of the form `geniusbees.devNN@gmail.com` (1–3 digits, for example `geniusbees.dev01@gmail.com`) and passwords of at least 6 characters. Password reset shows the reset token on screen in this development setup.

## 3. Run the classroom (automatic grading)

The classroom does not need the editor, Node.js or MySQL. It uses the sample PDFs, or any PDF exported from the editor.

**Windows (PowerShell)**

```powershell
cd "automatic grading"
py -3.13 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python run.py
```

**macOS / Linux**

```bash
cd "automatic grading"
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run.py
```

Open `http://127.0.0.1:8001`:

1. Copy the **first-teacher setup token** printed in the terminal into *Create your classroom* and create the teacher account.
2. Import a sample worksheet, check its answer key, and publish it.
3. In a different browser, or a private window, register a student with the class code shown to the teacher.

**Handwriting reading (optional, recommended).** Without it, everything works, but handwritten answers wait for the teacher. To enable it (use `.venv/bin/python` on macOS/Linux):

```powershell
.\.venv\Scripts\python -m pip install -r requirements-ocr.txt
.\.venv\Scripts\python tools/download_model.py
```

This downloads about 4.6 GB (GLM-OCR and PaddleOCR-VL) once, checks the files against pinned fingerprints, and runs offline afterwards. Marking with both models uses roughly 7–11 GB of RAM.

**Next steps:**

- [Classroom README](automatic%20grading/README.md): features and marking rules.
- [Testing from start to finish](automatic%20grading/TESTING-FROM-START-TO-FINISH.md): every teacher and student step, including paper uploads.
- [Deployment](automatic%20grading/docs/DEPLOYMENT.md): hosting with HTTPS and backups.

## Tests

The classroom has automated tests. From `automatic grading`:

```powershell
.\.venv\Scripts\python -m unittest discover -s tests
node --test tests/ink.test.mjs tests/session.test.mjs
```

The browser workflow checks (`node tools/browser_smoke.cjs`, `tools/student_retry_smoke.cjs`, `tools/paper_upload_smoke.cjs`) reuse Puppeteer from `backend/node_modules`, so run `npm install` in `backend` first. The editor has no automated test suite.

## Keeping data private

- Never commit `.env` files or anything under `automatic grading/data/` or `automatic grading/artifacts/`. The root `.gitignore` already excludes them.
- `automatic grading/data/` contains student accounts, answers and uploaded paper photos. Back it up privately.

## 🛠️ Tech stack

- **Editor frontend:** React 19, Vite 5, Tailwind CSS, Zustand
- **Editor backend:** Express 5, MySQL (mysql2), AWS SDK for S3, Puppeteer
- **Classroom:** FastAPI, SQLite, PDFium (pypdfium2), ReportLab, OpenCV, Transformers with GLM-OCR and PaddleOCR-VL, plain JavaScript client

## 🎨 Theme & design

The editor and the classroom share the **GeniusBees** identity and logo:

- **Primary:** Orange (`#F57C00`)
- **Secondary:** Green (`#4CAF50`) & Purple (`#7B1FA2`)
- **Background:** Clean White (`#FFFFFF`) with subtle surface layers.

## 🤝 Contributing

Contributions, issues and feature requests are welcome through this repository's Issues and Pull requests on GitHub.

---

<div align="center">
  <i>Built with ❤️ by GeniusBees</i>
</div>
