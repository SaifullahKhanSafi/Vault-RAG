"""Dependency-free benchmark mathematics; missing annotations remain unscored."""
import math
import random
import re
import statistics
import unicodedata

def normalized(text):
    return ' '.join(unicodedata.normalize('NFKC',str(text)).replace('\\','').casefold().split())

def matches(row,gold):
    return row.get('file')==gold['file'] and row.get('page')==gold['page'] and (
        not gold.get('version_id') or row.get('version_id')==gold['version_id']) and all(
            normalized(part) in normalized(row.get('content','')) for part in gold.get('contains',[]))

def retrieval_metrics(rows,gold,k):
    if not gold:return None
    covered=set();gains=[]
    for row in rows[:k]:
        indices=[i for i,g in enumerate(gold) if matches(row,g)]
        fresh=[i for i in indices if i not in covered]
        gain=max((gold[i].get('grade',2) for i in fresh),default=0)
        gains.append(gain);covered.update(indices)
    ideal=sorted([g.get('grade',2) for g in gold],reverse=True)[:k]
    dcg=lambda values:sum((2**v-1)/math.log2(i+2) for i,v in enumerate(values))
    return {'recall':len(covered)/len(gold),'precision':sum(g>0 for g in gains)/k,
            'hit':float(bool(covered)),'mrr':next((1/(i+1) for i,g in enumerate(gains) if g),0.),
            'ndcg':dcg(gains)/dcg(ideal) if ideal else 0.}

def fact_coverage(answer,facts):
    if not facts:return None
    text=normalized(answer)
    return sum(any(normalized(a) in text for a in fact['alternatives']) for fact in facts)/len(facts)

def abstained(answer):
    text=normalized(answer)
    return any(marker in text for marker in ["cannot find", "can't find",'not provided','not specified',
        'no information','not contain the answer','not available in','not mentioned','does not state'])

def citation_metrics(answer,context,gold):
    # A bibliographic match is validity/coverage, not semantic support for a claim.
    references=re.findall(r'\[([^\[\]]+?),\s*p\.\s*(\d+)\]',str(answer).replace('\\',''),flags=re.I)
    cited={(name.strip(),int(page)) for name,page in references}
    provided={(s['file'],s['page']) for s in context}
    relevant={(g['file'],g['page']) for g in gold if any(matches(row,g) for row in context)}
    return {'reference_validity':len(cited&provided)/len(cited) if cited else None,
            'gold_evidence_coverage':len(cited&relevant)/len(gold) if gold else None,
            'invalid_references':[{'file':name,'page':page} for name,page in sorted(cited-provided)],
            'reference_count':len(references)}

def edit_distance(left,right):
    if len(left)<len(right):left,right=right,left
    previous=list(range(len(right)+1))
    for i,a in enumerate(left,1):
        current=[i]
        for j,b in enumerate(right,1):current.append(min(current[-1]+1,previous[j]+1,previous[j-1]+(a!=b)))
        previous=current
    return previous[-1]

def extraction_metrics(predicted,reference):
    actual=normalized(predicted);expected=normalized(reference)
    return {'cer':edit_distance(actual,expected)/len(expected) if expected else None,
            'wer':edit_distance(actual.split(),expected.split())/len(expected.split()) if expected else None}

def table_accuracy(actual,expected):
    if not expected:return None
    cells=[(r,c,normalized(cell)) for r,row in enumerate(expected) for c,cell in enumerate(row)]
    def score(table):
        return sum(r<len(table) and c<len(table[r]) and normalized(table[r][c] or '')==value for r,c,value in cells)/len(cells)
    return max((score(table) for table in actual),default=0.)

def percentile(values,p):
    if not values:return None
    values=sorted(values);position=(len(values)-1)*p;low=int(position);high=math.ceil(position)
    return values[low]+(values[high]-values[low])*(position-low)

def distribution(values):
    values=[v for v in values if v is not None]
    return {'n':len(values),'mean':statistics.mean(values) if values else None,
            'median':percentile(values,.5),'p95':percentile(values,.95)}

def paired_interval(baseline,candidate,seed=42,iterations=1000):
    """Cluster bootstrap paired cases by question family, including failed cases as zero upstream."""
    shared=sorted(set(baseline)&set(candidate))
    if not shared:return None
    groups={}
    for key in shared:
        value,family=baseline[key];other,_=candidate[key]
        groups.setdefault(family,[]).append(other-value)
    names=sorted(groups);rng=random.Random(seed);samples=[]
    for _ in range(iterations):
        selected=[delta for name in rng.choices(names,k=len(names)) for delta in groups[name]]
        samples.append(statistics.mean(selected))
    return {'delta':statistics.mean(candidate[k][0]-baseline[k][0] for k in shared),
            'ci95':[percentile(samples,.025),percentile(samples,.975)],'paired_cases':len(shared),
            'families':len(names),'method':'question-family cluster bootstrap; exploratory on small synthetic sets'}
