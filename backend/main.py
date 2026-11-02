import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from uuid import UUID,uuid4
import httpx
from fastapi import FastAPI,Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from db import connect
from telemetry import configure,tracer,trace_id
from opentelemetry.propagate import inject
configure('rag-api')
from routers import accounts,documents,conversations,query,operations,identity,sso
from starlette.middleware.sessions import SessionMiddleware
from services import CHAT_MODEL,EMBEDDING_MODEL,OLLAMA_URL
from security import SECRET
from app_version import VERSION

log=logging.getLogger("rag.http")
logging.basicConfig(level=logging.INFO,format="%(message)s")

class SafeAccessLog(logging.Filter):
    def filter(self,record):
        if isinstance(record.args,tuple) and len(record.args)==5:
            client,method,target,version,status=record.args
            record.args=(client,method,str(target).split('?',1)[0],version,status)
        return True
logging.getLogger('uvicorn.access').addFilter(SafeAccessLog())

@asynccontextmanager
async def lifespan(app):
    if len(SECRET)<32:
        raise RuntimeError("AUTH_SECRET must contain at least 32 characters. Run tools/setup_env.py.")
    with connect() as conn:
        if not conn.execute("SELECT 1 FROM rag_schema_migrations WHERE name='001_application.sql'").fetchone():
            raise RuntimeError("Run migrations before starting the API.")
        role=conn.execute("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone()
        if role["rolsuper"] or role["rolbypassrls"]:
            raise RuntimeError("API must use the restricted rag_app database role.")
        if conn.execute("SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'rag_%' AND tableowner=current_user LIMIT 1").fetchone():
            raise RuntimeError("The API database role must not own application tables.")
    yield

app=FastAPI(title="Enterprise RAG API",version=VERSION,lifespan=lifespan)
app.add_middleware(SessionMiddleware,secret_key=SECRET,session_cookie='rag_oidc_state',max_age=600,https_only=os.getenv('COOKIE_SECURE','false').lower()=='true',same_site='lax')
app.add_middleware(CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS","http://localhost:3000,http://127.0.0.1:3000").split(","),
    allow_credentials=True,allow_methods=["GET","POST","PUT","PATCH","DELETE","OPTIONS"],
    allow_headers=["Content-Type","X-CSRF-Token","X-Request-ID"],expose_headers=["X-Request-ID"])
for router in [accounts.router,documents.router,conversations.router,query.router,operations.router,identity.router,sso.router]:
    app.include_router(router)

def record_http(method,route,status,duration):
    with connect() as conn:
        conn.execute("""INSERT INTO rag_http_metrics(method,route,status,requests,duration_ms) VALUES(%s,%s,%s,1,%s)
            ON CONFLICT(method,route,status) DO UPDATE SET requests=rag_http_metrics.requests+1,
            duration_ms=rag_http_metrics.duration_ms+EXCLUDED.duration_ms""",(method,route,status,duration))

@app.middleware("http")
async def observe(request:Request,call_next):
    started=time.monotonic()
    try:
        request_id=str(UUID(request.headers.get("x-request-id","")))
    except ValueError:
        request_id=str(uuid4())
    with tracer.start_as_current_span('http.request') as span:
        span.set_attribute('request.id',request_id)
        span.set_attribute('http.request.method',request.method)
        request.state.trace_context={}
        inject(request.state.trace_context)
        response=await call_next(request)
        span.set_attribute('http.route',getattr(request.scope.get('route'),'path','unmatched'))
        span.set_attribute('http.response.status_code',response.status_code)
        response.headers['X-Trace-ID']=trace_id()
    response.headers["X-Request-ID"]=request_id
    response.headers["X-Content-Type-Options"]="nosniff"
    response.headers["Referrer-Policy"]="same-origin"
    response.headers["Cache-Control"]="no-store"
    route=getattr(request.scope.get("route"),"path","unmatched")
    duration=round((time.monotonic()-started)*1000,2)
    log.info(json.dumps({"event":"http_response","request_id":request_id,"method":request.method,
                         "route":route,"status":response.status_code,"headers_ms":duration}))
    try:
        await asyncio.to_thread(record_http,request.method if request.method in {"GET","POST","PATCH","DELETE","OPTIONS","HEAD"} else "OTHER",route,response.status_code,duration)
    except Exception:
        log.exception("http_metric_recording_failed")
    return response

@app.get("/health/live")
def live():
    return {"status":"alive","version":VERSION}

@app.get("/health")
@app.get("/health/ready")
async def health():
    database=False
    worker=False
    try:
        with connect() as conn:
            database=bool(conn.execute("SELECT 1 FROM rag_schema_migrations").fetchone())
            worker=bool(conn.execute("SELECT 1 FROM rag_workers WHERE heartbeat_at>now()-interval '30 seconds' LIMIT 1").fetchone())
    except Exception:
        pass
    names=[]
    loaded=[]
    ollama=False
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            result=await client.get(f"{OLLAMA_URL}/api/tags")
            result.raise_for_status()
            names=[m["name"] for m in result.json()["models"]]
            ollama=True
            running=await client.get(f"{OLLAMA_URL}/api/ps")
            running.raise_for_status()
            loaded=[m["name"] for m in running.json()["models"]]
    except (httpx.HTTPError,KeyError,ValueError):
        pass
    installed={name:(name if ":" in name else name+":latest") in names for name in [CHAT_MODEL,EMBEDDING_MODEL]}
    warm=(CHAT_MODEL if ":" in CHAT_MODEL else CHAT_MODEL+":latest") in loaded
    ready=database and worker and ollama and all(installed.values())
    if os.getenv("REQUIRE_WARM_MODEL","false").lower()=="true":
        ready=ready and warm
    return JSONResponse({"status":"healthy" if ready else "degraded","database":"ready" if database else "unavailable",
        "worker":"ready" if worker else "unavailable","ollama":"reachable" if ollama else "unavailable",
        "models_installed":installed,"generation_model_loaded":warm},status_code=200 if ready else 503)
