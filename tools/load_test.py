"""Small authenticated load probe; reports successes, overload responses and latency."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import statistics
import sys
import time
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from smoke_test import login,checked
from test_support import local_settings

parser=argparse.ArgumentParser()
parser.add_argument("--base-url",default="http://localhost:8000")
parser.add_argument("--requests",type=int,default=8)
parser.add_argument("--concurrency",type=int,default=4)
parser.add_argument("--workspace")
parser.add_argument("--question",default="What information is available?")
args=parser.parse_args()
if not 1<=args.requests<=100 or not 1<=args.concurrency<=16:raise SystemExit("Use 1-100 requests and 1-16 clients.")
env=local_settings()
client=login(args.base_url,env["BOOTSTRAP_ADMIN_EMAIL"],env["BOOTSTRAP_ADMIN_PASSWORD"])
workspace=args.workspace or checked(client.post("/workspaces",json={"name":"Load probe "+uuid4().hex[:8]}),201)["id"]

def request(index):
    start=time.monotonic()
    with client.stream("POST","/query",json={"workspace_id":workspace,"question":args.question}) as response:
        status=response.status_code
        response.read()
    return {"status":status,"seconds":round(time.monotonic()-start,3)}
with ThreadPoolExecutor(max_workers=args.concurrency) as executor:rows=list(executor.map(request,range(args.requests)))
times=sorted(row["seconds"] for row in rows)
report={"workspace_id":workspace,"requests":len(rows),"concurrency":args.concurrency,
        "status_counts":{str(s):sum(r["status"]==s for r in rows) for s in {r["status"] for r in rows}},
        "p50_seconds":statistics.median(times),"p95_seconds":times[min(len(times)-1,int(.95*len(times)))],
        "note":"503 means the bounded shared model capacity is busy; this is not an answer-quality evaluation."}
destination=ROOT/"output";destination.mkdir(exist_ok=True)
(destination/"load-test.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
print(json.dumps(report,indent=2))
client.close()
if any(row["status"] not in (200,429,503) for row in rows):raise SystemExit(1)
