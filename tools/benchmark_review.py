"""Blind human-review export and optional judge calibration. Never invents human labels."""
import argparse,csv,hashlib,json
from pathlib import Path
from benchmark_report import safe_cell

def label(value):
    text=str(value).strip().lower()
    if text in ('true','yes','1'):return True
    if text in ('false','no','0'):return False
    if text in ('','unknown','unsure'):return None
    raise ValueError('Labels must be yes/no/unknown or blank.')

def agreement(pairs):
    if not pairs:return {'n':0}
    agree=sum(a==b for a,b in pairs)/len(pairs)
    pa=sum(a for a,b in pairs)/len(pairs);pb=sum(b for a,b in pairs)/len(pairs)
    chance=pa*pb+(1-pa)*(1-pb)
    # Treat unsupported/incorrect as the positive warning class.
    tp=sum(not a and not b for a,b in pairs);fp=sum(not a and b for a,b in pairs);fn=sum(a and not b for a,b in pairs)
    precision=tp/(tp+fp) if tp+fp else None;recall=tp/(tp+fn) if tp+fn else None
    return {'n':len(pairs),'agreement':agree,'cohen_kappa':(agree-chance)/(1-chance) if chance<1 else None,
      'warning_precision':precision,'warning_recall':recall,'false_warnings':fp,'missed_warnings':fn}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',required=True)
    p.add_argument('--export');p.add_argument('--labels');p.add_argument('--output');args=p.parse_args()
    if bool(args.export)==bool(args.labels):p.error('Choose exactly one of --export or --labels.')
    path=Path(args.report);report=json.loads(path.read_text(encoding='utf-8'));records={}
    for config,rows in report['results'].items():
        for row in rows:
            if not row['ok']:continue
            prefix=f"{config}:{row['case_id']}:{row['repeat']}"
            records[prefix+':answer']={'unit':'answer','configuration':config,'case_id':row['case_id'],'text':row['answer'],'row':row,'claim':None}
            for index,claim in enumerate(row.get('judge',{}).get('claims',[])):
                records[prefix+f':claim-{index}']={'unit':'claim','configuration':config,'case_id':row['case_id'],'text':claim['text'],'row':row,'claim':claim}
    if args.export:
        dataset_path=path.parent/'dataset.json'
        dataset=json.loads(dataset_path.read_text(encoding='utf-8')) if dataset_path.exists() else {'cases':[]}
        cases={c['id']:c for c in dataset['cases']}
        destination=Path(args.export);destination.parent.mkdir(parents=True,exist_ok=True)
        fields=['review_id','text_sha256','unit','configuration','case_id','question','text','reference_facts','evidence','human_answer_correct','human_supported','human_correct','human_has_citation','human_citation_supported','reviewer','notes']
        with destination.open('w',newline='',encoding='utf-8') as stream:
            writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
            for identity,item in records.items():
                evidence='\n\n'.join(f"[{s['file']}, p. {s['page']}]\n{s['content']}" for s in item['row']['diagnostics']['final_context'])
                writer.writerow({k:safe_cell(v) for k,v in {'review_id':identity,'text_sha256':hashlib.sha256(item['text'].encode()).hexdigest(),**{k:item[k] for k in ['unit','configuration','case_id','text']},'question':cases.get(item['case_id'],{}).get('question',''),'reference_facts':json.dumps(cases.get(item['case_id'],{}).get('facts',[])),'evidence':evidence}.items()})
        print('Blind review sheet:',destination);return
    pairs={key:[] for key in ('supported','correct','has_citation','citation_supported')};answers=[];seen=set()
    with Path(args.labels).open(newline='',encoding='utf-8-sig') as stream:
        for entry in csv.DictReader(stream):
            identity=entry['review_id']
            if identity in seen:raise ValueError('Duplicate review row: '+identity)
            seen.add(identity);item=records.get(identity)
            if not item or hashlib.sha256(item['text'].encode()).hexdigest()!=entry['text_sha256'] or safe_cell(item['text'])!=entry['text']:raise ValueError('Review row does not match the frozen report.')
            if item['unit']=='answer':
                value=label(entry.get('human_answer_correct',''))
                if value is not None:answers.append(value)
            else:
                for key in pairs:
                    human=label(entry.get('human_'+key,''));prediction=item['claim'].get(key)
                    if human is not None and type(prediction) is bool:pairs[key].append((prediction,human))
    result={'human_reviewed_answers':len(answers),'human_answer_accuracy':sum(answers)/len(answers) if answers else None,
      'eligible_answers':sum(r['unit']=='answer' for r in records.values()),'judge_calibration':{key:agreement(values) for key,values in pairs.items()},
      'note':'Scores apply only to supplied human labels. Blank/unknown labels are excluded; no coverage is inferred.'}
    output=Path(args.output) if args.output else path.parent/'human-review.json';output.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
