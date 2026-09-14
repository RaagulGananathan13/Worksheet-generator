"""Draft answer regions bound to the exact six supplied worksheet PDFs.

These are derived presets, NOT teacher-approved rubrics. Publication requires
the teacher's explicit confirmation in the editor. Coordinates were inspected
against the rendered originals; no questions are inferred at runtime.
"""
import copy
import hashlib
import os
from pathlib import Path

SOURCE = Path(os.getenv("AG_SAMPLES_DIR", str(Path(__file__).resolve().parents[2] / "sample-worksheets")))
HASHES = {
    "19963892.pdf": "6f8bed06bff71a4c792009e8c10a94197d2699c8828118062619f957e8d512f3",
    "35879581.pdf": "34143e206e8b24d88120f0b82f7a3a7e1d02c111c4b1ec564cbd4fef7ef1a667",
    "36635880.pdf": "601ee8ca4f4e3f4b61d30715a9e5dcf3be177346ea87f616466b86d8e18e206b",
    "48544102.pdf": "532df7e2a487f1325c7c027a31c0d2ff769791103fdb35f22d42566310382025",
    "91903282.pdf": "4e1b2dcd7164d8c0742c54daeb15a75aa3624c586b47683c8fe609c920277e5f",
    "96056280.pdf": "9e30d6bd57b88a0ce472421f782433b129192fa16d0d718344125f75fcd87e3e",
}


def rect(x, y, w, h, height=1268):
    return {"x": x / 980, "y": y / height, "w": w / 980, "h": h / height}


def question(identifier, label, area, expected=None, kind="number", options=None):
    return {"id": identifier, "label": label, "page": 0, "rect": area,
            "kind": kind, "expected": [] if expected is None else [str(expected)],
            "points": 1.0, "tolerance": 0.0, "case_sensitive": False,
            "options": options or []}


def _presets():
    presets = {}
    common = "Draft answers derived from the supplied PDF. Check every region, answer and mark, then confirm keys before publishing. "
    qs = [question(f"word-{i+1}", label, rect(106, y, 350, 68), answer)
          for i, (label, y, answer) in enumerate([
              ("Stickers: number of students (final answer)", 337, 384),
              ("Apples: number of baskets (final answer)", 501, 121),
              ("Cookies: number of boxes (final answer)", 666, 300)])]
    for i, (dividend, divisor) in enumerate([(826,2),(867,3),(840,4),(890,5),(906,6),(861,7),(864,8),(891,9)]):
        qs.append(question(f"divide-{i+1}", f"Division {i+1}: {dividend} ÷ {divisor} quotient", rect([115,338,561,784][i//2], [835,1037][i%2], 76, 34), dividend//divisor))
    presets["19963892.pdf"] = {"title": "Basic division III", "questions": qs,
        "notes": common + "11 final numeric answers, 1 mark each. This rubric does not award method/workings marks. Add manual fields if those are required."}

    subtrahends = [12,90,37,58,26,69,47,78,39,84,48,27,65,54,87,34,76,59,86,43]
    qs = [question(f"subtract-{i+1}", f"92 − {n}", rect([115,338,562,798][i//5], [376,569,762,955,1148][i%5], 104, 62), 92-n) for i,n in enumerate(subtrahends)]
    presets["35879581.pdf"] = {"title": "Subtract from 92", "questions": qs, "notes": common + "20 exact numeric answers, 1 mark each."}

    qs = []
    for i, n in enumerate(range(21,26)):
        x = [81,251,421,591,761][i]
        qs.append(question(f"cabbage-{n}", f"Write {n} inside the cabbage", rect(x,500,108,67), n))
        qs.append(question(f"trace-{n}", f"Trace {n}: teacher checks shape and stroke placement", rect(x-12,843,128,126), kind="manual"))
        qs.append(question(f"write-{n}", f"Write {n} in the bottom box", rect(x,1070,109,79), n))
    presets["36635880.pdf"] = {"title": "Write and trace 21–25", "questions": qs,
        "notes": common + "10 numeric writing answers and 5 tracing tasks, 1 mark each. Tracing quality requires teacher review; the printed pale digits are never OCR evidence."}

    operands = [1,5,9,3,11,6,2,8,4,12,7,10,5,12,3,9]
    qs = [question(f"add-{i+1}", f"2 + {n}", rect([372,853][i//8], 278+120*(i%8), 82, 63,1266), n+2) for i,n in enumerate(operands)]
    presets["48544102.pdf"] = {"title": "Add 2", "questions": qs, "notes": common + "16 exact numeric answers. Source page is 612 × 791.04 points, slightly shorter than US Letter; its original size is preserved."}

    qs = []
    for i,(name,count) in enumerate([("ants",7),("apples",5),("balls",9),("bamboo plants",4)]):
        y = 287 + 122*i
        opts = [{"value":str(n),"label":str(n),"rect":rect(61+82*(n-1),y,44,44)} for n in range(1,11)]
        qs.append(question(f"count-{i+1}", f"Count the {name}; select one number", rect(57,y,790,44), count,"choice",opts))
    for i,(row,col,n) in enumerate([(0,1,2),(0,4,5),(1,2,8),(2,0,11),(2,3,14),(3,1,17)]):
        qs.append(question(f"flower-{i+1}", f"Flower grid: row {row+1}, column {col+1}", rect([241,346,451,556,662][col]-26,[834,930,1026,1122][row]-25,52,50), n))
    presets["91903282.pdf"] = {"title": "Count and complete numbers", "questions": qs,
        "notes": common + "Four count-and-select questions and six missing numbers. Tap or pencil-select an option; circling the printed numbers with OCR is unnecessary."}

    qs = []
    for row, numbers in enumerate([[28,30,32],[37,39,41]]):
        for col,n in enumerate(numbers):
            qs.append(question(f"chain-{row}-{col}",f"Number chain {row+1}: missing value {col+1}",rect([173,419,663][col],[350,542][row],93,87),n))
    for row,numbers in enumerate([[31,33],[40,42]]):
        for col,n in enumerate(numbers):
            qs.append(question(f"frog-{row}-{col}",f"Frog sequence {row+1}: missing value {col+1}",rect([273,625][col],[831,1076][row],85,66),n))
    presets["96056280.pdf"] = {"title":"Complete the number sequences", "questions":qs, "notes":common + "10 missing numeric values, 1 mark each."}
    return presets


PRESETS = _presets()


def list_samples():
    return [{"filename":name,"title":p["title"],"question_count":len(p["questions"]),"notes":p["notes"]}
            for name,p in PRESETS.items() if (SOURCE/name).is_file()]


def preset_for_content(content):
    digest = hashlib.sha256(content).hexdigest()
    for name, known in HASHES.items():
        if digest == known:
            return copy.deepcopy(PRESETS[name])
    return None


def load_sample(filename):
    if filename not in HASHES:
        raise ValueError("Unknown sample worksheet.")
    path = SOURCE / filename
    if not path.is_file():
        raise ValueError("Sample PDF is not installed. Upload it instead.")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != HASHES[filename]:
        raise ValueError("The sample PDF has changed; upload it and configure fresh answer regions.")
    return content, copy.deepcopy(PRESETS[filename])
