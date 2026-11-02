import hmac
import os
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Request
from fastapi.responses import PlainTextResponse
from db import connect
from security import User,current_user,require_role

router=APIRouter()

@router.get("/workspaces/{workspace}/overview")
def overview(workspace:UUID,user:User=Depends(current_user)):
    with connect(user.id) as conn:
        require_role(conn,workspace,("admin",))
        counts=conn.execute("""SELECT
            (SELECT count(*) FROM rag_documents WHERE workspace_id=%s AND deleted_at IS NULL) AS documents,
            (SELECT count(*) FROM rag_memberships WHERE workspace_id=%s) AS members,
            (SELECT count(*) FROM rag_jobs WHERE workspace_id=%s AND status='failed') AS failed_jobs,
            (SELECT count(*) FROM rag_feedback WHERE workspace_id=%s AND rating=-1) AS negative_feedback
        """,(workspace,workspace,workspace,workspace)).fetchone()
        quality=conn.execute("""SELECT count(*) AS requests,
            count(*) FILTER(WHERE outcome='complete') AS successful,
            round(avg(duration_ms)) AS average_ms,
            percentile_cont(0.95) WITHIN GROUP(ORDER BY duration_ms) AS p95_ms,
            round(avg(first_token_ms)) AS average_first_token_ms,
            round(avg(retrieval_ms)) AS average_retrieval_ms
            FROM rag_query_runs WHERE workspace_id=%s AND created_at>now()-interval '24 hours'""",(workspace,)).fetchone()
        feedback=conn.execute("""SELECT f.rating,f.note,f.updated_at FROM rag_feedback f
            WHERE f.workspace_id=%s ORDER BY f.updated_at DESC LIMIT 20""",(workspace,)).fetchall()
        return {**counts,"last_24_hours":quality,"feedback":feedback}

@router.get("/workspaces/{workspace}/audit")
def audit_log(workspace:UUID,user:User=Depends(current_user)):
    with connect(user.id) as conn:
        require_role(conn,workspace,("admin",))
        return conn.execute("SELECT action,target,user_id,created_at FROM rag_audit WHERE workspace_id=%s ORDER BY id DESC LIMIT 100",(workspace,)).fetchall()

@router.get("/metrics",response_class=PlainTextResponse)
def metrics(request:Request):
    expected=os.getenv("METRICS_TOKEN","")
    if not expected or not hmac.compare_digest(request.headers.get("authorization",""),"Bearer "+expected):
        raise HTTPException(401,"A metrics token is required.")
    with connect() as conn:
        rows=conn.execute("SELECT * FROM rag_http_metrics").fetchall()
        active=conn.execute("SELECT count(*) AS n FROM rag_model_leases WHERE expires_at>now()").fetchone()["n"]
        aggregates=conn.execute("SELECT * FROM rag_metrics()").fetchone()
    lines=["# TYPE rag_http_requests_total counter","# TYPE rag_http_duration_seconds_sum counter"]
    for row in rows:
        label=f'method="{row["method"]}",route="{row["route"]}",status="{row["status"]}"'
        lines.append(f'rag_http_requests_total{{{label}}} {row["requests"]}')
        lines.append(f'rag_http_duration_seconds_sum{{{label}}} {row["duration_ms"]/1000}')
    lines.extend(["# TYPE rag_model_active gauge",f"rag_model_active {active}"])
    for name,key,kind in [
        ("rag_ingestion_pending_jobs","queued_jobs","gauge"),
        ("rag_ingestion_failed_jobs","failed_jobs","gauge"),
        ("rag_worker_alive","worker_alive","gauge"),
        ("rag_queries_total","query_total","counter"),
        ("rag_query_failures_total","query_failed","counter"),
        ("rag_query_cancellations_total","query_cancelled","counter"),
        ("rag_query_duration_seconds_sum","query_seconds","counter"),
        ("rag_first_token_seconds_sum","first_token_seconds","counter"),
        ("rag_first_token_seconds_count","first_token_count","counter"),
    ]:
        lines.extend([f"# TYPE {name} {kind}",f"{name} {aggregates[key]}"])
    return "\n".join(lines)+"\n"
