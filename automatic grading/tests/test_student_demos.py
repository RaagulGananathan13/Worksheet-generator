"""Verify the shipped visual demos and their paired digital-ink fixtures."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.samples import HASHES, PRESETS, load_sample, preset_for_content
from app.schemas import AnswersUpdate
from tools.generate_student_demos import OUTPUT, generate


class StudentDemoTests(unittest.TestCase):
    def test_all_twelve_pdfs_and_stroke_fixtures_are_labelled_and_valid(self):
        manifest=json.loads((OUTPUT/'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(len(manifest['files']),12)
        for item in manifest['files']:
            with self.subTest(file=item['pdf']):
                source=load_sample(item['source_filename'])[0]
                self.assertEqual(hashlib.sha256(source).hexdigest(),item['source_sha256'])
                content=(OUTPUT/item['pdf']).read_bytes()
                self.assertEqual(hashlib.sha256(content).hexdigest(),item['pdf_sha256'])
                self.assertIsNone(preset_for_content(content),'Completed visual copy must not get a blank-template preset')
                pdf=PdfReader(OUTPUT/item['pdf'])
                self.assertEqual(len(pdf.pages),1)
                self.assertIn('SYNTHETIC TEST COPY',pdf.pages[0].extract_text())
                fixture=json.loads((OUTPUT/item['fixture']).read_text(encoding='utf-8'))
                self.assertTrue(fixture['synthetic'])
                AnswersUpdate(version=1,answers=fixture['answers'])
                ids={q['id'] for q in PRESETS[item['source_filename']]['questions']}
                self.assertEqual(set(fixture['answers']),ids)
                self.assertEqual({q['id'] for q in fixture['questions']},ids)
                self.assertTrue(all('expected' not in q for q in fixture['questions']))
                self.assertTrue(any(a['strokes'] for a in fixture['answers'].values()))

    def test_mixed_scenarios_have_exactly_one_deliberate_error_and_one_blank(self):
        manifest=json.loads((OUTPUT/'manifest.json').read_text(encoding='utf-8'))
        for item in manifest['files']:
            counts={case:sum(r['intended_case']==case for r in item['responses']) for case in ['deliberately wrong','blank']}
            expected=1 if item['scenario']=='mixed' else 0
            self.assertEqual(counts,{'deliberately wrong':expected,'blank':expected})

    def test_generation_refuses_to_overwrite_existing_demos(self):
        before=hashlib.sha256((OUTPUT/'manifest.json').read_bytes()).hexdigest()
        with self.assertRaises(FileExistsError):generate()
        self.assertEqual(before,hashlib.sha256((OUTPUT/'manifest.json').read_bytes()).hexdigest())


if __name__=='__main__':
    unittest.main()
