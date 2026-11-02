"""Live authenticated acceptance checks. Uses isolated smoke workspaces, never resets data."""
import argparse
import json
import secrets
import time
from uuid import uuid4
import httpx
from test_support import local_settings,fixture_pdf

def login(base,email,password):
    client=httpx.Client(base_url=base,timeout=330)
    result=client.post("/auth/login",json={"email":email,"password":password})
    result.raise_for_status()
    client.headers["X-CSRF-Token"]=result.json()["csrf_token"]
    return client

def checked(response,status=200):
    assert response.status_code==status,f"{response.status_code}: {response.text[:500]}"
    return response.json()

def wait_job(client,workspace,job,expected="ready",timeout=180):
    started=time.monotonic()
    while time.monotonic()-started<timeout:
        tasks=checked(client.get(f"/workspaces/{workspace}/jobs"))
        row=next(j for j in tasks if j["id"]==job)
        if row["status"] in ("ready","failed","cancelled"):
            assert row["status"]==expected,row
            return row
        time.sleep(1)
    raise AssertionError("Timed out waiting for ingestion job")

def ask(client,workspace,question,conversation=None,documents=None,request_id=None,rerank=False,method="hybrid"):
    answer="";sources=[];meta={};complete=False
    payload={"workspace_id":workspace,"question":question,"request_id":request_id or str(uuid4()),
             "document_ids":documents or [],"rerank":rerank,"method":method}
    if conversation:payload["conversation_id"]=conversation
    started=time.monotonic()
    with client.stream("POST","/query",json=payload) as response:
        assert response.status_code==200,response.read()
        for line in response.iter_lines():
            if not line.startswith("data: "):continue
            event=json.loads(line[6:])
            if event["type"]=="error":raise AssertionError(event["data"])
            if event["type"]=="meta":meta=event["data"]
            if event["type"]=="sources":sources=event["data"]
            if event["type"]=="token":answer+=event["data"]
            if event["type"]=="done":complete=True
    assert complete,"Response stream was incomplete"
    print(f"  Answer in {time.monotonic()-started:.1f}s: {answer}",flush=True)
    return answer,sources,meta

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--base-url",default="http://localhost:8000")
    parser.add_argument("--no-generation",action="store_true")
    args=parser.parse_args()
    env=local_settings()
    admin=login(args.base_url,env["BOOTSTRAP_ADMIN_EMAIL"],env["BOOTSTRAP_ADMIN_PASSWORD"])
    suffix=uuid4().hex[:10]
    created=[]
    clients=[admin]
    try:
        assert checked(admin.get("/health"))["status"]=="healthy"
        initial=checked(admin.get("/workspaces"))
        baseline={w["id"]:checked(admin.get(f"/workspaces/{w['id']}/documents")) for w in initial}
        a=checked(admin.post("/workspaces",json={"name":"Smoke A "+suffix}),201)["id"]
        b=checked(admin.post("/workspaces",json={"name":"Smoke B "+suffix}),201)["id"]
        created=[a,b]
        password=secrets.token_urlsafe(24)
        reader=checked(admin.post(f"/workspaces/{a}/users",json={"email":f"reader-{suffix}@example.test","name":"Smoke reader","password":password,"role":"reader"}),201)
        outsider=checked(admin.post(f"/workspaces/{b}/users",json={"email":f"outsider-{suffix}@example.test","name":"Smoke outsider","password":password,"role":"editor"}),201)
        rc=login(args.base_url,reader["email"],password);oc=login(args.base_url,outsider["email"],password);clients.extend([rc,oc])
        assert oc.get(f"/workspaces/{a}/documents").status_code==403
        assert rc.post(f"/workspaces/{a}/documents",files={"file":("denied.pdf",fixture_pdf(),"application/pdf")}).status_code==403
        assert rc.get(f"/workspaces/{a}/overview").status_code==403
        assert admin.patch(f"/workspaces/{a}/members/{checked(admin.get('/auth/me'))['user']['id']}",json={"role":"reader"}).status_code==409
        print("PASS: authentication, workspace separation, reader restrictions and last-admin protection",flush=True)
        file=fixture_pdf()
        uploaded=checked(admin.post(f"/workspaces/{a}/documents",files={"file":("cedar.pdf",file,"application/pdf")}),202)
        doc=uploaded["id"]
        wait_job(admin,a,uploaded["job_id"])
        assert checked(admin.get(f"/workspaces/{a}/documents"))[0]["chunk_count"]>0
        assert admin.post(f"/workspaces/{a}/documents",files={"file":("cedar.pdf",file,"application/pdf")}).status_code==409
        assert checked(rc.get(f"/documents/{doc}/versions"))[0]["original_available"]
        assert rc.get(f"/documents/{doc}/file").content==file
        assert oc.get(f"/documents/{doc}/file").status_code==404
        assert oc.get(f"/documents/{doc}/versions").status_code==404
        assert rc.delete(f"/documents/{doc}").status_code==403
        print("PASS: queued ingestion, original PDF, version metadata, duplicate handling and download isolation",flush=True)
        no_csrf=httpx.Client(base_url=args.base_url,cookies=admin.cookies)
        assert no_csrf.delete(f"/documents/{doc}").status_code==403
        no_csrf.close()
        assert admin.delete(f"/documents/{doc}",headers={"Origin":"https://attacker.invalid"}).status_code==403
        print("PASS: CSRF and untrusted-origin rejection",flush=True)
        for method in ["vector","hybrid"]:
            found=checked(admin.post(f"/workspaces/{a}/search",json={"question":"Project Cedar approval code","method":method}))
            assert any(s["document_id"]==doc and s["page"]==1 for s in found["sources"])
        print("PASS: permission-filtered vector and hybrid retrieval",flush=True)
        if not args.no_generation:
            request_id=str(uuid4())
            answer,sources,meta=ask(admin,a,"What is the approval code for Project Cedar?",documents=[doc],request_id=request_id)
            assert "CEDAR-7421" in answer
            assert any(s["document_id"]==doc and s["page"]==1 and s["excerpt"] for s in sources)
            replayed,_,_=ask(admin,a,"What is the approval code for Project Cedar?",meta["conversation_id"],[doc],request_id=request_id)
            assert replayed==answer
            assert len(checked(admin.get("/conversations/"+meta["conversation_id"]))["messages"])==2
            assert oc.get("/conversations/"+meta["conversation_id"]).status_code==404
            assert rc.get("/conversations/"+meta["conversation_id"]).status_code==404
            follow,_,_=ask(admin,a,"Who coordinates that project?",meta["conversation_id"],[doc])
            assert "Mira Shah" in follow
            saved=checked(admin.get("/conversations/"+meta["conversation_id"]))
            assert len(saved["messages"])==4
            assert saved["messages"][-1]["status"]=="complete"
            checked(admin.post("/messages/"+meta["message_id"]+"/feedback",json={"rating":-1}))
            assert rc.post("/messages/"+meta["message_id"]+"/feedback",json={"rating":1}).status_code==404
            assert checked(admin.get(f"/workspaces/{a}/overview"))["negative_feedback"]==1
            _,_,reader_meta=ask(rc,a,"What is the approval code for Project Cedar?",documents=[doc])
            checked(rc.post("/messages/"+reader_meta["message_id"]+"/feedback",json={"rating":-1}))
            assert admin.get("/conversations/"+reader_meta["conversation_id"]).status_code==404
            assert checked(admin.get(f"/workspaces/{a}/overview"))["negative_feedback"]==2
            print("PASS: live streamed generation, citations, private durable history, follow-up and feedback",flush=True)
        updated=checked(admin.post(f"/workspaces/{a}/documents/{doc}/versions",files={"file":("cedar.pdf",fixture_pdf("CEDAR-NEW-19"),"application/pdf")}),202)
        wait_job(admin,a,updated["job_id"])
        versions=checked(admin.get(f"/documents/{doc}/versions"))
        assert len(versions)==2 and versions[0]["version"]==2
        assert checked(admin.get(f"/workspaces/{a}/documents"))[0]["version"]==2
        assert admin.post(f"/workspaces/{a}/documents/{doc}/versions",files={"file":("cedar.pdf",fixture_pdf("CEDAR-NEW-19"),"application/pdf")}).status_code==409
        found=checked(admin.post(f"/workspaces/{a}/search",json={"question":"approval code"}))["sources"]
        assert any("CEDAR-NEW-19" in s["excerpt"] for s in found)
        assert all("CEDAR-7421" not in s["excerpt"] for s in found)
        checked(admin.delete(f"/documents/{doc}"))
        assert checked(admin.post(f"/workspaces/{a}/search",json={"question":"Project Cedar"}))["sources"]==[]
        assert admin.get(f"/documents/{doc}/file").status_code==404
        checked(admin.post(f"/documents/{doc}/restore"))
        assert checked(admin.get(f"/workspaces/{a}/documents"))[0]["id"]==doc
        print("PASS: atomic replacement versions, old-version exclusion, trash and restore",flush=True)
        blank=checked(admin.post(f"/workspaces/{a}/documents",files={"file":("blank.pdf",fixture_pdf(blank=True),"application/pdf")}),202)
        failed=wait_job(admin,a,blank["job_id"],"failed")
        assert "OCR" in failed["error"]
        checked(admin.post(f"/jobs/{blank['job_id']}/retry"))
        wait_job(admin,a,blank["job_id"],"failed")
        print("PASS: failed job state, readable error and explicit retry",flush=True)
        assert checked(admin.get(f"/workspaces/{a}/audit"))
        metrics=admin.get("/metrics",headers={"Authorization":"Bearer "+env["METRICS_TOKEN"]})
        assert metrics.status_code==200 and "rag_http_requests_total" in metrics.text
        assert httpx.get(args.base_url+"/metrics").status_code==401
        for w in initial:
            after=checked(admin.get(f"/workspaces/{w['id']}/documents"))
            assert after==baseline[w["id"]],"Pre-existing workspace documents changed"
        print("PASS: audit events, protected metrics and pre-existing document preservation",flush=True)
        # Exercise actual RLS through the restricted role, bypassing the API.
        import psycopg
        with psycopg.connect(f"postgresql://rag_app:{env['APP_DB_PASSWORD']}@127.0.0.1:5432/rag_db",connect_timeout=5) as conn:
            conn.execute("SELECT set_config('app.user_id',%s,true)",(outsider["id"],))
            assert conn.execute("SELECT count(*) FROM rag_chunks WHERE document_id=%s",(doc,)).fetchone()[0]==0
            conn.execute("SELECT set_config('app.user_id',%s,true)",(reader["id"],))
            assert conn.execute("UPDATE rag_documents SET name='forbidden.pdf' WHERE id=%s",(doc,)).rowcount==0
        print("PASS: database row-level isolation and reader write denial",flush=True)
        print("ALL ENTERPRISE ACCEPTANCE CHECKS PASSED",flush=True)
    finally:
        # Retain isolated test records for inspection; exclude their documents from retrieval.
        for workspace in created:
            try:
                for doc in checked(admin.get(f"/workspaces/{workspace}/documents")):
                    admin.delete(f"/documents/{doc['id']}")
            except Exception:
                print("Cleanup warning: inspect isolated smoke workspace",flush=True)
        for client in clients:client.close()

if __name__=="__main__":main()
