"""Compare frozen case sets; optional release gate for statistically supported pass-rate regressions."""
import argparse,json,statistics
from pathlib import Path
from benchmark_metrics import paired_interval

def case_key(report):
    return report.get('case_set_sha256') or report.get('dataset_sha256')

def compare(baseline,current):
    if case_key(baseline)!=case_key(current):raise ValueError('Case sets differ. Compare the same frozen questions/annotations, and verify corpus snapshots separately.')
    result={}
    for config,rows in current['results'].items():
        if config not in baseline['results']:continue
        def group(items):
            groups={}
            for row in items:groups.setdefault(row['case_id'],[]).append(row)
            return {key:(statistics.mean(float(r['passed']) for r in values),values[0]['family']) for key,values in groups.items()}
        result[config]=paired_interval(group(baseline['results'][config]),group(rows))
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--baseline',required=True);p.add_argument('--current',required=True);p.add_argument('--fail-on-regression',action='store_true');args=p.parse_args()
    def load(path):
        import hashlib
        report=json.loads(Path(path).read_text(encoding='utf-8'))
        dataset=Path(path).parent/'dataset.json'
        if not report.get('case_set_sha256') and dataset.exists():
            logical=json.loads(dataset.read_text(encoding='utf-8'))
            for case in logical['cases']:
                for source in case.get('expected_sources',[]):source.pop('version_id',None)
            report['case_set_sha256']=hashlib.sha256(json.dumps(logical,sort_keys=True).encode()).hexdigest()
        return report
    baseline=load(args.baseline);current=load(args.current)
    result=compare(baseline,current);print(json.dumps(result,indent=2))
    security_failed=current.get('security_regression_suite',{}).get('passed') is False
    api_failed=any(not r['ok'] for rows in current['results'].values() for r in rows)
    invalid_citations=any(r.get('citations',{}).get('invalid_references') for rows in current['results'].values() for r in rows)
    observed_regression=any(score and score['ci95'][1]<0 for score in result.values())
    if args.fail_on_regression and (security_failed or api_failed or invalid_citations or observed_regression):raise SystemExit(1)

if __name__=='__main__':main()
