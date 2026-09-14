# After the paper-upload and handwriting-accuracy update

This update adds printed-worksheet uploads, replaces the old handwriting reader with two free local models, marks handwriting in the background, and uses the GeniusBees logo. Your accounts, worksheets, attempts and marks are kept.

## 1. Restart the grading server, keeping your classroom

Finish saving any open drafts. In the PowerShell window running your grading server, press **Ctrl+C**. Do not delete `data`, create a replacement classroom, or run two grading servers against the same database.

Install the updated dependencies (OpenCV is new; it aligns paper photos), then start the server from the same terminal, keeping any custom `AG_DATA_DIR` setting you normally use:

```powershell
cd 'C:\path\to\Worksheet-generator\automatic grading'
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m pip install -r requirements-ocr.txt
.\.venv\Scripts\python run.py
```

On the first start, the database gains three attempt columns (`submission_mode`, `paper`, `grading_tries`). Existing rows are not changed. If startup reports a database error, keep the `data` folder and report the terminal message; do not reset the classroom.

Open `http://127.0.0.1:8001` and hard-refresh with **Ctrl+Shift+R**. The header now shows the GeniusBees logo. Sign in with your existing account.

## 2. Handwriting models

On the computer where this update was developed, both models are already installed and verified: GLM-OCR and PaddleOCR-VL, about 4.6 GB in `data/models`. Models are not stored in Git, so a fresh clone must download them (below). Check at `http://127.0.0.1:8001/api/health`: `ocr.configured` and `ocr.cross_check` should both be `true`. `available` becomes `true` after the first handwritten submission loads the models.

On another computer, or if the check fails:

```powershell
.\.venv\Scripts\python tools/download_model.py
.\.venv\Scripts\python tools/download_model.py --verify-only
```

The downloader resumes if interrupted and refuses files whose fingerprints differ from the pinned ones. Marking with both models needs roughly 7–11 GB of RAM, so close other heavy programs on a 16 GB laptop.

The old reader's files in `data/models/trocr` (about 1.3 GB) are no longer used. You may delete that folder once you are happy with the update.

## 3. How handwriting is now marked

- **Correct:** GLM-OCR reads the answer confidently and the reading matches the answer key.
- **Wrong (zero):** the reading clearly differs from the key, GLM-OCR is highly confident, **and** PaddleOCR-VL independently reads exactly the same thing. For paper answers PaddleOCR-VL looks at the original photo of the answer, not the cleaned-up marks, so both readings cannot share a cleaning mistake.
- **Teacher review:** everything else, including unclear writing, the two models disagreeing, a reading that differs from the key only by a dot, space or punctuation (for example `17.8` for `178`), and a word one letter away from an accepted answer (for example `BEAK` for `BEAR`, or `d` for `b`).
- **Always teacher review:** tracing, drawings and manual questions.
- **Blank:** zero.

Marking now happens in the background. After submitting, the worksheet shows **Marking** and updates by itself. Handwritten answers take a few seconds each, and answers that need the second model take longer. The first submission after a restart also loads the models.

## 4. Test a paper worksheet as a student

1. Sign in as a test student and open a published worksheet.
2. Select **Print / PDF**, print it at actual size, and write answers in the boxes with a dark pencil or pen. For choice questions, circle one printed option.
3. Photograph the whole page flat and in good light, or scan it.
4. In the worksheet, select **Upload paper copy**, choose the photo or PDF, and select **Upload and mark**.
5. Check the result: empty boxes get zero; clear handwriting is marked; unclear answers wait for the teacher. Open an answer to see the paper crop and the writing the marker isolated.

Without a printer, use a demonstration file: import and publish the original `48544102.pdf` sample, then upload `..\sample-worksheets\student-written-demos\48544102-mixed.synthetic.pdf` as the paper copy.

A photo of a different worksheet, a missing page or an unreadable photo is refused with a message, and the online draft stays unchanged.

## 5. Test a paper upload as the teacher

1. Open **Student results → Upload a paper worksheet**.
2. Choose the worksheet, the student and the photo(s), then select **Upload and mark**.
3. A new numbered attempt is created for that student, keeping earlier results. If the student has an unfinished online attempt with saved answers, the upload asks you to confirm replacing it first.
4. Review pending answers as usual. **Marked PDF** shows the student's own paper page, and the CSV export lists the attempt as "Paper upload".

## 6. Check accuracy honestly on your pupils' writing

The new models read clear digits and short words far better than the old reader, but no model is perfect. During a pilot:

- review a sample of automatically marked answers, especially automatic zeros;
- collect a few dozen real answers the teacher has transcribed (correct **and** incorrect), save them as images with a labels file, and run:

```powershell
.\.venv\Scripts\python tools/evaluate_handwriting.py --labels path\to\labels.json
```

The report counts automatic marks, teacher-review answers, and any unsafe outcome (a right answer marked wrong, or a wrong answer marked right). See [handwriting evaluation](docs/OCR-EVALUATION.md). Keep teacher checking until your own results support unattended marking.

## 7. Tablets and the rest of the classroom

Online answering, **Try again**, teacher review, exports and the tablet checks from the [complete testing guide](TESTING-FROM-START-TO-FINISH.md) work as before. For an iPad on the same private Wi-Fi, start with `run.py --host 0.0.0.0 --port 8001` and open your computer's IPv4 address. Hosted use for real pupils needs HTTPS, backups and a test with a full class submitting at once.
