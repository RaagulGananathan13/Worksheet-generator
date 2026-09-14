"""Render local PDF samples for development inspection; never changes originals."""
from pathlib import Path
import json
import pypdfium2 as pdfium

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / "sample-worksheets"

def main():
    output = ROOT / "artifacts" / "sample-previews"
    output.mkdir(parents=True, exist_ok=True)
    report = []
    for path in sorted(SOURCE.glob("*.pdf")):
        with pdfium.PdfDocument(path) as document:
            pages = []
            for index, page in enumerate(document):
                bitmap = page.render(scale=1.6)
                try:
                    bitmap.to_pil().save(output / f"{path.stem}-{index + 1}.png")
                finally:
                    bitmap.close()
                textpage = page.get_textpage()
                try:
                    text = textpage.get_text_range()
                finally:
                    textpage.close()
                width, height = page.get_size()
                pages.append({"width": width, "height": height, "text": text})
                page.close()
            report.append({"filename": path.name, "pages": pages})
    (output / "inventory.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(output)

if __name__ == "__main__":
    main()
