"""Probe immutable production images locally, including a two-worker read-only API."""
import json
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4
import httpx
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from test_support import local_settings
env=local_settings()
docker=["docker","--config",str(ROOT/"backend")]
temporary=ROOT/"tmp"/("runtime-"+uuid4().hex+".env")
temporary.parent.mkdir(exist_ok=True)
values={"RAW_DATABASE_URL":f"postgresql://rag_app:{env['APP_DB_PASSWORD']}@db:5432/rag_db",
        "AUTH_SECRET":env["AUTH_SECRET"],"METRICS_TOKEN":env["METRICS_TOKEN"],
        "OLLAMA_BASE_URL":"http://host.docker.internal:11434","STORAGE_DIR":"/data"}
temporary.write_text("\n".join(f"{k}={v}" for k,v in values.items())+"\n",encoding="utf-8")
containers=[]
def start(arguments):
    result=subprocess.run(docker+["run","--rm","-d"]+arguments,capture_output=True,text=True,check=True)
    identity=result.stdout.strip();containers.append(identity);return identity
def wait(url):
    deadline=time.monotonic()+45
    while time.monotonic()<deadline:
        try:
            response=httpx.get(url,timeout=3)
            if response.status_code==200:return response
        except httpx.HTTPError:pass
        time.sleep(1)
    raise RuntimeError("Runtime endpoint did not become ready: "+url)
try:
    web=start(["--read-only","--tmpfs","/tmp","-p","127.0.0.1:3001:3000","rag-web-production"])
    response=wait("http://127.0.0.1:3001")
    assert "Enterprise RAG" in response.text
    who=subprocess.run(docker+["exec",web,"id"],capture_output=True,text=True,check=True).stdout.strip()
    print("PASS: standalone frontend HTTP 200;",who,flush=True)
    backend=start(["--read-only","--tmpfs","/tmp","--network","rag_default","--env-file",str(temporary),
                   "-p","127.0.0.1:8001:8000","rag-api-production","uvicorn","main:app","--host","0.0.0.0","--port","8000","--workers","2"])
    assert wait("http://127.0.0.1:8001/health").json()["status"]=="healthy"
    with httpx.Client(base_url="http://127.0.0.1:8001",timeout=10) as client:
        response=client.post("/auth/login",json={"email":env["BOOTSTRAP_ADMIN_EMAIL"],"password":env["BOOTSTRAP_ADMIN_PASSWORD"]})
        response.raise_for_status()
        assert client.get("/auth/me").status_code==200
    who=subprocess.run(docker+["exec",backend,"id"],capture_output=True,text=True,check=True).stdout.strip()
    print("PASS: read-only two-worker production API health and session login;",who,flush=True)
    print("PRODUCTION IMAGE RUNTIME CHECKS PASSED",flush=True)
finally:
    for identity in reversed(containers):
        subprocess.run(docker+["stop","-t","5",identity],capture_output=True)
    temporary.unlink(missing_ok=True)
