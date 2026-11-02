"""Seed RAG evaluation: retrieval coverage, expected facts, abstention and citation presence."""
import argparse
import json
from pathlib import Path
import re
import sys
import time
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from smoke_test import login,checked,wait_job,ask
from test_support import local_settings,fixture_pdf

parser=argparse.ArgumentParser()
parser.add_argument("--base-url",default="http://localhost:8000")
parser.add_argument("--dataset",default=str(ROOT/"evals"/"cedar.json"))
parser.add_argument("--limit",type=int,default=20)
parser.add_argument("--method",choices=["vector","hybrid"],default="hybrid")
parser.add_argument("--rerank",action="store_true")
parser.add_argument("--min-pass-rate",type=float,default=.9)
args=parser.parse_args()
cases=json.loads(Path(args.dataset).read_text())[:args.limit]
env=local_settings()
client=login(args.base_url,env["BOOTSTRAP_ADMIN_EMAIL"],env["BOOTSTRAP_ADMIN_PASSWORD"])
workspace=checked(client.post("/workspaces",json={"name":"Evaluation "+uuid4().hex[:8]}),201)["id"]
name="cedar-evaluation.pdf"
document=checked(client.post(f"/workspaces/{workspace}/documents",files={"file":(name,fixture_pdf(),"application/pdf")}),202)
results=[]
try:
    wait_job(client,workspace,document["job_id"])
    for case in cases:
        # Respect the normal user request budget; evaluation never disables rate limits.
        time.sleep(3)
        found=checked(client.post(f"/workspaces/{workspace}/search",json={"question":case["question"],"document_ids":[document["id"]],"method":args.method}))["sources"]
        conversation=None
        if case.get("setup_question"):
            _,_,meta=ask(client,workspace,case["setup_question"],documents=[document["id"]],method=args.method)
            conversation=meta["conversation_id"]
        start=time.monotonic()
        answer,sources,_=ask(client,workspace,case["question"],conversation,[document["id"]],rerank=args.rerank,method=args.method)
        normalized=re.sub(r"[,\\]","",answer.lower())
        markers=["cannot find","not provided","not specified","does not contain","not contain","no information","not available","not mentioned"]
        abstained=any(marker in normalized for marker in markers)
        expected=all(value.lower() in normalized for value in case.get("expected",[]))
        alternatives=not case.get("any_of") or any(value.lower() in normalized for value in case["any_of"])
        factual=abstained if case.get("abstain") else expected and alternatives and not abstained
        retrieval=any(s["document_id"]==document["id"] and s["page"]==1 for s in found)
        citation=any(s["document_id"]==document["id"] and s["page"]==1 for s in sources) and bool(re.search(r"p\\?\.\\?\s*1",answer,re.I))
        # Abstaining answers are not required to cite an unsupported fact.
        passed=factual and retrieval and (case.get("abstain",False) or citation)
        results.append({"id":case["id"],"passed":passed,"retrieval_hit":retrieval,"fact_or_abstention_pass":factual,
                        "citation_present":citation,"seconds":round(time.monotonic()-start,2),"answer":answer})
        print(case["id"],"PASS" if passed else "FAIL",flush=True)
finally:
    client.delete("/documents/"+document["id"])
    client.close()
report={"dataset":str(Path(args.dataset).name),"method":args.method,"rerank":args.rerank,"cases":len(results),
        "pass_rate":sum(r["passed"] for r in results)/len(results) if results else 0,
        "retrieval_hit_rate":sum(r["retrieval_hit"] for r in results)/len(results) if results else 0,
        "results":results,"limitations":"Synthetic one-page seed set. Presence/phrase checks do not establish claim-level faithfulness or enterprise-domain accuracy."}
destination=ROOT/"output";destination.mkdir(exist_ok=True)
path=destination/("evaluation-"+args.method+("-rerank" if args.rerank else "")+".json")
path.write_text(json.dumps(report,indent=2),encoding="utf-8")
print("Evaluation saved:",path,"pass rate:",report["pass_rate"],flush=True)
if report["pass_rate"]<args.min_pass_rate:raise SystemExit(1)
