"""Verify crashed-worker lease recovery against an isolated test document."""
from pathlib import Path
import subprocess
import sys
from uuid import uuid4
import psycopg
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from test_support import local_settings,fixture_pdf
from smoke_test import login,checked,wait_job
env=local_settings()
client=login("http://localhost:8000",env["BOOTSTRAP_ADMIN_EMAIL"],env["BOOTSTRAP_ADMIN_PASSWORD"])
workspace=checked(client.post("/workspaces",json={"name":"Recovery test "+uuid4().hex[:8]}),201)["id"]
docker=["docker","--config",str(ROOT/"backend"),"compose"]
document=None
try:
    subprocess.run(docker+["stop","worker"],check=True)
    uploaded=checked(client.post(f"/workspaces/{workspace}/documents",files={"file":("recovery.pdf",fixture_pdf(),"application/pdf")}),202)
    document=uploaded["id"]
    with psycopg.connect("postgresql://rag_user:securepassword@127.0.0.1:5432/rag_db",connect_timeout=5) as conn:
        conn.execute("""UPDATE rag_jobs SET status='processing',attempts=1,locked_by='simulated-crash',
            lease_until=now()-interval '2 minutes' WHERE id=%s""",(uploaded["job_id"],))
        conn.execute("UPDATE rag_versions SET status='processing' WHERE id=%s",(uploaded["version_id"],))
    subprocess.run(docker+["start","worker"],check=True)
    job=wait_job(client,workspace,uploaded["job_id"])
    assert job["attempts"]==2
    versions=checked(client.get(f"/documents/{document}/versions"))
    assert versions[0]["status"]=="ready" and versions[0]["chunk_count"]>0
    print("CRASHED-WORKER RECOVERY PASSED: expired lease reclaimed and document published once",flush=True)
finally:
    subprocess.run(docker+["start","worker"],check=True)
    if document:client.delete("/documents/"+document)
    client.close()
