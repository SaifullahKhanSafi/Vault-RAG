import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from benchmark_judge import judge_case
from benchmark_review import agreement,label

class BenchmarkJudgeTests(unittest.TestCase):
    def judge(self,result):
        import json
        response=MagicMock();response.json.return_value={'message':{'content':json.dumps(result)}}
        with patch('benchmark_judge.httpx.Client') as client:
            client.return_value.__enter__.return_value.post.return_value=response
            score=judge_case({'answer':'A B','diagnostics':{'final_context':[]}},
              {'question':'Q','facts':[{'alternatives':['A']},{'alternatives':['B']}]},'local','http://localhost')
            schema=client.return_value.__enter__.return_value.post.call_args.kwargs['json']['format']
            self.assertEqual(schema['properties']['reference_coverage']['minItems'],2)
            self.assertEqual(schema['properties']['reference_coverage']['maxItems'],2)
            return score

    def test_claim_scores_count_unsupported_claims(self):
        result=self.judge({'claims':[
          {'text':'A','supported':True,'correct':True,'has_citation':True,'citation_supported':True},
          {'text':'B','supported':False,'correct':False,'has_citation':True,'citation_supported':False}],
          'reference_coverage':[True,False]})
        for key in ('faithfulness','correctness_precision','correctness_recall','correctness_f1','citation_precision','citation_completeness'):
            self.assertEqual(result[key],.5)
        self.assertFalse(result['calibrated'])

    def test_invalid_judgments_are_rejected_and_empty_claims_are_unscored(self):
        with self.assertRaises(ValueError):self.judge({'claims':[],'reference_coverage':[True]})
        with self.assertRaises(ValueError):self.judge({'claims':[],'reference_coverage':['true',False]})
        self.assertIsNone(self.judge({'claims':[],'reference_coverage':[False,False]})['faithfulness'])

    def test_human_calibration_uses_warning_class_and_excludes_missing_labels(self):
        self.assertIsNone(label('unknown'));self.assertIsNone(label(''))
        self.assertEqual(agreement([]),{'n':0})
        result=agreement([(False,False),(False,True),(True,False),(True,True)])
        self.assertEqual(result['warning_precision'],.5);self.assertEqual(result['warning_recall'],.5)
        self.assertEqual(result['cohen_kappa'],0)

if __name__=='__main__':unittest.main()
