# Synthetic student-answer test copies

These files were generated for testing. They contain **constructed digital pen strokes**, not real students' handwriting. The blue responses and red `SYNTHETIC TEST COPY` label distinguish them from your original blank worksheets. The six original PDFs in the parent folder are unchanged.

## What is in this folder?

For each of the six worksheet IDs there are two scenarios:

- `ID-correct.synthetic.pdf`: numeric/selection answers are intended to be correct. Manual tracing is only an approximate writing example and still needs human assessment.
- `ID-mixed.synthetic.pdf`: the first non-manual answer is deliberately wrong, the second is blank, and the other numeric/selection answers are intended to be correct.
- Matching `.synthetic.json` files: the exact saved digital pen strokes/choices used to draw each PDF. These let you test online answer submission through the replay helper without an iPad.
- `manifest.json`: source fingerprints, generated PDF fingerprints, intended answer values and which responses were deliberately wrong/blank. This is test documentation, not a grading key sent to OCR.

There are **12 demonstration PDFs and 12 matching digital-ink files**.

| Source ID | Worksheet | Correct-case intended automatic-capable answers | Mixed-case intended automatic-capable answers |
| --- | --- | --- | --- |
| 19963892 | Division | 11 correct | 9 correct, 1 wrong, 1 blank |
| 35879581 | Subtraction | 20 correct | 18 correct, 1 wrong, 1 blank |
| 36635880 | Write and trace 21–25 | 10 numeric correct + 5 manual tracing regions | 8 numeric correct, 1 wrong, 1 blank + 5 manual tracing regions |
| 48544102 | Add 2 | 16 correct | 14 correct, 1 wrong, 1 blank |
| 91903282 | Count and complete | 10 correct | 8 correct, 1 wrong, 1 blank |
| 96056280 | Missing numbers | 10 correct | 8 correct, 1 wrong, 1 blank |

These are **intended written answers**, not promised OCR scores. Unclear synthetic writing may go to review. Handwriting that differs from the key is marked wrong only when both local models agree; otherwise it waits for a teacher. A blank answer is zero. Selection choices are scored directly without OCR. The five tracing tasks never receive automatic shape-quality marks.

## Using these PDFs as paper uploads

The portal marks printed worksheets from photos or scans, and these PDFs work as test uploads because they are the original page with constructed ink drawn on it. Import and publish the **original blank PDF** from the parent folder, start that worksheet as a test student, then choose **Upload paper copy** and select the matching `ID-correct` or `ID-mixed` PDF. A teacher can instead use **Student results → Upload a paper worksheet**. All 12 were checked: every page aligns, each blank answer is detected as blank, and each circled choice is read correctly.

Do **not** upload them with the teacher's **Add worksheet → Upload a PDF** button: that imports a new blank worksheet background, not a student's answers.

For a replay test, create a test student and publish the matching original worksheet first. From `automatic grading`:

```powershell
.\.venv\Scripts\python tools/replay_demo_submission.py --fixture '..\sample-worksheets\student-written-demos\48544102-correct.synthetic.json' --username student.demo
```

Enter that student's password when prompted. By default the helper saves a draft without submitting. Sign into the student browser and inspect the blue ink, then submit through the browser. Alternatively, add `--submit` to save and submit through the real API. Use separate test students for the correct and mixed scenarios, or explicitly reopen an attempt as teacher before replacing its draft.

Existing nonempty drafts are protected: the helper refuses to replace them unless you deliberately specify `--replace-draft`. It never changes a teacher's key, directly writes the database, or silently reopens a marked attempt. Its default/local-only endpoint is `http://127.0.0.1:8001`.

The helper signs out its own session when finished. It does not log in the browser for you; use the ordinary student sign-in form to inspect the saved attempt.

## Start-to-finish instructions

Read [the complete testing guide](../../automatic%20grading/TESTING-FROM-START-TO-FINISH.md) for setup tokens, teacher/student accounts, all six samples, expected results, iPad checks, mark review, exports and troubleshooting.

The generator script is `automatic grading/tools/generate_student_demos.py`. It refuses to overwrite an existing demo set. You do not need to rerun it; this folder already contains the generated files.
