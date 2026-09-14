# Handwriting recognition: model selection and evaluation

Evaluated 2026-09-14 on the development laptop (Intel i7-1195G7, 4 cores, 16 GB RAM, CPU only) with outbound network connections blocked during inference. Labels were written by eye and compared only after each model had read the image; prompts never contained answers. These are small diagnostic sets, not a calibrated classroom accuracy estimate.

## Decision

- **GLM-OCR** (`zai-org/GLM-OCR`, MIT, revision `2e85a62840ccac27daa451df36c736c4636b8628`, weights SHA-256 `a16eb0de…9498815`) reads every handwritten answer.
- **PaddleOCR-VL-1.5** (`PaddlePaddle/PaddleOCR-VL-1.5`, Apache-2.0, revision `2a4195faa5e7914c12f2fc601d72c81caf8d2da5`, weights SHA-256 `d557c9d8…73f8958`) is consulted only when a confident GLM-OCR reading differs from the answer key. For paper answers it reads the untouched photo of the answer area rather than the isolated marks.
- Both load from local safetensors through Transformers with `trust_remote_code=False`, in float32 on CPU. `tools/download_model.py` installs and verifies them.

Marking rules (`app/grading.py`, `app/ocr.py`):

| Outcome | Requirement |
| --- | --- |
| Correct | GLM-OCR reading complete, well formed (a number, or English words), minimum token probability ≥ 0.90, and equal to an accepted answer |
| Wrong (zero) | GLM-OCR ≥ 0.95, PaddleOCR-VL reads exactly the same value at ≥ 0.75, and the reading is not a near miss (spacing/punctuation only, or one letter away in a word) |
| Teacher review | everything else: low confidence, malformed readings, disagreement, near misses, model errors, tracing/drawing |

## Why these models: head-to-head benchmark

All candidates are free, run locally and load without remote code. Each read the same prepared images. "Exact" compares the reading with the label, ignoring letter case.

| Model | Saved classroom ink (17 readable answers, mouse/trackpad) | Paper photo crops (38 answers, printing removed) | Constructed digital ink | Speed on this CPU | Result |
| --- | --- | --- | --- | --- | --- |
| TrOCR-base (former reader) | 0 answers qualified; digits split ("1 2 1") or garbled ("dent left .") | 0 of 8 qualified in the earlier crop test | 1 of 6 qualified | ~3 s | Replaced |
| **GLM-OCR** | **14 exact**; 2 more differ only by a stray dot actually present in the ink ("17.8", "2.") | **33 exact**; 31 of its 32 readings at ≥ 0.90 were right | **68 of 68 exact** | ~1–10 s | **Primary** |
| **PaddleOCR-VL-1.5** | **15 exact**; read 151 as "51" and one staircase "44" as symbols | read digits and words well; lower confidences (0.45–0.99) | not needed | ~7–22 s (attention cache on) | **Second opinion** |
| Qwen3.5-2B | 2 of the first 6 exact ("394" for 384; digits wrapped in `$…$`) | 19 of the first 20 exact (isolated and raw crops) | not run | 25–60 s | Rejected: slow, weaker |
| LightOnOCR-2-1B | not usable | 0 of 33: empty or repeated formatting output; enlarged input produced invented "Lorem ipsum" text | not run | 8 s; 482 s enlarged | Rejected: page-level model |

The one confident GLM-OCR error mattered: a photographed "TEDDY BEAR" whose faint pencil R was partly removed during mark isolation was read as "TEDDY BEAK" at 0.988, and PaddleOCR-VL read the same damaged image the same way at 0.975. Three changes followed: faint strokes that continue a kept stroke are now kept; the second model reads the untouched photo instead of the isolated marks; and a word one letter away from an accepted answer always goes to the teacher. In the full evaluation below, that answer goes to teacher review instead of receiving a zero.

GLM-OCR also read the isolated marks better than raw photo crops (33 versus 27 exact on the same 38 answers): raw crops invited readings such as "4....." from printed dotted lines.

## Full pipeline evaluation

Every example ran through the installed pipeline: paper photos were aligned to their blank templates with the printing removed, digital ink was rendered as the server does, and grading was simulated twice, once with the label as the answer key (the student was right) and once with a different key (the student was wrong). Thresholds: count 0.9, wrong 0.95, confirm 0.75.

| Source | Answers | Exact first reading | Right answer: marked correct | Right answer: review | Right answer marked **wrong** | Wrong answer: marked wrong | Wrong answer: review | Wrong answer marked **right** | Median time |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| photographed paper | 38 | 34 | 33 | 5 | 0 | 26 | 12 | 0 | 5.75 s |
| private labelled answers | 11 | 9 | 10 | 1 | 0 | 6 | 5 | 0 | 7.03 s |
| constructed digital ink | 30 | 30 | 30 | 0 | 0 | 30 | 0 | 0 | 10.47 s |

**Unsafe outcomes in these runs: 0.** No right answer was marked wrong and no wrong answer was marked right.

"Review" is the safe outcome: the teacher sees the writing and decides. The simulated wrong key is a different accepted answer (the label plus one for numbers, another word for text), so a "marked wrong" count shows how often a clearly different answer was confirmed by both models. Median time includes the second model whenever a reading differed from the key, which happens for every wrong-key simulation; real worksheets need the second model only for answers that seem wrong.

Sources: “photographed paper” is 38 answers on six phone photos of printed worksheets from `OCR/test cases (2)`; “private labelled answers” is 11 unambiguous mouse/trackpad answers saved in the local classroom database; “constructed digital ink” is the first 30 numeric answers of the synthetic demo fixtures. Reports: `artifacts/handwriting-evaluation-photos-and-saved-ink.json` and `artifacts/handwriting-evaluation-demos.json`.

## Known limits

- Letters written over pale printed tracing guides are mostly removed with the guide, so they go to teacher review.
- Very faint pencil, spaced-out digits, symbols and fractions, multi-line sentences and Sinhala are not dependable; they go to review or should be manual questions.
- Model confidence is a screening signal, not an accuracy percentage. Two models can still agree on a genuinely ambiguous glyph (a child's 1 that looks like 7). Keep reviewing automatic zeros during a pilot.
- Timings were measured with other work running at the same time; allow for the first-load delay after a restart.

## Reproduce

Run inside `automatic grading` with the models installed:

```powershell
.\.venv\Scripts\python tools/download_model.py --verify-only
.\.venv\Scripts\python tools/evaluate_handwriting.py --photos --labels artifacts\handwriting-labels\saved-classroom-ink.json --output artifacts\handwriting-evaluation-photos-and-saved-ink.json
.\.venv\Scripts\python tools/evaluate_handwriting.py --demos --limit 30 --output artifacts\handwriting-evaluation-demos.json
```

`--photos` needs the intern's photographed sheets in `../OCR/test cases (2)`. `--labels` takes a private JSON list of `{"image", "kind", "label"}`; the saved-classroom-ink set is kept under the ignored `artifacts` folder because it comes from the local classroom database. Use a teacher-labelled set of real pupils' answers, including incorrect ones, before relying on unattended marks.

## History

The earlier TrOCR evaluation found that none of eight scanned handwriting crops and only one of six constructed digits passed its gate, and all 17 handwritten answers saved in the classroom database waited for review. Those scripts are archived in `tools/retired_trocr_experiments`.

Sources: [GLM-OCR model card](https://huggingface.co/zai-org/GLM-OCR), [PaddleOCR-VL-1.5 model card](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.5), [LightOnOCR-2-1B model card](https://huggingface.co/lightonai/LightOnOCR-2-1B), [Qwen3.5-2B model card](https://huggingface.co/Qwen/Qwen3.5-2B), [TrOCR model card](https://huggingface.co/microsoft/trocr-base-handwritten).
