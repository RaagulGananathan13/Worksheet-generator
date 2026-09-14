# Supplied worksheet analysis and draft marking keys

These keys were derived by inspecting the actual rendered PDFs, not from filenames or the intern's templates. They require teacher confirmation. Coordinates and SHA-256 fingerprints are in `app/samples.py`; run `tools/preview_regions.py` to see every region superimposed on a copy. None of these operations writes to the original PDF.

| Original file | Layout and marking policy | Fields / maximum marks |
| --- | --- | --- |
| 19963892.pdf | Three division word problems and eight long divisions; final numeric answer only | 11 / 11 |
| 35879581.pdf | Four columns of five two-digit subtractions | 20 / 20 |
| 36635880.pdf | Write 21–25 twice; trace five pale exemplars | 15 / 15, including 5 reviewed tracing marks |
| 48544102.pdf | Two columns of eight additions, each adding 2 | 16 / 16 |
| 91903282.pdf | Four count-and-select rows; six missing flower numbers | 10 / 10 |
| 96056280.pdf | Six chain gaps; four frog sequence gaps | 10 / 10 |

All six PDFs have one page. Five measure exactly 612 × 792 points (8.5 × 11 inch US Letter). `48544102.pdf` measures 612 × approximately 791.04 points: preserve this supplied page geometry, rather than shifting its answer regions to a guessed size. `19963892.pdf` is image-only in text extraction; text parsing alone cannot reconstruct its problems.

## 19963892 — division

Word problems: 768 stickers / 2 per student = **384 students**; 847 apples / 7 per basket = **121 baskets**; 900 cookies / 3 per box = **300 boxes**. Students enter the final number in the answer area.

The numbered long divisions run down columns, not across rows:

| Printed number | Calculation | Answer |
| --- | --- | --- |
| 1 | 826 / 2 | 413 |
| 2 | 867 / 3 | 289 |
| 3 | 840 / 4 | 210 |
| 4 | 890 / 5 | 178 |
| 5 | 906 / 6 | 151 |
| 6 | 861 / 7 | 123 |
| 7 | 864 / 8 | 108 |
| 8 | 891 / 9 | 99 |

Only the quotient region above each division bar is scored. This is not automatic assessment of long-division method. The teacher can add a manual workings region if the assessment requires method marks.

## 35879581 — subtraction

Printed question order 1–20, down each column: subtract `12, 90, 37, 58, 26, 69, 47, 78, 39, 84, 48, 27, 65, 54, 87, 34, 76, 59, 86, 43` from 92.

Answers: `80, 2, 55, 34, 66, 23, 45, 14, 53, 8, 44, 65, 27, 38, 5, 58, 16, 33, 6, 49`.

## 36635880 — writing and tracing

Each of the five columns models a number from 21 through 25. The second cabbage row and bottom rectangular row receive numeric answer regions below the small printed cues. The large solid digits are examples, not answer regions. The pale digits are manual tracing regions.

Recognizing the printed pale `21` says nothing about whether a child traced it correctly. Only newly captured ink is preserved as the student's response, and a teacher assesses tracing shape/placement. The tracing region remains over the original pattern.

## 48544102 — addition

Question order 1–16 runs down the first column, then the second. The non-2 operands are `1, 5, 9, 3, 11, 6, 2, 8, 4, 12, 7, 10, 5, 12, 3, 9`.

Answers: `3, 7, 11, 5, 13, 8, 4, 10, 6, 14, 9, 12, 7, 14, 5, 11`.

## 91903282 — counting and missing numbers

Object counts: **7 ants, 5 apples, 9 balls, 4 bamboo plants**. Options 1–10 are page-relative tap regions. Selection is marked deterministically and does not use OCR.

Flower gaps: row 1 column 2 = 2; row 1 column 5 = 5; row 2 column 3 = 8; row 3 column 1 = 11; row 3 column 4 = 14; row 4 column 2 = 17.

## 96056280 — number sequences

First chain: **28, 30, 32**. Second chain: **37, 39, 41**. Top frog row: **31, 33**. Bottom frog row: **40, 42**.

## New worksheet types

The generator exports presentation, not a semantic question schema. Therefore no safe universal answer key can be inferred for every uploaded worksheet. New PDFs require teacher-defined fields and accepted answers. A numeric answer can accept equivalent decimals or fractions; text uses exact normalized accepted variants; choices use explicit values; subjective work uses manual points. Multi-line handwriting, Sinhala handwriting, arbitrary equations, geometry and essays are not reliably handled by the local handwriting models (GLM-OCR and PaddleOCR-VL); use manual marking for them.
