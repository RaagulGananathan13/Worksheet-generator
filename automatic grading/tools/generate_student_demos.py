"""Create labelled synthetic pen-stroke demos; never alter the six originals.

PDFs are visual test references, not uploaded submissions. Matching JSON files
preserve the digital ink that the replay helper saves through student APIs.
These constructed strokes are not real pupils' handwriting or an OCR benchmark.
"""
from io import BytesIO
from pathlib import Path
import argparse
import hashlib
import json
import math
import random
import sys

from reportlab.pdfgen.canvas import Canvas

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import documents
from app.documents_permissive import _draw_answer
from app.samples import HASHES, load_sample
from app.schemas import AnswersUpdate

OUTPUT = ROOT.parent / "sample-worksheets" / "student-written-demos"
FORMAT = "geniusbees-synthetic-ink-v1"

# Hand-specified pen paths, not a handwriting font and not human-collected data.
# Each glyph can have several strokes, all in its own local 0..1 coordinate box.
GLYPHS = {
    "0": [[(.52,.06),(.24,.08),(.10,.30),(.10,.67),(.26,.91),(.59,.94),(.81,.75),(.87,.39),(.75,.13),(.52,.06)]],
    "1": [[(.24,.25),(.49,.07),(.48,.94)]],
    "2": [[(.10,.22),(.25,.07),(.57,.06),(.79,.19),(.81,.36),(.63,.55),(.36,.72),(.09,.93),(.84,.93)]],
    "3": [[(.10,.14),(.32,.05),(.62,.09),(.78,.22),(.70,.39),(.43,.48),(.66,.51),(.80,.66),(.73,.85),(.51,.95),(.22,.92),(.08,.81)]],
    "4": [[(.58,.05),(.11,.62),(.85,.62)],[(.69,.08),(.65,.95)]],
    "5": [[(.80,.08),(.20,.08),(.16,.47),(.50,.43),(.75,.54),(.82,.72),(.66,.91),(.35,.95),(.11,.82)]],
    "6": [[(.75,.08),(.49,.05),(.22,.25),(.09,.60),(.16,.84),(.41,.95),(.69,.87),(.83,.67),(.73,.48),(.50,.43),(.20,.57)]],
    "7": [[(.10,.09),(.87,.09),(.60,.47),(.34,.95)]],
    "8": [[(.48,.05),(.21,.10),(.11,.27),(.28,.44),(.63,.57),(.81,.76),(.66,.93),(.36,.96),(.13,.83),(.15,.65),(.42,.48),(.76,.27),(.74,.12),(.48,.05)]],
    "9": [[(.75,.39),(.67,.12),(.42,.05),(.18,.17),(.10,.37),(.22,.54),(.47,.56),(.74,.39)],[(.75,.14),(.75,.51),(.55,.95)]],
    "-": [[(.12,.50),(.85,.50)]],
}


def number_ink(value, rectangle, page, seed):
    rng = random.Random(seed)
    text = str(value)
    region_width = rectangle["w"] * page["width"]
    region_height = rectangle["h"] * page["height"]
    units = len(text) * .60 + max(0,len(text)-1) * .16
    height = min(region_height * .76, region_width * .78 / units)
    total_width = height * units
    left, top = (region_width-total_width)/2, (region_height-height)/2
    strokes=[]
    for digit_index, digit in enumerate(text):
        lean = rng.uniform(-.03,.06)
        lift = rng.uniform(-.015,.015) * height
        for polyline in GLYPHS[digit]:
            points=[]
            for segment in range(len(polyline)-1):
                start,end=polyline[segment],polyline[segment+1]
                for step in range(5):
                    t=step/5
                    x=start[0]+(end[0]-start[0])*t
                    y=start[1]+(end[1]-start[1])*t
                    x += lean*(1-y) + rng.uniform(-.004,.004)
                    y += rng.uniform(-.003,.003)
                    points.append({
                        "x":round((left+height*(digit_index*.76+x*.60))/region_width,6),
                        "y":round((top+lift+height*y)/region_height,6),
                        "p":round(.52+.10*math.sin(len(points)/7)+rng.uniform(-.025,.025),4),
                    })
            x,y=polyline[-1]
            points.append({"x":round((left+height*(digit_index*.76+(x+lean*(1-y))*.60))/region_width,6),
                           "y":round((top+lift+height*y)/region_height,6),"p":.5})
            strokes.append({"width":round(max(.001,min(.03,1.05/region_width)),6),"points":points})
    return strokes


def make_fixture(filename, scenario, pages):
    _,preset=load_sample(filename)
    answers,observations={},[]
    automated=[q["id"] for q in preset["questions"] if q["kind"]!="manual"]
    wrong_id,blank_id=automated[:2] if scenario=="mixed" else (None,None)
    for index,question in enumerate(preset["questions"]):
        qid=question["id"]
        intended=question["expected"][0] if question["expected"] else qid.rsplit("-",1)[-1]
        outcome="manual" if question["kind"]=="manual" else "correct"
        if qid==wrong_id:
            intended=next((option["value"] for option in question["options"] if option["value"] not in question["expected"]),None) if question["kind"]=="choice" else str(int(intended)+1)
            outcome="deliberately wrong"
        if qid==blank_id:
            intended=""
            outcome="blank"
            answers[qid]={"text":"","strokes":[]}
        elif question["kind"]=="choice":
            answers[qid]={"text":intended,"strokes":[]}
        else:
            answers[qid]={"text":"","strokes":number_ink(intended,question["rect"],pages[question["page"]],f"{filename}:{scenario}:{index}")}
        observations.append({"question_id":qid,"label":question["label"],"intended_written_value":intended,"intended_case":outcome})
    AnswersUpdate(version=1,answers=answers)
    public=[{key:value for key,value in q.items() if key not in {"expected","tolerance","case_sensitive"}} for q in preset["questions"]]
    return {
        "format":FORMAT,"synthetic":True,"source_filename":filename,"source_sha256":HASHES[filename],
        "scenario":scenario,"questions":public,"answers":answers,
    },observations


def demo_pdf(fixture, metadata, cache):
    output=BytesIO()
    canvas=Canvas(output,pageCompression=1,invariant=1)
    canvas.setTitle(f"SYNTHETIC TEST - {fixture['source_filename']} - {fixture['scenario']}")
    canvas.setAuthor("GeniusBees test fixture generator - not a real student")
    canvas.setSubject("Constructed pen strokes for visual review. Upload the original blank PDF to the portal; replay matching JSON to test saved ink.")
    for index,page in enumerate(metadata["pages"]):
        width,height=page["width"],page["height"]
        canvas.setPageSize((width,height))
        canvas.drawImage(str(cache/f"{metadata['sha256']}-{index}.png"),0,0,width=width,height=height)
        for question in fixture["questions"]:
            if question["page"]==index:
                _draw_answer(canvas,question,fixture["answers"][question["id"]],None,width,height)
        canvas.setFillColorRGB(.72,.13,.13)
        canvas.setFont("Helvetica-Bold",6.5)
        canvas.drawString(14,height-10,f"SYNTHETIC TEST COPY | {fixture['scenario'].upper()} | constructed pen strokes, not real student handwriting")
        canvas.showPage()
    canvas.save()
    return output.getvalue()


def generate(output=OUTPUT):
    output=Path(output).resolve()
    # The default explicitly requested folder or a contained developer test folder.
    if output!=OUTPUT.resolve() and not output.is_relative_to(ROOT/"artifacts"):
        raise ValueError("Demo output must be student-written-demos or inside automatic grading/artifacts.")
    cache=ROOT/"artifacts"/"student-demo-source-cache"
    planned=[output/f"{Path(filename).stem}-{scenario}.synthetic{ext}"
             for filename in HASHES for scenario in ("correct","mixed") for ext in (".pdf",".json")]
    planned.append(output/"manifest.json")
    if any(path.exists() for path in planned):
        raise FileExistsError("Demo files already exist. Nothing was overwritten; use the existing set or a new --output directory under artifacts.")
    output.mkdir(parents=True,exist_ok=True)
    records=[]
    for filename in HASHES:
        content,preset=load_sample(filename)
        original_hash=hashlib.sha256(content).hexdigest()
        metadata=documents.import_pdf(content,cache)
        for scenario in ("correct","mixed"):
            fixture,observations=make_fixture(filename,scenario,metadata["pages"])
            prefix=f"{Path(filename).stem}-{scenario}.synthetic"
            pdf=demo_pdf(fixture,metadata,cache)
            (output/f"{prefix}.pdf").write_bytes(pdf)
            (output/f"{prefix}.json").write_text(json.dumps(fixture,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
            auto=sum(q["kind"]!="manual" for q in fixture["questions"])
            manual=len(fixture["questions"])-auto
            records.append({"pdf":f"{prefix}.pdf","fixture":f"{prefix}.json","source_filename":filename,"source_sha256":original_hash,
                            "scenario":scenario,"title":preset["title"],"question_count":len(fixture["questions"]),
                            "manual_questions":manual,"intended_correct_numeric_or_choice":auto-(2 if scenario=="mixed" else 0),
                            "pdf_sha256":hashlib.sha256(pdf).hexdigest(),"responses":observations})
        if hashlib.sha256(load_sample(filename)[0]).hexdigest()!=original_hash:
            raise RuntimeError("Original PDF changed during generation.")
    manifest={"format":"geniusbees-synthetic-demo-manifest-v1","synthetic":True,
              "warning":"Visual fixtures only, not student-collected handwriting or accuracy evidence. Intended correct values are not guaranteed automatic OCR marks. Trace quality always needs review.",
              "files":records}
    (output/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=OUTPUT)
    args=parser.parse_args()
    try:
        manifest=generate(args.output)
    except (ValueError,FileExistsError) as error:
        parser.exit(1,str(error)+"\n")
    print(f"Created {len(manifest['files'])} labelled PDFs and matching digital-ink JSON files in {args.output}")
    print("Original PDFs unchanged. Use originals for teacher imports; use paired JSON with replay_demo_submission.py.")


if __name__=="__main__":
    main()
