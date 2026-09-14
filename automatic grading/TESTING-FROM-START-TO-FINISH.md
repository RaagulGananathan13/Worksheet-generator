# Test the grading system from teacher setup to final marks

This guide is for the separate application in `automatic grading`. It explains what to start, how to create accounts, how to use the six supplied worksheets, how to test handwriting and marks, and how to stop without losing your data.

Use fictional student names for these tests. Do not use real pupil records until the launch checks at the end have been completed.

For an existing classroom receiving the student retry/writing-pad update, start with [What to do next](WHAT-TO-DO-NEXT.md). Do not recreate accounts or delete data; restart the server and hard-refresh the browser.

## 1. What is the server setup token?

The server setup token is a temporary administrator setup secret. It proves that the person creating the **first teacher account** has access to the computer running this application. Without it, the first visitor to a new server could make themselves its teacher.

When you start the application with `run.py`, the PowerShell window normally shows a line like this:

```text
First-teacher setup token (keep private): <a-random-value-generated-on-your-computer>
```

Copy **only the random value after the colon** into **Server setup token** on the **Create your classroom** page. Do not copy the example above; use the value in your running server's terminal. Then enter your name and choose your own teacher username and password.

- It is not your teacher password, Windows password, worksheet-generator login, API key or student class code.
- Keep it private. Students do not need it.
- It only works while the selected application database has no teacher account. Once the first teacher exists, use **Sign in** with that teacher's username and password.
- By default, a new random token is generated every time the server starts. If you restart before creating the teacher, use the newest token, not the previous terminal's value.
- `run.py` can still print a token after a teacher exists, but that token cannot create another first teacher.
- If `AG_BOOTSTRAP_TOKEN` was explicitly configured, the terminal instead says that it is using your configured token and deliberately does not print it. Use the value supplied by the server operator. `run.py` does not automatically read a `.env` file.

If you cannot find the terminal and have not created a teacher yet, stop your own grading-server process normally and restart it using section 3. Do not delete the database to get a token.

## 2. Do I need to start the original worksheet generator?

**No, not for testing the grading application with existing PDFs.** Start only the server in `automatic grading`; it serves both its browser interface and its API on port **8001**.

| Task | What must be running? |
| --- | --- |
| Import one of the six original sample PDFs | Only the grading server |
| Teacher/student login, writing, marking, review and reports | Only the grading server |
| Upload a PDF you already exported | Only the grading server |
| Design a new worksheet and export its PDF | The existing generator, using its existing workflow; then import that PDF into grading |
| Run the intern's OCR application | Not needed for this system |

The grading portal does not need the generator's React/Vite server, Express server or MySQL database. Accounts are separate: an existing generator login does not automatically become a teacher or student here.

The integration is: **export blank worksheet PDF → teacher prepares marking areas/key → publish → student answers online or on printed paper → automatic comparison or teacher review → final marks/report**.

Students can hand in two ways: in the online answer areas, or by uploading a photo or scan of the printed worksheet (section 8A). The teacher's **Add worksheet → Upload a PDF** button is different: it imports a *blank* worksheet background, never a student's answers.

## 3. Start the grading server on your Windows computer

### 3.1 Normal start in this existing workspace

Open PowerShell and run (replace `C:\path\to` with the folder where you cloned or copied the repository):

```powershell
cd 'C:\path\to\Worksheet-generator\automatic grading'
.\.venv\Scripts\python run.py
```

Leave this terminal open. The browser application stops responding if the server is stopped.

Open this address in your browser:

```text
http://127.0.0.1:8001
```

Use the same address consistently; `localhost` and `127.0.0.1` are different browser origins and do not share the same login/local recovery storage.

Expected result:

- A fresh database shows **Create your classroom**.
- An existing classroom shows **Welcome back**. Sign in; do not try first-teacher setup again.
- An already logged-in browser may go straight to its worksheet library.

For a basic status check, open `http://127.0.0.1:8001/api/health`. It should return JSON with `ok: true`. This is a status page, not the student application.

### 3.2 Only if `.venv` or dependencies are missing

The local environment was created during development. You do not need to recreate it every time you run the server. On a new checkout/machine, install Python 3.13, then run:

```powershell
cd 'C:\path\to\Worksheet-generator\automatic grading'
python --version
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python run.py
```

Using the full `.venv` Python path avoids PowerShell activation-policy problems. No `npm install`, frontend build or generator startup is needed for normal grading use.

### 3.3 Optional: a completely fresh test classroom without deleting anything

Use this if you want to practise the first-teacher setup again while preserving your current classroom. First stop the grading server you started with **Ctrl+C**. In the same PowerShell window:

```powershell
cd 'C:\path\to\Worksheet-generator\automatic grading'
$gradingTestDirectory = Join-Path (Get-Location).Path ('artifacts\manual-runs\' + [guid]::NewGuid().ToString('N'))
$env:AG_DATA_DIR = $gradingTestDirectory
Write-Output ('Test classroom data: ' + $gradingTestDirectory)
.\.venv\Scripts\python run.py
```

Record the printed **Test classroom data** path so you can return to that classroom. A unique new folder is used; the existing `data/grading.sqlite3` and its student records are not overwritten. Imported document copies and test records go into the new folder. The local handwriting models stay in `automatic grading/data/models` (the `OCR_MODEL_PATH` default) and are shared by every classroom data directory.

Use a fresh browser profile/window or sign out and refresh so an old classroom session is not confused with the new database. For future commands involving this test classroom, `AG_DATA_DIR` must point to this same directory, including account recovery commands.

To return to the normal default classroom later, stop this server with **Ctrl+C**, then run:

```powershell
$env:AG_DATA_DIR = $null
.\.venv\Scripts\python run.py
```

This clears a setting in the current terminal; it does not delete either classroom. If your normal deployment deliberately uses another custom data directory, restore that configured path instead.

## 4. Create the first teacher and record the class code

1. On **Create your classroom**, enter the current server setup token as explained in section 1.
2. For **Your name**, use a test teacher name such as `Demo Teacher`.
3. For **Username**, use a memorable test username such as `teacher.demo`.
4. For **Password**, choose your own password with at least **10 characters**. Store it securely; there is no public email/password-recovery form.
5. Click **Create teacher account**.
6. The teacher library opens. At the top, find **YOUR CLASS JOIN CODE**. Copy or record it for test student registration.

Check that the account role shown near your name is **teacher**, and that **Worksheets**, **Student results** and **Add worksheet** are available.

Keep the teacher browser open. Do not share its credentials with students. The class join code is the invitation students use to register; it does not grant teacher access.

## 5. Import and publish a sample worksheet as the teacher

Start with **48544102.pdf — Add 2** because its typed answers give a simple, repeatable 16-mark test.

1. Click **Add worksheet**.
2. Select **Sample worksheets**.
3. Find **Add 2** and click **Import**.
4. The preparation screen opens with the original PDF and **16 answer areas**.
5. Inspect the original header/footer and all answer areas. No sample source PDF is edited.
6. Select each answer area in the right-hand **Marking key** panel. Check **Question / instruction**, **Answer type**, **Accepted answers**, **Marks** and the area position.
7. For this standard test, keep the preset numeric answers and **1 mark per question**. Keep **Numeric tolerance** at **0**.
8. After checking all 16, tick **I have checked every accepted answer, answer area and mark allocation.**
9. Click **Publish worksheet**, then confirm in the publication dialog.
10. Return to **Worksheets** and confirm that the card says **Published**, with **16 marks**.

The presets are derived draft keys, not teacher-approved answers. The confirmation is meaningful: inspect the answers before publishing. Editing a question clears the confirmation checkbox; check it again only after reviewing your edits.

**Save draft** saves an unpublished worksheet. Students cannot start a draft. On an already published worksheet, **Update & publish** applies your reviewed changes for future attempts; existing attempts retain the marking key they started with.

Repeat the import/review/publication process for the other five samples when ready. The gallery reads the six originals directly from the sibling `sample-worksheets` folder. Re-importing the same content into the same teacher library reuses the existing import; it is not a way to make a fresh student attempt.

## 6. Register a student in a separate browser session

Use a **different browser profile/browser**, or one private/InPrivate window for the student, while leaving the teacher in your normal browser. Two ordinary tabs in one profile share the same session and cannot act as independent teacher and student accounts. Multiple private windows in the same browser may also share one private session.

1. Open `http://127.0.0.1:8001` in the student browser.
2. Select **Join a class**.
3. Enter a fictional name, such as `Demo Correct`.
4. Choose a unique username, such as `demo.correct`.
5. Choose a separate password with at least 10 characters.
6. Enter the teacher's **class code**, not the server setup token.
7. Click **Join classroom**.
8. Check that the role is **student**, and that the published worksheet appears under **My worksheets**.

You should not see the teacher's marking key or teacher editing controls. A student should not need to register again after signing out; use **Sign in** next time.

If the teacher publishes while this page is already open, click **My worksheets** again to refresh the library.

## 7. First full test: typed answers and automatic marks

This checks login, publication, answer saving, deterministic scoring and reporting **without depending on handwriting recognition**.

### 7.1 Enter all correct answers

1. As `demo.correct`, open **Add 2** using **Let's begin**.
2. Select the first numbered answer chip or worksheet answer area.
3. Select **Type instead** in **Your answer space**.
4. Type the answer in **Your answer**.
5. Use **Next** or the numbered chips to complete every question. Select **Type instead** for an answer if the writing pad is shown.
6. Use the values below in printed question order: **down the left column, then down the right column**, not across each row.

| Question | Calculation | Correct answer |
| --- | --- | --- |
| 1 | 2 + 1 | 3 |
| 2 | 2 + 5 | 7 |
| 3 | 2 + 9 | 11 |
| 4 | 2 + 3 | 5 |
| 5 | 2 + 11 | 13 |
| 6 | 2 + 6 | 8 |
| 7 | 2 + 2 | 4 |
| 8 | 2 + 8 | 10 |
| 9 | 2 + 4 | 6 |
| 10 | 2 + 12 | 14 |
| 11 | 2 + 7 | 9 |
| 12 | 2 + 10 | 12 |
| 13 | 2 + 5 | 7 |
| 14 | 2 + 12 | 14 |
| 15 | 2 + 3 | 5 |
| 16 | 2 + 9 | 11 |

### 7.2 Check autosave before submission

1. Wait until the top status says **All answers saved**.
2. Reload the browser page.
3. Verify that all 16 answers are still present and the progress says **16 / 16 answered**.
4. Do not submit while the status says **Saved on this device only**, **Version conflict** or another saving error. Resolve it first.

### 7.3 Submit and inspect the result

1. Click **Submit worksheet**.
2. Read the confirmation, then click **Submit worksheet** again.
3. Wait for marking to complete.
4. With the unchanged approved preset, the result should be **16 / 16**, **100%**, **All answers marked**.
5. Select several answers and check their individual marks and feedback.
6. Open **Marked PDF** and check that it contains the worksheet answers/marks and the result summary.
7. Open **My results** and verify that this attempt is listed as **Marked**.

After submission, that submission becomes read-only. As a student, use **Try again** once it reaches **Teacher review** or **Marked** to start a new blank attempt. Previous handwriting, marks and feedback remain available in **My results**. A teacher can still return the latest submission for corrections; that is different from creating a new attempt. See section 9.4.

### 7.4 Check that a wrong answer does not receive credit

As the same student, click **Try again** and confirm to start attempt 2, keeping the correct first submission. Alternatively, register a second fictional student, for example `demo.wrong`, through the same class code. Sign out before changing student accounts, or use another independent browser profile.

Complete the same worksheet with the answers above, except type **7** for question **16** instead of **11**. Submit. Expected result: **15 / 16 = 93.75%**, with question 16 showing **0 / 1** and **Not correct yet**.

This expected exact result is for **typed** input. A handwritten wrong answer follows the conservative review process in section 8, not necessarily an immediate zero.

Optional blank-response check: with a separate test student, answer the first 15 correctly and leave question 16 blank. The submission dialog should warn about the blank answer; after confirmation, the final result is also **15 / 16**. A genuinely blank response receives zero. An OCR failure on existing ink does not.

## 8. Test real writing, pencil tools and local OCR

### 8.1 Write in the browser

Use a fresh test student such as `demo.ink`, or have the teacher return an existing submitted attempt as described in section 9.

1. Open **Add 2** and select an answer area.
2. Keep **Write with pencil** selected.
3. Write the number with a mouse or supported stylus, either inside the worksheet region or in the larger answer pad beside/below the worksheet. The larger pad helps with small printed boxes.
4. Check that the same ink appears in both views.
5. Test **Pen**, **Eraser**, **Undo last stroke** and **Clear this answer**. The eraser removes whole strokes; it is not a pixel eraser.
6. Finger movement is intended for scrolling by default. Tick **Draw with a finger too** only if you want finger drawing.
7. Wait for **All answers saved**, reload, and verify that the ink is preserved.
8. Fill remaining questions, then submit.

An empty pad explicitly says **Blank answer — no pen strokes**. A first stationary contact selects/focuses the writing surface without creating ink; a real drag starts writing immediately. Once focused, deliberate dot strokes are retained. Printed/ruled guides are visual only. Existing accidental dots in older drafts are preserved until you explicitly erase/clear them; a new **Try again** attempt starts clean.

On a laptop touchpad, hold the left-click button while moving your finger, or use its click-and-drag gesture. Pointer movement alone does not write. The **Draw with a finger too** checkbox controls touchscreen contact, not a laptop trackpad's mouse input.

Typing and handwriting are alternative responses for one area, not two independent answers. Typing replaces that area's ink. Do not switch a response to typing merely to inspect OCR; the recognized result is shown after submission when available.

### 8.2 What result should you expect?

- A confident GLM-OCR reading that matches the key receives full marks automatically.
- A reading that differs from the key is marked wrong only when GLM-OCR is highly confident **and** PaddleOCR-VL independently reads exactly the same thing. Otherwise (uncertain, disputed, a stray dot or punctuation difference, a word one letter away from the key, or a recognizer failure) it waits for teacher review; it is not treated as an incorrect answer.
- The score may show **Marks so far**, **Teacher review** and a count of pending answers. This is a provisional total, not a final percentage.
- Drawing/tracing tasks always need teacher judgment when answered.
- A genuinely blank field receives zero; the printed worksheet background does not count as student writing.

Clear handwriting usually receives automatic marks, but do not expect every handwritten answer to be marked automatically: messy, spaced or very small writing still goes to review. The local models have not been validated as an unattended classroom examiner. Pending review is part of the safety design, not proof that the pupil's answer is wrong.

### 8.3 Check/install the free OCR model

The teacher library shows a warning when local recognition is not configured. For the full status, open `http://127.0.0.1:8001/api/health` and inspect its `ocr` object. A message saying the verified model will load on the first handwritten submission is normal: large weights are loaded only when needed. The first handwriting submission can take longer. Missing OCR does not prevent writing, saving, typed marking or teacher review.

**On the original development computer:** the OCR packages are installed and both models passed verification (GLM-OCR 526 tensors, PaddleOCR-VL 620 tensors). They load on the first handwritten submission. A configured model can still return uncertain readings; installing it does not guarantee correct transcription.

Only on a new installation or if the health page reports missing packages, open another PowerShell terminal and install them:

```powershell
cd 'C:\path\to\Worksheet-generator\automatic grading'
.\.venv\Scripts\python -m pip install -r requirements-ocr.txt
```

On a new computer the models must be downloaded once (below). **After the package installation succeeds**, check their files without downloading them again. This check also needs the optional packages because it validates the safetensors weights:

```powershell
.\.venv\Scripts\python tools/download_model.py --verify-only
```

If the model-file verification above reports missing or invalid files, download the models:

```powershell
.\.venv\Scripts\python tools/download_model.py
```

Installation requires internet access and about **4.6 GB of model weights** (GLM-OCR 2.65 GB, PaddleOCR-VL 1.92 GB), plus packages. Downloads resume if interrupted and are checked against pinned fingerprints. After installation, handwriting recognition runs locally with no paid API or external service. Both models together use roughly 7–11 GB of RAM while marking. Stop and restart the grading server after installation, then sign in and test again.

If a download is interrupted, run the same command again: finished pieces are kept.

The models are used here for short English words and numbers. They are not a reliable general solution for Sinhala handwriting, essays, arbitrary equations or tracing quality. Do not lower confidence thresholds just to obtain more automatic marks. Free software does not mean free hosting, electricity or server capacity.

## 8A. Hand in a printed worksheet (photo or scan)

Use this when pupils work on paper.

1. As the student, open the worksheet and select **Print / PDF** above the page. Print it at actual size (100%).
2. Write the answers on paper with a dark pencil or pen, inside the answer boxes. For choice questions, circle or tick exactly one printed option.
3. Photograph each page flat, in good light, with the whole page visible, or scan it. Avoid shadows across answers and do not crop the page edges.
4. In the student's worksheet, select **Upload paper copy**, choose the photo(s) or PDF scan (up to 10 files, 20 MB each) and select **Upload and mark**.
5. The pages are checked first. If a page cannot be matched (a different worksheet, a missing page, a photo that is too blurry or cut off), the upload is refused with a message and the online draft stays unchanged.
6. Otherwise the attempt shows **Marking** and updates by itself. Open any answer to see the crop of the paper and the writing the marker isolated with the printing removed.

A teacher can upload for a student: **Student results → Upload a paper worksheet**, choose the worksheet and student, add the photo(s) and upload. A new numbered attempt is created, so earlier results stay. If the student has an unfinished online attempt with saved answers, tick the box to mark the paper copy instead.

What to expect:

- Empty answer boxes receive zero. Very light marks, answers partly outside the photo, and several marked options wait for the teacher.
- Handwriting follows the same rules as section 8.2.
- Tracing and drawing always wait for the teacher.
- The **Marked PDF** uses the student's uploaded page as its background, and the CSV export lists the attempt as "Paper upload".

Quick test without a printer: the 12 files in `sample-worksheets/student-written-demos` are the original pages with constructed ink drawn on them, so they work as paper uploads. Import and publish the matching original sample, start it as a test student, then upload for example `48544102-mixed.synthetic.pdf` with **Upload paper copy**. Its blank answer receives zero; the handwritten answers are marked by the local models or wait for review.

## 9. Teacher review, final results, exports and another try

### 9.1 Resolve pending answers

1. Return to the teacher browser and click **Student results**.
2. Click **Refresh** if the student's latest submission is not yet shown.
3. Find the student's worksheet. If it says **Teacher review**, click **Review**.
4. Select a pending answer chip.
5. Look at the **actual saved ink** in the answer pad/worksheet. Compare it with **Teacher marking key**. Do not approve a mark solely because the OCR's **Read as** text looks plausible.
6. Enter **Awarded marks** between 0 and the question maximum. For these samples, each question is worth 1; a teacher may award an appropriate partial value when their rubric allows it.
7. Optionally correct **Read as (optional)** and add **Feedback for student**.
8. Click **Save teacher mark**.
9. Repeat for every pending answer.

When all answers have marks, the result becomes **Marked** and a final percentage appears. For a completely correct answered sample with the default one-mark key and satisfactory tracing where required, the teacher-confirmed score can reach its full total.

The teacher may also review an automatically marked answer and correct its marks. The review is recorded and the total recalculated.

### 9.2 Check what the student sees

In the student's browser, reopen **My results** and the attempt. Check the final marks and teacher feedback. Students see their own answers and feedback, not the private accepted-answer list or another student's worksheet.

### 9.3 Export evidence

- In the attempt, use **Marked PDF**. Check worksheet appearance, ink, question marks, student identity and summary. This is an annotated report copy; the original uploaded PDF stays unchanged.
- In the teacher's **Student results**, use **Export marks CSV**. Open it in Excel or another spreadsheet and verify the student, worksheet, status and totals. Pending totals remain provisional; do not report them as final percentages.
- The **PDF** link above the worksheet downloads its original background, not the annotated student report.

Generated report text currently uses a basic Latin font. Non-Latin names/feedback may render incorrectly in the PDF even though their values remain in the browser/database/CSV. Test the client's required languages before relying on these reports.

### 9.4 Student: redo a worksheet without losing previous results

1. Open a submitted worksheet from **My results** or the worksheet library.
2. When it says **Teacher review** or **Marked**, click **Try again** and confirm.
3. A **new blank attempt** opens with the next attempt number. You do not need the teacher to finish reviewing the previous attempt first.
4. Write/type the answers, wait for **All answers saved**, and submit normally.
5. In **My results**, check that both attempts are present with their own answers, marks and feedback. The older pending attempt can still be reviewed by the teacher.
6. The library opens your latest attempt. Use the results list to revisit older submissions. PDFs and teacher CSV exports identify attempt numbers.

The teacher must still have the worksheet published, and you cannot retry while a submission is actively **being marked**. Repeated clicks reuse an existing newer draft instead of creating duplicate active attempts. A new attempt uses the teacher's current published marking key; previous attempts keep their original keys.

### 9.5 Teacher: return the latest submission for corrections

1. As teacher, open the submitted attempt.
2. Click **Return for another try** and confirm.
3. Existing answers/ink are preserved, but the attempt's current marks/results are cleared.
4. The student refreshes **My worksheets**, opens **Keep going**, changes the response, waits for saving and submits again.
5. Review the new result as necessary.

Returning an attempt does **not** replace its original rubric snapshot with a newly edited marking key. If the key was wrong, correct that student's marks through teacher review. To test a revised worksheet key end-to-end, publish the revision and start an attempt with a student who has not previously started that worksheet.

The teacher cannot return an older attempt after the student has started a later one. Review the older submission's marks normally, or work with the latest attempt. Students can test a revised published key using **Try again** without registering another account.

## 10. The separate student-written demonstration PDFs

The earlier verification included screenshots and small digital-stroke checks, not a set of filled versions of all six PDFs. In response to your request, **12 filled demonstration PDFs and 12 matching digital-ink JSON files** have now been created under:

```text
sample-worksheets\student-written-demos   (inside the repository folder)
```

Read [that folder's README](../sample-worksheets/student-written-demos/README.md) for its exact inventory and expected answers. The original six PDFs in `sample-worksheets` remain untouched. Each original now has a `correct` demonstration and a `mixed` demonstration:

- `ID-correct.synthetic.pdf`: automatic-capable responses are intended to be correct. The tracing examples still require a teacher to assess shape/placement.
- `ID-mixed.synthetic.pdf`: the first automatic-capable response is wrong, the second is blank, and the rest are intended to be correct.
- Matching `ID-correct.synthetic.json` and `ID-mixed.synthetic.json`: the constructed digital strokes/choices used for each PDF.
- `manifest.json`: source/output fingerprints and the intended response values for inspection.

For example, `48544102-mixed.synthetic.pdf` contains **14 intended correct answers, 1 wrong answer and 1 blank**. After human verification, its intended final total is **14/16 = 87.5%** with the standard one-mark key. This is a different test from the manually typed **15/16** scenario in section 7. OCR may initially leave many of its handwritten answers pending.

These are **synthetic demonstration responses** made from constructed digital strokes, not handwriting collected from real students. A PDF showing the right intended answers does not prove the recognizer will read those strokes correctly. They are useful for inspecting placement, comparing correct/incorrect work, and exercising the save/review/report workflow; they are not a representative OCR accuracy benchmark.

### 10.1 Open the PDFs for visual checks

1. Open a generated PDF in your normal PDF viewer.
2. Compare it with the corresponding original sample PDF.
3. Verify that the intended answers sit inside the correct boxes and that the header/footer remain visible.
4. Use the demo folder's README/JSON metadata to understand which responses were deliberately incorrect or require manual review.

**Do not upload these completed PDFs with the teacher's Add worksheet → Upload a PDF button**: that button imports a blank worksheet background. To have them marked, upload them as a paper copy inside a student attempt, or with **Student results → Upload a paper worksheet** (section 8A).

### 10.2 Replay the paired synthetic digital ink into a test student draft

The paired `.synthetic.json` fixtures allow the same constructed writing to enter the supported online-answer workflow without pretending that it was extracted from a PDF.

Preparation:

1. Keep the local grading server running on `http://127.0.0.1:8001`.
2. As teacher, import **the original corresponding sample** from the gallery, check the preset and publish it. Keep the fixture's answer regions/question types unchanged for a matching replay.
3. Register a dedicated fictional student in that teacher's class, for example `demo.replay`. Use an unused attempt or an empty draft.
4. Close that student's worksheet editor tab while the helper saves, so a browser autosave cannot race with the helper. You can open it after the helper finishes.
5. In a second PowerShell terminal, run:

```powershell
cd 'C:\path\to\Worksheet-generator\automatic grading'
.\.venv\Scripts\python tools/replay_demo_submission.py --fixture '..\sample-worksheets\student-written-demos\48544102-correct.synthetic.json' --username demo.replay
```

Enter that **student's password** at the hidden password prompt. Do not enter the teacher password, class code or server setup token. The helper is for the local server; it is not a production bulk-import tool.

By default it **saves a draft only**. The helper signs out its own session afterward; it does not log the browser in for you. Sign in through the ordinary browser form as that student, open **Add 2 / Keep going**, inspect the imported ink, and submit through the browser. Then follow section 9 to review any pending marks.

Alternative for an **empty/unused draft**: add `--submit` on your first replay command to save and submit through the real marking API. Choose this instead of the save-only command above. If you already saved that fixture, submit it in the browser; rerunning the helper without explicit replacement will correctly refuse the now-nonempty draft.

```powershell
.\.venv\Scripts\python tools/replay_demo_submission.py --fixture '..\sample-worksheets\student-written-demos\48544102-correct.synthetic.json' --username demo.replay --submit
```

Only use the following if you deliberately want to replace that test student's existing, nonempty draft answers with the fixture:

```powershell
.\.venv\Scripts\python tools/replay_demo_submission.py --fixture '..\sample-worksheets\student-written-demos\48544102-correct.synthetic.json' --username demo.replay --replace-draft
```

`--replace-draft` is an explicit overwrite of the selected test draft. It does not reopen a submitted attempt or create a retry. For submitted work, sign in as the student and click **Try again** first; the helper then finds that new draft. Alternatively, a teacher can return the latest attempt, or you can register a fresh test student. Never use these overwrite examples against real pupil work.

Repeat with other fixture filenames listed in the demo folder. Replay checks the actual online marking path: OCR may leave even intended-correct synthetic answers pending. Use the typed test in section 7 when you need a deterministic 16/16 scoring check.

## 11. Test all six original sample PDFs

These totals assume the unchanged draft presets have been reviewed and approved. All samples have one page. Their combined total is **82 answer areas/marks**: **77 numeric/choice areas** and **5 manual tracing areas**.

| Original PDF / gallery title | What to enter or check | Expected completion with approved correct responses |
| --- | --- | --- |
| `19963892.pdf` / Basic division III | Three word-problem results and eight quotients | 11/11 using correct typed numbers; handwritten responses may need review. Only final answers are marked, not division method. |
| `35879581.pdf` / Subtract from 92 | 20 numeric answers, down each column | 20/20 using correct typed numbers. |
| `36635880.pdf` / Write and trace 21–25 | Ten number-writing areas and five pale-digit tracing tasks | With ten correct typed numeric answers and ink in all five tracing areas: 10 confirmed marks, 5 pending; 15/15 only after satisfactory tracing is reviewed. Do not leave tracing blank and expect it to be pending. |
| `48544102.pdf` / Add 2 | 16 additions in the table above | 16/16 all correct typed; 15/16 for one wrong typed answer. |
| `91903282.pdf` / Count and complete numbers | Tap four object-count choices; fill six flower gaps | 10/10 with correct taps and typed gap answers. Choice selection does not require OCR. |
| `96056280.pdf` / Complete the number sequences | Six chain gaps and four frog gaps | 10/10 using correct typed numbers. |

For question-by-question keys and layout explanations, read [docs/SAMPLES.md](docs/SAMPLES.md). Do not guess order from where fields appear: some worksheets are numbered down columns. For tracing, follow each area's **Question / instruction** rather than assuming the first five chips are all of one type.

For **Count and complete numbers**, select **7 ants**, **5 apples**, **9 balls** and **4 bamboo plants** by tapping the relevant choice on the page or in the answer panel. Test that tapping a different choice changes the selection and that reloading preserves the final choice. Do not draw freehand circles over printed digits as a substitute for the choice control.

To inspect every preset area as an image, run:

```powershell
.\.venv\Scripts\python tools/preview_regions.py
```

Open the generated PNGs under `automatic grading/artifacts/region-previews`. These are copies showing answer areas and draft keys; they do not alter the original PDFs. They contain answers, so keep them out of the student's test view.

## 12. Import and test a newly generated worksheet

This is the step where the original worksheet-generation tool may be needed.

1. Use the generator as usual to create a **blank student worksheet** and export its PDF.
2. Leave the grading server running. The generator can be stopped after export if you do not need it for further editing.
3. In the grading teacher account, click **Add worksheet → Upload a PDF**.
4. Enter a **Worksheet title**, select the exported file, and click **Upload worksheet**.
5. For an unfamiliar PDF, click **Add answer area** and drag a rectangle over each student response location. Use **Add area by coordinates** if that is easier, and adjust the selected region's position/size when necessary.
6. For each region, enter its instruction, answer type, accepted answer(s) and marks. Use one accepted answer per line. Use **Drawing / teacher review** for subjective answers, working, tracing or drawings.
7. Save the draft, inspect every field, confirm the key and publish.
8. Sign in as a test student, complete it, submit, review and export as in sections 7–9.

Limits: PDFs must be valid, unencrypted, no more than **20 MB** and **10 pages**. Unknown layouts do not get reliable question detection or answer-key generation automatically. Exact content matching can recover the known presets for the original samples, even if an original PDF is renamed; a modified/completed PDF is different content.

## 13. Test on an actual iPad or Android tablet

Browser automation is not a replacement for checking the client's actual device and pencil.

1. Connect the Windows computer and tablet to the same **trusted private Wi-Fi network**.
2. Stop your grading server with **Ctrl+C**.
3. Start it with:

```powershell
.\.venv\Scripts\python run.py --host 0.0.0.0 --port 8001
```

4. In another PowerShell terminal, run `ipconfig`. Find the **IPv4 Address** of the active Wi-Fi/Ethernet adapter connected to that network, for example `192.168.1.25`.
5. On the tablet, open `http://192.168.1.25:8001`, replacing that example with the computer's actual IPv4 address. **Do not use `127.0.0.1` or `0.0.0.0` on the tablet**; those are not the address of your Windows server from the tablet.
6. If Windows Firewall asks, allow access only on the appropriate trusted **Private** network. Do not disable the firewall, open the port to the public internet or configure router port forwarding for this test.
7. Sign in as a fictional student and complete a worksheet using Apple Pencil or the intended stylus.

Check all of the following:

- The first pen stroke is captured; slow and fast writing both remain visible.
- Resting a palm does not create unwanted answers on the actual hardware.
- Finger scrolling, surrounding-page scrolling and writing work without accidental strokes.
- The large answer pad, choice taps, undo, eraser and clear behave correctly.
- Portrait/landscape rotation preserves stroke placement.
- Briefly switching apps and returning preserves saved work.
- Reloading after **All answers saved** restores the same strokes.
- The student can submit and the teacher can view exactly that ink.

Local LAN HTTP is for a controlled fictional-data test. Host real student use over **HTTPS**. If `AG_SECURE_COOKIES=1` was set for hosting, it must not be used with ordinary local/LAN HTTP, or login cookies will not work as intended. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the supplied HTTPS hosting configuration.

## 14. Recovery, conflict and access-control checks

Use only dedicated test accounts and drafts for these checks.

### Brief loss of connection

1. Open a test student's draft and save an initial answer.
2. Temporarily disconnect that browser/device from the network while keeping the page open.
3. Add another answer. Confirm the warning that the draft is saved on this device only.
4. Reconnect and use **Retry save** if needed. Wait for **All answers saved**.
5. Reload and check that both answers are present.

Local recovery is a fallback, not a backup. Keep the same browser profile/origin, do not clear site data, and do not sign out while answers remain unsaved. Signing out deliberately clears that account's local recovery copies after warning about unsaved work. If offered a conflict dialog, use **Download local draft** to preserve your local response before choosing a server copy. There is no general UI importer for arbitrary downloaded local drafts.

### Two devices/tabs editing one attempt

1. Open the same student's draft in two tabs/devices.
2. Save an answer in the first.
3. Try changing/saving from the stale second copy.
4. Expect **Version conflict**, not a silent overwrite of the newer answer.
5. Preserve a local draft if needed, then use **Load server copy** and reconcile deliberately.

Normal classroom use should have one active editor for each student's attempt.

### Account separation

1. Confirm that a student does not see teacher editing controls or private marking keys.
2. Copy a test attempt URL while logged in as one student. Try opening it as a different student in another independent browser profile. Access should be denied; it must not display the first student's answers.
3. Sign out and reload a private worksheet/report URL. It should require authentication rather than expose student data.
4. Confirm that teacher results show only their own class. If you need a second teacher for a controlled test, create one through the operator tool below, not first-teacher bootstrap again.

## 15. Automated checks you can run yourself

Open another PowerShell window. These commands run the code checks; they do not replace the manual classroom tests above. The complete Python suite includes OCR tests, so it needs the optional packages from section 8.3. The model weights are not needed for these controlled unit tests. With only `requirements.txt`, the portal can run but OCR tests need the optional dependencies.

```powershell
cd 'C:\path\to\Worksheet-generator\automatic grading'
.\.venv\Scripts\python -m unittest discover -s tests -v
node --test tests/ink.test.mjs tests/session.test.mjs
node tools/browser_smoke.cjs
node tools/student_retry_smoke.cjs
node tools/paper_upload_smoke.cjs
```

The latest run passed **127 Python tests**, **22 JavaScript tests**, the **16-check browser workflow**, the **15-check retry/writing browser workflow** and the new **11-check paper-upload browser workflow**. See [docs/VERIFICATION.md](docs/VERIFICATION.md) for scope and limitations; judge your own run by its final success/failure output.

- Python tests create temporary test stores and exercise scoring, PDF imports/reports, authentication, ownership, key privacy, review and saving/version behavior.
- JavaScript tests require Node.js; they test ink/session behavior without starting the generator.
- The browser smoke test uses the already installed `backend/node_modules/puppeteer` package for testing only. The generator service itself stays stopped.
- The browser script starts/stops **its own server on port 8017**, refuses to use an already running server there, and places disposable test data under `automatic grading/artifacts/browser-runs`. Your manual server on 8001 may remain running.
- Browser screenshots/result JSON/logs are under `automatic grading/artifacts/browser`.
- The browser test deliberately disables the OCR model for predictable review-path checks. A passing browser smoke test does **not** prove real handwriting accuracy.
- `student_retry_smoke.cjs` uses its own isolated server on **8021**, refuses an occupied port, and stores test data/screenshots/results under `artifacts/student-retry-runs`. It checks empty ink, selection taps, intentional dots, first strokes, numbered retries, retained history and 16/16 typed scoring. It also uses a deliberately unavailable model, not your running classroom.

If Puppeteer is absent in a separate deployment copy, that browser script needs its documented repository dependency before it can run; this does not mean the normal grading server needs Node.js or the generator to operate. Do not install dependencies into the original generator merely to follow the grading walkthrough without reviewing that change separately.

## 16. Stop, restart, password recovery and preserve your data

### Stop and resume

1. Finish saving student drafts and teacher edits.
2. Sign out on shared devices.
3. In the grading server terminal, press **Ctrl+C**.
4. Restart with the same command and **same data-directory setting** to recover the same classroom.

Normally, records are in `automatic grading/data/grading.sqlite3` and imported PDFs/pages in `automatic grading/data/documents`. A custom `AG_DATA_DIR` puts classroom records/documents in that directory instead. Stopping the server does not remove these records.

Do not delete `data`, remove the SQLite database or rerun setup against a new folder expecting previous accounts to follow automatically. For a consistent backup, stop the application and back up the whole classroom data directory to private storage. Do not copy only a live SQLite file while the server is writing. Test backup restoration separately before real use.

### Forgotten password

There is no public reset-by-email screen. A trusted operator with access to this Windows account can run, from `automatic grading`:

```powershell
.\.venv\Scripts\python tools/manage_users.py reset-password teacher.demo
```

Replace `teacher.demo` with the actual username. Enter the new password twice at the hidden prompts. The command revokes that account's existing sessions. It works for student accounts too.

If using a custom test/host data directory, set `AG_DATA_DIR` to that exact directory in this terminal first. A new PowerShell window does not inherit a setting typed into a different existing window.

### Additional teacher account

After the database has been initialized, a trusted local operator can create a separate teacher and class:

```powershell
.\.venv\Scripts\python tools/manage_users.py add-teacher teacher.second --name 'Second Demo Teacher'
```

Choose the password at the prompts and record the resulting new class code. Do not give students terminal access to these operator commands.

## 17. Troubleshooting checklist

| Symptom | What to check |
| --- | --- |
| What do I enter for server setup token? | The current random value printed by your own `run.py` terminal, or the explicitly configured `AG_BOOTSTRAP_TOKEN`. See section 1. |
| Token rejected | Check that the value is from the currently running server, has no copied label/extra spaces, and that a first teacher has not already been created. Do not retry indefinitely; authentication is rate-limited. |
| Setup page appears again after restart | You may be using a different `AG_DATA_DIR`, different server/port or fresh database. Return to the original data directory instead of creating unrelated replacement accounts. |
| `.venv\Scripts\python` not found | First `cd` into `automatic grading`; then follow the one-time install steps if the environment is genuinely absent. |
| Browser cannot connect | Keep the grading terminal running, check startup errors and the exact port. On a tablet, use the computer's actual LAN IP, not loopback. |
| Port 8001 already in use | The grading server may already be running. Use that server or stop your own earlier server normally. Do not kill an unknown process. An alternative is `run.py --port 8002` and the matching browser URL; demo replay defaults to 8001. |
| Student sees no worksheet | Check the class code/teacher, publish status, and refresh **My worksheets**. A saved draft is not a published worksheet. |
| Teacher and student keep replacing each other's login | Use independent browser profiles/browsers, not two ordinary tabs sharing cookies. |
| Login loops on ordinary HTTP | Check whether production `AG_SECURE_COOKIES=1` is set. Use local settings for fictional HTTP testing; use HTTPS for hosted student use. |
| Sample gallery missing/rejecting a sample | Keep the six original PDFs in the sibling `sample-worksheets` folder with their original filenames/content. Presets are hash-checked. Generated filled demos are not replacements for originals. |
| Publish refuses | Review every area, supply valid accepted answers for automatic question types, and tick the confirmation after your last edit. |
| Handwriting stays pending | Check the local OCR status and the writing. Uncertain or disputed readings need review by design; an automatic wrong mark needs both models to agree. Read section 8 before changing any settings. |
| Correct typed answers get unexpected marks | Verify the question order, accepted key, point allocation and the attempt's original rubric snapshot. A later worksheet edit does not silently change an existing attempt. |
| Cannot change a submitted response | Use **Try again** as student for a new blank attempt, preserving the old result. The teacher can instead return the latest submission for corrections. A new login does not reset a submission. |
| A completed PDF added with Add worksheet shows no score | That button imports blank worksheet backgrounds. Upload completed pages with **Upload paper copy** (student) or **Upload a paper worksheet** (teacher). |
| Paper upload refused | Check that it is the same worksheet, every page is included once, and the whole page is visible, flat and sharp. Retake the photo in better light. |
| Marking takes a while | Handwriting is read on the server's CPU, one attempt at a time, and the models load on first use. The attempt shows Marking and updates by itself; keep the page open or come back later. |
| Unsaved/conflict warning | Keep the tab open, preserve the local draft if offered, reconnect/retry or load the newer server copy deliberately. Never assume an unsent response is in the server database. |

## 18. Was the intern's old system used?

The new portal is a **new standalone implementation**, not the old intern server with a new screen.

The intern's code was inspected to understand its image-based setup, answer boxes and marking approach. The general idea of teacher-defined normalized answer regions is useful and was redesigned here. However, this application does not import or start the intern's backend, reuse its paid API calls, depend on its `.env`, or use its old templates as keys for these six PDFs.

New code handles teacher/student authentication, online pressure-bearing ink, PDF importing, the sample presets, marking rules, free local OCR integration, save conflicts, rubric snapshots, teacher review, marks, reports and hosting configuration. The old handwriting examples were used read-only for a small diagnostic model evaluation; that is different from running the old application. The paper-upload feature re-implements two of the intern's ideas with tests: normalized answer regions, and aligning a photo to its template by feature matching. The intern's photographed test sheets are used read-only to measure the paper pipeline.

For the detailed reasoning and file-level assessment, see [the intern OCR audit](docs/LEGACY-OCR-AUDIT.md) and [project analysis](docs/PROJECT-ANALYSIS.md).

## 19. Final acceptance: when is it ready for a client pilot?

Finish with this checklist and keep the exported test reports as evidence:

- [ ] First-teacher setup, ordinary sign-in, student enrollment and logout work.
- [ ] A teacher has independently checked and approved every sample key/answer region/mark.
- [ ] All-correct typed **Add 2** gives **16/16**, and one wrong typed answer gives **15/16**.
- [ ] All six original sample layouts are checked; tracing goes through teacher review.
- [ ] A photographed and a scanned paper copy are marked, and a photo of a different worksheet is refused.
- [ ] Real device ink survives saving, reload, rotation and a brief network interruption.
- [ ] Pending OCR responses are reviewed from their actual ink and end with correct final totals.
- [ ] A student cannot access another student's work or the teacher's private key.
- [ ] Marked PDF and CSV values agree with the on-screen final marks.
- [ ] The required languages display correctly in exported reports, or the report limitation is addressed.
- [ ] Teacher returning an attempt, resubmission and password recovery are tested.
- [ ] Backup/restore, HTTPS hosting, device compatibility and simultaneous classroom load are tested on the actual deployment.
- [ ] Representative real student handwriting has been labelled and evaluated, including incorrect answers; automatic acceptance and teacher-review workload are acceptable (`tools/evaluate_handwriting.py --labels`).

Passing the software checks or replaying constructed demo ink does not prove handwriting accuracy. The current result should be piloted with **teacher-supervised marking** until those real-classroom checks support a stronger claim.
