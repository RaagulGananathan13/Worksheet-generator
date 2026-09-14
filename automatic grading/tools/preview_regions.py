"""Render annotated preset previews for human acceptance of answer regions."""
import sys
from pathlib import Path
import pypdfium2 as pdfium
from PIL import ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.samples import load_sample, HASHES


def main():
    output = ROOT / "artifacts" / "region-previews"
    output.mkdir(parents=True, exist_ok=True)
    for filename in HASHES:
        content, preset = load_sample(filename)
        with pdfium.PdfDocument(content) as document:
            for page_index,page in enumerate(document):
                bitmap=page.render(scale=1.6)
                try:
                    preview=bitmap.to_pil().convert("RGB")
                finally:
                    bitmap.close()
                draw=ImageDraw.Draw(preview,"RGBA")
                width,height=preview.size
                for index,question in enumerate(preset["questions"]):
                    if question["page"] != page_index:
                        continue
                    r=question["rect"]
                    area=(r["x"]*width,r["y"]*height,(r["x"]+r["w"])*width,(r["y"]+r["h"])*height)
                    draw.rectangle(area,outline=(230,63,12,255),fill=(255,200,50,35),width=2)
                    label=f"{index+1}: " + (question["expected"][0] if question["expected"] else "REVIEW")
                    draw.text((area[0],max(0,area[1]-13)),label,fill=(200,30,12,255))
                preview.save(output / f"{Path(filename).stem}-{page_index+1}.png")
                page.close()
    print(output)


if __name__ == "__main__":
    main()
