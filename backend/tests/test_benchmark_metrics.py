import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from benchmark_metrics import retrieval_metrics,citation_metrics,fact_coverage,extraction_metrics,table_accuracy,paired_interval

class BenchmarkMetricTests(unittest.TestCase):
    def test_ranking_penalizes_wrong_passage_and_duplicates(self):
        gold=[{'file':'a.pdf','page':1,'contains':['approval code'],'grade':3},{'file':'b.pdf','page':2,'grade':1}]
        rows=[{'file':'a.pdf','page':1,'content':'unrelated passage'},
              {'file':'a.pdf','page':1,'content':'approval code ABC'},
              {'file':'a.pdf','page':1,'content':'approval code ABC'}]
        score=retrieval_metrics(rows,gold,5)
        self.assertEqual(score['recall'],.5);self.assertEqual(score['precision'],.2);self.assertEqual(score['mrr'],.5)
        self.assertGreater(score['ndcg'],0);self.assertLess(score['ndcg'],1)
        self.assertIsNone(retrieval_metrics(rows,[],5))

    def test_perfect_ranking_and_stale_versions(self):
        gold=[{'file':'a','page':1,'grade':3,'version_id':'new'},{'file':'b','page':2,'grade':1}]
        rows=[{'file':'a','page':1,'version_id':'new'},{'file':'b','page':2}]
        self.assertEqual(retrieval_metrics(rows,gold,2)['ndcg'],1)
        rows[0]['version_id']='old';self.assertEqual(retrieval_metrics(rows,gold,2)['recall'],.5)

    def test_citations_are_not_called_faithfulness(self):
        context=[{'file':'a.pdf','page':1,'content':'code ABC'}];gold=[{'file':'a.pdf','page':1,'contains':['ABC']}]
        result=citation_metrics('Wrong fact [a.pdf, p. 1] [invented.pdf, p. 9]',context,gold)
        self.assertEqual(result['reference_validity'],.5);self.assertEqual(result['gold_evidence_coverage'],1)
        self.assertNotIn('faithfulness',result)
        self.assertEqual(fact_coverage('Code ABC',[{'alternatives':['ABC','XYZ']}]),1)

    def test_ocr_and_table_errors(self):
        self.assertEqual(extraction_metrics('cat','cat')['cer'],0)
        self.assertAlmostEqual(extraction_metrics('cut','cat')['cer'],1/3)
        self.assertEqual(extraction_metrics('one two','one three')['wer'],.5)
        self.assertEqual(table_accuracy([[['A','1'],['B','9']]],[['A','1'],['B','2']]),.75)

    def test_paired_bootstrap_identity(self):
        values={'a':(1.,'family'),'b':(0.,'family')}
        result=paired_interval(values,values,iterations=100)
        self.assertEqual(result['delta'],0);self.assertEqual(result['ci95'],[0,0])

if __name__=='__main__':unittest.main()
