"""Small real-generation load probe. Records rejections/errors and never retries them away."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import secrets
import sys
import time
from uuid import uuid4
import httpx
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from smoke_test import login,checked
from test_support import local_settings
from benchmark import Engine,save_json
from benchmark_metrics import distribution

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workspace',required=True)
    p.add_argument('--concurrency',nargs='+',type=int,default=[1,2,4]);p.add_argument('--requests',type=int,default=6)
    p.add_argument('--question',default='What is the approval code for Project Cedar?');p.add_argument('--base-url',default='http://localhost:8000')
    p.add_argument('--output');p.add_argument('--cold-start',action='store_true',help='Explicitly unload the local chat model first; affects other local users.')
    p.add_argument('--ollama-url',default='http://localhost:11434');args=p.parse_args()
    if not 1<=args.requests<=18 or any(not 1<=c<=8 for c in args.concurrency) or args.requests*len(args.concurrency)>18:
        p.error('Use 1..8 concurrent clients and at most 18 total requests per run to stay below the normal per-user query budget.')
    env=local_settings();admin=login(args.base_url,os.getenv('RAG_EVAL_EMAIL',env['BOOTSTRAP_ADMIN_EMAIL']),os.getenv('RAG_EVAL_PASSWORD',env['BOOTSTRAP_ADMIN_PASSWORD']))
    password=secrets.token_urlsafe(24);email='load-'+uuid4().hex[:12]+'@example.com'
    checked(admin.post(f'/workspaces/{args.workspace}/users',json={'email':email,'name':'Isolated load actor','password':password,'role':'reader'}),201);admin.close()
    client=login(args.base_url,email,password);engine=Engine(client,args.workspace,pace=0)
    out=Path(args.output) if args.output else ROOT/'output'/'benchmarks'/('load-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    if (out/'load.json').exists():raise ValueError('Choose a new output directory.')
    if args.cold_start:
        with httpx.Client(timeout=30) as local:
            response=local.post(args.ollama_url+'/api/generate',json={'model':env.get('CHAT_MODEL','qwen2.5:7b-instruct'),'keep_alive':0});response.raise_for_status()
    report={'workspace_id':args.workspace,'requests_per_level':args.requests,'forced_model_unload':args.cold_start,'levels':[],
      'limitations':['A small descriptive load probe, not a production capacity guarantee.',
        'Each request performs real generation on accessible PDFs. HTTP 503/429 and stream errors are counted, not retried.',
        'Cold-start model unloading occurs only with --cold-start. Cached/empty answers are not equivalent to real generation.',
        'Model memory is an Ollama after-batch snapshot, not host peak RAM or peak GPU allocation.']}
    try:
        for level in args.concurrency:
            started=time.monotonic()
            def request(_):
                try:return engine.query(args.question,'hybrid')
                except httpx.HTTPError as error:return {'ok':False,'error':type(error).__name__,'http_status':None}
            with ThreadPoolExecutor(max_workers=level) as pool:rows=list(pool.map(request,range(args.requests)))
            wall=time.monotonic()-started;complete=[r for r in rows if r['ok']]
            generated=[r for r in complete if r.get('diagnostics',{}).get('final_context')]
            statuses={}
            for row in rows:
                key=str(row.get('http_status'));statuses[key]=statuses.get(key,0)+1
            with httpx.Client(timeout=10) as local:
                try:memory=local.get(args.ollama_url+'/api/ps').json().get('models',[])
                except httpx.HTTPError:memory=None
            report['levels'].append({'concurrency':level,'attempted':len(rows),'completed':len(complete),
              'completion_rate':len(complete)/len(rows),'http_statuses':statuses,'elapsed_seconds':wall,
              'completed_with_document_context':len(generated),'empty_context_completions':len(complete)-len(generated),
              'completed_requests_per_second':len(complete)/wall,'attempted_requests_per_second':len(rows)/wall,
              'latency_completed_seconds':distribution([r['seconds'] for r in complete]),
              'ttft_completed_seconds':distribution([r.get('ttft_seconds') for r in complete]),'model_memory_after_batch':memory,'requests':rows})
            save_json(out/'load.json',report);print('Concurrency',level,':',len(complete),'completed of',len(rows),'statuses',statuses,flush=True)
        import csv
        with (out/'load.csv').open('w',newline='',encoding='utf-8') as stream:
            writer=csv.DictWriter(stream,fieldnames=['concurrency','attempted','completed','completion_rate','completed_requests_per_second','p95_seconds','statuses']);writer.writeheader()
            for row in report['levels']:writer.writerow({**{k:row[k] for k in ['concurrency','attempted','completed','completion_rate','completed_requests_per_second']},'p95_seconds':row['latency_completed_seconds']['p95'],'statuses':json.dumps(row['http_statuses'])})
        print('Load results:',out/'load.json',flush=True)
    finally:client.close()

if __name__=='__main__':main()
