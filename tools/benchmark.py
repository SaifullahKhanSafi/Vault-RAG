"""Reproducible, authenticated RAG benchmark. Run --help; see BENCHMARKING.md."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import secrets
import statistics
import subprocess
import sys
import time
from uuid import uuid4
import httpx

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from smoke_test import login,checked,wait_job
from test_support import local_settings
from benchmark_metrics import (retrieval_metrics,fact_coverage,abstained,citation_metrics,
                                extraction_metrics,table_accuracy,distribution,paired_interval)
from benchmark_fixtures import build

CONFIGS={'lexical':('lexical',False),'vector':('vector',False),'hybrid':('hybrid',False),'hybrid-rerank':('hybrid',True)}

def validate(dataset):
    if not isinstance(dataset,dict) or dataset.get('schema_version')!=1:raise ValueError('Expected schema_version 1 dataset object.')
    cases=dataset.get('cases',[])
    if not cases:raise ValueError('Dataset is empty.')
    ids=set()
    for case in cases:
        if not isinstance(case.get('id'),str) or not case['id'] or case['id'] in ids:raise ValueError('Case IDs must be unique nonempty strings.')
        ids.add(case['id'])
        if not isinstance(case.get('question'),str) or not 1<=len(case['question'].strip())<=4000:raise ValueError('Invalid question.')
        gold=case.get('expected_sources',[]);pages=set()
        if not case.get('abstain') and (not gold or not case.get('facts')):raise ValueError('Answerable cases need expected_sources and facts.')
        for source in gold:
            if not isinstance(source.get('file'),str) or type(source.get('page')) is not int or source['page']<1:raise ValueError('Expected sources need file and physical page.')
            if (source['file'],source['page']) in pages:raise ValueError('Combine annotations into one evidence unit per file/page.')
            pages.add((source['file'],source['page']))
            if type(source.get('grade',2)) is not int or source.get('grade',2) not in (1,2,3):raise ValueError('Relevance grade must be 1, 2 or 3.')
            if not isinstance(source.get('contains',[]),list) or any(not isinstance(s,str) or not s.strip() for s in source.get('contains',[])):raise ValueError('contains must contain nonempty evidence strings.')
        for fact in case.get('facts',[]):
            if not isinstance(fact.get('alternatives'),list) or not fact['alternatives'] or any(not isinstance(s,str) or not s.strip() for s in fact['alternatives']):raise ValueError('Facts need nonempty alternative strings.')
    return dataset

def save_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp');temp.write_text(json.dumps(data,indent=2,default=str),encoding='utf-8');temp.replace(path)

class Engine:
    def __init__(self,client,workspace,pace=3.2):self.client=client;self.workspace=workspace;self.pace=pace;self.last=0
    def query(self,question,method,rerank=False,conversation=None,top_k=5):
        time.sleep(max(0,self.pace-(time.monotonic()-self.last)))
        status=self.client.get('/health').json()
        started=time.monotonic();self.last=started;answer='';sources=[];diagnostics={};meta={};first=None;done=False
        with self.client.stream('POST','/query',json={'workspace_id':self.workspace,'question':question,
          'method':method,'rerank':rerank,'top_k':top_k,'include_context':True,
          'conversation_id':conversation,'request_id':str(uuid4())}) as response:
            if response.status_code!=200:
                response.read();return {'ok':False,'http_status':response.status_code,'error':'HTTP request rejected','seconds':time.monotonic()-started,'model_loaded_before':status.get('generation_model_loaded')}
            trace=response.headers.get('X-Trace-ID')
            for line in response.iter_lines():
                if not line.startswith('data: '):continue
                event=json.loads(line[6:]);kind=event['type'];value=event['data']
                if kind=='meta':meta=value
                elif kind=='diagnostics':diagnostics=value
                elif kind=='sources':sources=value
                elif kind=='token' and value:
                    if first is None:first=time.monotonic()-started
                    answer+=value
                elif kind=='error':return {'ok':False,'http_status':200,'error':value,'seconds':time.monotonic()-started,'answer':answer,'diagnostics':diagnostics,'model_loaded_before':status.get('generation_model_loaded')}
                elif kind=='done':done=True
        return {'ok':done and bool(diagnostics),'http_status':200,'answer':answer,'sources':sources,'diagnostics':diagnostics,
          'seconds':time.monotonic()-started,'ttft_seconds':first,'conversation_id':meta.get('conversation_id'),
          'trace_id':trace,'model_loaded_before':status.get('generation_model_loaded'),
          **({'error':'Missing completion or context diagnostics'} if not done or not diagnostics else {})}

def prepare(args,out):
    env=local_settings();admin=login(args.base_url,os.getenv('RAG_EVAL_EMAIL',env['BOOTSTRAP_ADMIN_EMAIL']),os.getenv('RAG_EVAL_PASSWORD',env['BOOTSTRAP_ADMIN_PASSWORD']))
    if not args.fixture:
        dataset=validate(json.loads(Path(args.dataset).read_text(encoding='utf-8')))
        if not args.workspace:raise ValueError('--workspace is required with --dataset')
        return admin,args.workspace,dataset,[]
    dataset,files=build(out/'corpus')
    workspace=checked(admin.post('/workspaces',json={'name':'Synthetic benchmark '+out.name[-12:]}),201)['id']
    password=secrets.token_urlsafe(24);email='benchmark-'+uuid4().hex[:12]+'@example.com'
    checked(admin.post(f'/workspaces/{workspace}/users',json={'email':email,'name':'Isolated benchmark actor','password':password,'role':'admin'}),201)
    client=login(args.base_url,email,password);admin.close();last_upload=0;manifest=[]
    for artifact in files:
        time.sleep(max(0,6.2-(time.monotonic()-last_upload)));last_upload=time.monotonic()
        path=Path(artifact['path']);data=path.read_bytes();started=time.monotonic()
        if path.name=='orion.pdf':data=(out/'corpus'/'orion-v1.fixture').read_bytes()
        record=checked(client.post(f'/workspaces/{workspace}/documents',files={'file':(path.name,data,'application/pdf')}),202)
        wait_job(client,workspace,record['job_id'],timeout=240)
        if path.name=='orion.pdf':
            time.sleep(max(0,6.2-(time.monotonic()-last_upload)));last_upload=time.monotonic()
            record=checked(client.post(f'/workspaces/{workspace}/documents/{record["id"]}/versions',files={'file':(path.name,path.read_bytes(),'application/pdf')}),202)
            wait_job(client,workspace,record['job_id'],timeout=240)
        manifest.append({**artifact,**record,'ingestion_seconds':round(time.monotonic()-started,3),'bytes':path.stat().st_size})
        print('Indexed',path.name,flush=True)
        save_json(out/'manifest.json',{'workspace_id':workspace,'documents':manifest})
    return client,workspace,validate(dataset),manifest

def bind_versions(client,workspace,dataset):
    documents=checked(client.get(f'/workspaces/{workspace}/documents'));by_name={d['name']:d for d in documents}
    for case in dataset['cases']:
        for source in case.get('expected_sources',[]):
            doc=by_name.get(source['file'])
            if not doc or not doc['active_version']:raise ValueError('Expected document is not indexed: '+source['file'])
            if source.get('version_id') and source['version_id']!=doc['active_version']:raise ValueError('Expected version is not the active version: '+source['file'])
            source['version_id']=doc['active_version']
    return documents

def score(row,case):
    row.update(case_id=case['id'],family=case.get('family',case['id']),category=case.get('category','unspecified'),expected_abstention=bool(case.get('abstain')))
    if not row['ok']:
        row['passed']=False;row['failures']=['api_error' if row.get('http_status')!=200 else 'stream_error'];return row
    gold=case.get('expected_sources',[]);context=row['diagnostics']['final_context'];candidates=row['diagnostics']['candidates']
    row['candidate_metrics']={str(k):retrieval_metrics(candidates,gold,k) for k in (5,10)}
    row['final_metrics']=retrieval_metrics(context,gold,row['diagnostics']['top_k'])
    row['fact_coverage']=fact_coverage(row['answer'],case.get('facts',[]));row['abstained']=abstained(row['answer'])
    row['citations']=citation_metrics(row['answer'],context,gold);failures=[]
    if any(value.casefold() in row['answer'].casefold() for value in case.get('forbidden',[])):failures.append('forbidden_or_injected_content')
    if case.get('abstain'):
        if not row['abstained']:failures.append('unsupported_answer')
    else:
        if row['abstained']:failures.append('false_refusal')
        if row['fact_coverage']!=1:failures.append('expected_fact_missing')
        if row['final_metrics']['recall']!=1:failures.append('evidence_missing_from_final_context')
        if row['citations']['gold_evidence_coverage']!=1:failures.append('gold_evidence_citation_missing')
    if row['citations']['invalid_references']:failures.append('invalid_citation')
    if row['diagnostics']['rerank_status']=='fallback':failures.append('reranker_fallback')
    row['passed']=not failures;row['failures']=failures
    return row

def extraction_report(client,documents,dataset):
    result=[];by_name={d['name']:d for d in documents}
    for reference in dataset.get('extraction_references',[]):
        doc=by_name.get(reference['file'])
        if not doc:result.append({'file':reference['file'],'available':False});continue
        data=checked(client.get('/documents/'+doc['id']+'/extraction'))
        page=next((p for p in data['pages'] if p['page']==reference['page']),None)
        item={'file':reference['file'],'page':reference['page'],'available':bool(page)}
        if page:
            item['method']=page['method']
            if 'text' in reference:item.update(extraction_metrics(page['text_content'],reference['text']))
            if 'table' in reference:item['table_cell_accuracy']=table_accuracy(page['tables'],reference['table'])
        result.append(item)
    return result

def aggregate(rows):
    valid=[r for r in rows if r['ok']];answerable=[r for r in rows if not r['expected_abstention']];unanswerable=[r for r in rows if r['expected_abstention']]
    def mean(values):
        values=[v for v in values if v is not None];return statistics.mean(values) if values else None
    failures={}
    for row in rows:
        for reason in row['failures']:failures[reason]=failures.get(reason,0)+1
    judged=[r['judge'] for r in rows if r.get('judge') and 'error' not in r['judge']]
    return {'cases':len(rows),'completed':len(valid),'error_rate':1-len(valid)/len(rows) if rows else None,
      'strict_fixture_pass_rate':mean([float(r['passed']) for r in rows]),
      'candidate_recall_at_5':mean([(r.get('candidate_metrics',{}).get('5') or {}).get('recall',0) for r in answerable]),
      'candidate_recall_at_10':mean([(r.get('candidate_metrics',{}).get('10') or {}).get('recall',0) for r in answerable]),
      'final_recall':mean([(r.get('final_metrics') or {}).get('recall',0) for r in answerable]),
      'final_precision':mean([(r.get('final_metrics') or {}).get('precision',0) for r in answerable]),
      'final_ndcg':mean([(r.get('final_metrics') or {}).get('ndcg',0) for r in answerable]),
      'final_mrr':mean([(r.get('final_metrics') or {}).get('mrr',0) for r in answerable]),
      'fact_coverage':mean([r.get('fact_coverage',0) for r in answerable]),
      'correct_abstention_rate':mean([float(r.get('ok') and r.get('abstained',False)) for r in unanswerable]),
      'false_refusal_rate_completed':mean([float(r.get('abstained',False)) for r in answerable if r['ok']]),
      'gold_citation_coverage':mean([r.get('citations',{}).get('gold_evidence_coverage',0) for r in answerable]),
      'latency_all_completed_seconds':distribution([r['seconds'] for r in valid]),
      'latency_warm_observed_seconds':distribution([r['seconds'] for r in valid if r.get('model_loaded_before')]),
      'latency_completed_with_context_seconds':distribution([r['seconds'] for r in valid if r['diagnostics']['final_context']]),
      'empty_context_completions':sum(not r['diagnostics']['final_context'] for r in valid),
      'latency_cold_observed_seconds':distribution([r['seconds'] for r in valid if r.get('model_loaded_before') is False]),
      'ttft_seconds':distribution([r.get('ttft_seconds') for r in valid]),
      'retrieval_seconds':distribution([r['diagnostics']['retrieval_ms']/1000 for r in valid]),'failures':failures,
      'advisory_judge':{'attempted':sum('judge' in r for r in rows),'errors':sum('error' in r.get('judge',{}) for r in rows),
         'cases':len(judged),'calibrated':False,**{key:mean([j.get(key) for j in judged]) for key in
         ('faithfulness','correctness_precision','correctness_recall','correctness_f1','citation_precision','citation_completeness')}}}

def summarize(report):
    report['summary']={name:aggregate(rows) for name,rows in report['results'].items()}
    report['categories']={name:{category:aggregate([r for r in rows if r['category']==category]) for category in sorted({r['category'] for r in rows})} for name,rows in report['results'].items()}
    base=report['results'].get('hybrid',[]);report['paired_comparisons_to_hybrid']={}
    def grouped(rows):
        cases={}
        for row in rows:cases.setdefault(row['case_id'],[]).append(row)
        return {key:(statistics.mean(float(r['passed']) for r in values),values[0]['family']) for key,values in cases.items()}
    for name,rows in report['results'].items():
        if name=='hybrid':continue
        report['paired_comparisons_to_hybrid'][name]=paired_interval(
          grouped(base),grouped(rows))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    source=parser.add_mutually_exclusive_group(required=True);source.add_argument('--fixture',action='store_true');source.add_argument('--dataset')
    parser.add_argument('--workspace');parser.add_argument('--base-url',default='http://localhost:8000')
    parser.add_argument('--configs',nargs='+',choices=list(CONFIGS),default=list(CONFIGS));parser.add_argument('--limit',type=int,default=40)
    parser.add_argument('--top-k',type=int,choices=range(1,11),default=5);parser.add_argument('--pace',type=float,default=3.2)
    parser.add_argument('--repeats',type=int,default=1);parser.add_argument('--output');parser.add_argument('--validate-only',action='store_true')
    parser.add_argument('--security',action='store_true',help='Run the existing isolated enterprise security/OCR regression suite.')
    parser.add_argument('--judge-model');parser.add_argument('--judge-config',default='hybrid');parser.add_argument('--judge-limit',type=int,default=8)
    parser.add_argument('--ollama-url',default='http://localhost:11434');parser.add_argument('--fail-on-errors',action='store_true')
    args=parser.parse_args()
    if len(set(args.configs))!=len(args.configs):parser.error('Choose each configuration once; use --repeats for repeated measurements.')
    if args.judge_model and (args.judge_config not in args.configs or args.judge_limit<1):parser.error('Choose a selected --judge-config and a positive --judge-limit.')
    if args.limit<1 or args.repeats<1 or args.pace<0:parser.error('Limits/repeats must be positive and pace nonnegative.')
    if args.validate_only:
        if not args.dataset:parser.error('--validate-only requires --dataset')
        data=validate(json.loads(Path(args.dataset).read_text(encoding='utf-8')));print('Valid dataset:',len(data['cases']),'cases');return
    run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:6]
    out=Path(args.output) if args.output else ROOT/'output'/'benchmarks'/run_id;out.mkdir(parents=True,exist_ok=True)
    if (out/'report.json').exists():raise ValueError('Output already contains a report. Choose a new directory to preserve the previous run.')
    report={'run_id':run_id,'created_at_utc':datetime.now(timezone.utc).isoformat(),'status':'preparing',
      'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'host':{'platform':platform.platform(),'cpu_count':os.cpu_count(),'python':platform.python_version()},
      'configurations':args.configs,'top_k':args.top_k,'repeats':args.repeats,'pace_seconds':args.pace,'results':{},
      'limitations':['Synthetic fixture labels are agent-authored, not human-reviewed business ground truth.',
        'Deterministic fact/citation checks are proxies, not semantic correctness or faithfulness.',
        'Gold evidence units are unique file/page pairs with optional required text; duplicate hits receive no extra gain.',
        'Precision@k uses denominator k even if fewer results exist; relevance depends on annotation completeness.',
        'Candidate Recall@10 is before reranking; final metrics describe the actual context supplied to generation.',
        'Model-loaded status is observed, not a controlled cold-start experiment. TTFT begins at HTTP send.',
        'Latency percentiles on small samples are descriptive. Errors remain visible; latency is conditional on completion. Fast empty-context refusals are also counted separately.',
        'Paired intervals are exploratory and cluster related questions; no universal industry threshold is claimed.']}
    client=None
    save_json(out/'report.json',report)
    try:
        client,workspace,dataset,manifest=prepare(args,out);dataset['cases']=dataset['cases'][:args.limit]
        documents=bind_versions(client,workspace,dataset);save_json(out/'dataset.json',dataset)
        logical=json.loads(json.dumps(dataset))
        for case in logical['cases']:
            for source in case.get('expected_sources',[]):source.pop('version_id',None)
        report.update(workspace_id=workspace,dataset_name=dataset.get('name'),review_status=dataset.get('review_status','unspecified'),
          case_set_sha256=hashlib.sha256(json.dumps(logical,sort_keys=True).encode()).hexdigest(),
          judgments_complete=dataset.get('judgments_complete',False),dataset_sha256=hashlib.sha256(json.dumps(dataset,sort_keys=True).encode()).hexdigest(),
          corpus=[{k:d.get(k) for k in ('id','name','active_version','chunk_count')} for d in documents],
          extraction=extraction_report(client,documents,dataset),status='running')
        with httpx.Client(timeout=10) as models:
            try:report['ollama_models']=models.get(args.ollama_url+'/api/tags').json().get('models',[])
            except httpx.HTTPError:report['ollama_models']=None
        engine=Engine(client,workspace,args.pace);save_json(out/'report.json',report)
        for config in args.configs:
            method,rerank=CONFIGS[config];rows=report['results'][config]=[]
            for repeat in range(args.repeats):
                for case in dataset['cases']:
                    try:
                        cid=None
                        if case.get('setup_question'):
                            setup=engine.query(case['setup_question'],method,rerank,top_k=args.top_k)
                            if not setup['ok']:raise ValueError('Follow-up setup failed')
                            cid=setup['conversation_id']
                        row=engine.query(case['question'],method,rerank,cid,args.top_k)
                    except (httpx.HTTPError,ValueError,KeyError) as error:
                        row={'ok':False,'error':type(error).__name__,'http_status':None,'seconds':None}
                    row['repeat']=repeat+1;score(row,case);rows.append(row)
                    save_json(out/'report.json',report)
                    print(config,case['id'],'PASS' if row['passed'] else ','.join(row['failures']),round(row.get('seconds') or 0,2),'s',flush=True)
        if args.judge_model:
            from benchmark_judge import judge_case
            judged=0
            for row in report['results'].get(args.judge_config,[]):
                if not row['ok'] or row['expected_abstention']:continue
                if judged>=args.judge_limit:break
                case=next(c for c in dataset['cases'] if c['id']==row['case_id'])
                try:row['judge']=judge_case(row,case,args.judge_model,args.ollama_url)
                except (httpx.HTTPError,ValueError,KeyError):row['judge']={'error':'Judge output or service failed','advisory':True,'calibrated':False}
                judged+=1;save_json(out/'report.json',report);print('Advisory judge',row['case_id'],flush=True)
        if args.security:
            result=subprocess.run([sys.executable,'-u',str(ROOT/'tools'/'test_enterprise_features.py')],cwd=ROOT,capture_output=True,text=True)
            (out/'security.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
            report['security_regression_suite']={'passed':result.returncode==0,'log':'security.log','scope':'Existing isolated account, ACL/RLS, revocation, OCR and SSO-recovery regression checks; not a security certification.'}
        summarize(report);report['status']='complete';report['completed_at_utc']=datetime.now(timezone.utc).isoformat();save_json(out/'report.json',report)
        from benchmark_report import write_report
        write_report(report,out)
        print('Report:',out/'index.html',flush=True)
        if args.fail_on_errors and (any(not r['ok'] for rows in report['results'].values() for r in rows) or report.get('security_regression_suite',{}).get('passed') is False):raise SystemExit(1)
    except BaseException as error:
        if report.get('status')!='complete':
            report['status']='interrupted' if isinstance(error,KeyboardInterrupt) else 'failed'
            report['failure_type']=type(error).__name__;save_json(out/'report.json',report)
        raise
    finally:
        if client:client.close()

if __name__=='__main__':main()
