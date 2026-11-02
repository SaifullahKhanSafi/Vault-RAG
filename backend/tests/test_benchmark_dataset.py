import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from benchmark_fixtures import build
from benchmark import validate
from benchmark_metrics import normalized
from pypdf import PdfReader

class BenchmarkDatasetTests(unittest.TestCase):
    def test_pilot_labels_match_native_pdf_pages(self):
        with tempfile.TemporaryDirectory() as directory:
            data,files=build(directory);validate(data)
            self.assertEqual(len(data['cases']),40);self.assertEqual(len(files),10)
            self.assertIn('not_human_reviewed',data['review_status'])
            for case in data['cases']:
                for source in case['expected_sources']:
                    reader=PdfReader(Path(directory)/source['file'])
                    self.assertLessEqual(source['page'],len(reader.pages))
                    if source['file']!='raven-scan.pdf':
                        text=normalized(reader.pages[source['page']-1].extract_text())
                        for phrase in source.get('contains',[]):self.assertIn(normalized(phrase),text)

    def test_invalid_ground_truth_does_not_silently_score(self):
        with self.assertRaises(ValueError):validate({'schema_version':1,'cases':[{'id':'a','question':'Question'}]})
        with self.assertRaises(ValueError):validate({'schema_version':1,'cases':[{'id':'a','question':'Question','abstain':True},{'id':'a','question':'Other','abstain':True}]})

if __name__=='__main__':unittest.main()
