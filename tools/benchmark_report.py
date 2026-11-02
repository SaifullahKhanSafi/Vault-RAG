"""Standalone private HTML/CSV reports; all source content is escaped, no external assets."""
import csv
from html import escape
import json

def safe_cell(value):
    return "'"+value if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')) else value

def write_report(report,out):
    columns=['configuration','cases','completed','strict_fixture_pass_rate','candidate_recall_at_5','candidate_recall_at_10',
             'final_recall','final_precision','final_ndcg','final_mrr','fact_coverage','correct_abstention_rate','gold_citation_coverage',
             'ttft_p50_seconds','ttft_p95_seconds','warm_p50_seconds','warm_p95_seconds','error_rate']
    summaries=[]
    for name,score in report['summary'].items():
        item={'configuration':name,**score,'ttft_p50_seconds':score['ttft_seconds']['median'],'ttft_p95_seconds':score['ttft_seconds']['p95'],
              'warm_p50_seconds':score['latency_warm_observed_seconds']['median'],'warm_p95_seconds':score['latency_warm_observed_seconds']['p95']}
        summaries.append(item)
    with (out/'summary.csv').open('w',newline='',encoding='utf-8') as file:
        writer=csv.DictWriter(file,fieldnames=columns,extrasaction='ignore');writer.writeheader();writer.writerows(summaries)
    with (out/'cases.csv').open('w',newline='',encoding='utf-8') as file:
        fields=['configuration','case_id','category','repeat','passed','ok','seconds','ttft_seconds','fact_coverage','failures','answer']
        writer=csv.DictWriter(file,fieldnames=fields,extrasaction='ignore');writer.writeheader()
        for name,rows in report['results'].items():
            for row in rows:writer.writerow({k:safe_cell(v) for k,v in {'configuration':name,**row,'failures':'; '.join(row['failures'])}.items()})
    def number(value):return '—' if value is None else str(value) if type(value) is int else f'{value:.3f}' if isinstance(value,float) else escape(str(value))
    display={'configuration':'Configuration','cases':'Cases','strict_fixture_pass_rate':'Strict pass',
      'final_recall':f"Recall@{report['top_k']}",'final_ndcg':f"nDCG@{report['top_k']}",
      'fact_coverage':'Fact coverage','gold_citation_coverage':'Evidence cited',
      'warm_p50_seconds':'Warm median (s)','warm_p95_seconds':'Warm p95 (s)','error_rate':'Request errors'}
    table='<tr>'+''.join('<th>'+escape(label)+'</th>' for label in display.values())+'</tr>'
    table+=''.join('<tr>'+''.join('<td>'+number(row.get(c))+'</td>' for c in display)+'</tr>' for row in summaries)
    cases=[]
    for name,rows in report['results'].items():
        for row in rows:
            title=f"{name} · {row['case_id']} · {'PASS' if row['passed'] else ', '.join(row['failures'])}"
            record={'answer':row.get('answer'),'metrics':row.get('final_metrics'),'citations':row.get('citations'),
                    'diagnostics':row.get('diagnostics'),'advisory_judge':row.get('judge'),'error':row.get('error')}
            cases.append('<details><summary>'+escape(title)+'</summary><pre>'+escape(json.dumps(record,indent=2,ensure_ascii=False))+'</pre></details>')
    categories=escape(json.dumps(report.get('categories',{}),indent=2));comparisons=escape(json.dumps(report.get('paired_comparisons_to_hybrid',{}),indent=2))
    document='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>RAG benchmark report</title><style>body{font:15px/1.6 system-ui;margin:32px;color:#172033;background:#f8fafc}h1{margin-bottom:4px}section,details{background:white;padding:20px;border:1px solid #dbe2ed;border-radius:12px;margin:16px 0}table{border-collapse:collapse;white-space:nowrap}td,th{padding:10px;border-bottom:1px solid #e2e8f0;text-align:left}th{background:#eef2ff}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}summary{cursor:pointer;font-weight:600}.scroll{overflow:auto}.notice{border-left:4px solid #4f46e5;padding-left:16px}a{color:#4338ca}</style>
    <h1>RAG benchmark</h1><p>RUN_ID</p><p class="notice">DATASET · REVIEW_STATUS<br>Fixture pass rates and substring checks are not validated business accuracy. Citation validity is not claim support. Local model judgments are advisory and uncalibrated.</p>
    <section><h2>Configuration comparison</h2><div class="scroll"><table>TABLE</table></div><p>Rates are fractions from 0 to 1. Final context cutoff: TOP_K. The CSV includes candidate Recall@5/@10, precision, MRR and first-token timing. Errors are retained as failed quality cases; latency summaries contain completed requests only. Warm state means the model was observed loaded; it does not guarantee an identical cached context.</p><a href="report.json">Full JSON</a> · <a href="summary.csv">Summary CSV</a> · <a href="cases.csv">Case CSV</a> · <a href="dataset.json">Frozen dataset</a></section>
    <section><h2>Extraction</h2><pre>EXTRACTION</pre><h2>Security regression suite</h2><pre>SECURITY</pre></section>
    <section><h2>Advisory model judge</h2><pre>JUDGE</pre><p>Only explicitly selected cases are judged. These scores remain uncalibrated until humans review the claims.</p></section>
    <section><h2>Paired differences from hybrid</h2><pre>COMPARISONS</pre></section>
    <details><summary>Results by question category</summary><pre>CATEGORIES</pre></details>
    <section><h2>Case details and evidence</h2>CASES</section><section><h2>Method limits</h2><ul>LIMITATIONS</ul></section></html>'''
    values={'RUN_ID':escape(report['run_id']),'DATASET':escape(report.get('dataset_name') or ''),'REVIEW_STATUS':escape(report.get('review_status') or ''),
            'TABLE':table,'TOP_K':str(report['top_k']),'EXTRACTION':escape(json.dumps(report.get('extraction'),indent=2)),
            'SECURITY':escape(json.dumps(report.get('security_regression_suite',{'status':'not run'}),indent=2)),
            'JUDGE':escape(json.dumps({name:score.get('advisory_judge',{}) for name,score in report['summary'].items()},indent=2)),
            'COMPARISONS':comparisons,'CATEGORIES':categories,'CASES':''.join(cases),
            'LIMITATIONS':''.join('<li>'+escape(s)+'</li>' for s in report['limitations'])}
    # Single substitution pass prevents placeholder text in evidence being interpreted.
    import re
    document=re.sub('|'.join(re.escape(k) for k in sorted(values,key=len,reverse=True)),lambda m:values[m.group()],document)
    (out/'index.html').write_text(document,encoding='utf-8')

if __name__=='__main__':
    import argparse,hashlib,shutil
    from datetime import datetime,timezone
    from pathlib import Path
    from benchmark import summarize,save_json
    parser=argparse.ArgumentParser(description='Regenerate summaries in a new directory without rerunning or replacing raw measurements.')
    parser.add_argument('--report',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--judge-model');parser.add_argument('--judge-config',default='hybrid');parser.add_argument('--judge-limit',type=int,default=8)
    parser.add_argument('--ollama-url',default='http://localhost:11434');args=parser.parse_args()
    source=Path(args.report);out=Path(args.output)
    if out.exists() and any(out.iterdir()):raise ValueError('Choose an empty output directory.')
    out.mkdir(parents=True,exist_ok=True);report=json.loads(source.read_text(encoding='utf-8'))
    if report.get('status')!='complete':raise ValueError('The source run is not complete.')
    report['raw_source_report_sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
    report['summary_code_sha256']=hashlib.sha256(Path(__file__).read_bytes()+(Path(__file__).parent/'benchmark.py').read_bytes()).hexdigest()
    for name in ('dataset.json','manifest.json','security.log'):
        if (source.parent/name).exists():shutil.copyfile(source.parent/name,out/name)
    if (out/'dataset.json').exists():
        logical=json.loads((out/'dataset.json').read_text(encoding='utf-8'))
        for case in logical['cases']:
            for evidence in case.get('expected_sources',[]):evidence.pop('version_id',None)
        report['case_set_sha256']=hashlib.sha256(json.dumps(logical,sort_keys=True).encode()).hexdigest()
    if args.judge_model:
        import httpx
        from benchmark_judge import judge_case
        if args.judge_config not in report['results'] or args.judge_limit<1:raise ValueError('Choose an existing judge configuration and positive case limit.')
        dataset=json.loads((out/'dataset.json').read_text(encoding='utf-8'));cases={c['id']:c for c in dataset['cases']};count=0
        for row in report['results'][args.judge_config]:
            if count>=args.judge_limit:break
            case=cases[row['case_id']]
            if not row['ok'] or case.get('abstain'):continue
            if 'judge' in row:row['prior_judge']=row['judge']
            try:row['judge']=judge_case(row,case,args.judge_model,args.ollama_url)
            except (httpx.HTTPError,ValueError,KeyError):row['judge']={'error':'Judge output or service failed','advisory':True,'calibrated':False}
            count+=1;print('Advisory judge',row['case_id'],flush=True)
        report['judge_rescore']={'model':args.judge_model,'configuration':args.judge_config,'cases':count,
          'created_at':datetime.now(timezone.utc).isoformat(),'judge_code_sha256':hashlib.sha256((Path(__file__).parent/'benchmark_judge.py').read_bytes()).hexdigest(),
          'note':'Rejudged frozen answers/context; original request timings and deterministic scores are unchanged.'}
    summarize(report);save_json(out/'report.json',report);write_report(report,out);print('Regenerated summaries:',out/'index.html')
