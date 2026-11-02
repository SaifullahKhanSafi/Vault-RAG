from pathlib import Path
from uuid import UUID,uuid4
from fastapi import APIRouter,Depends,File,HTTPException,UploadFile,Request
from fastapi.responses import FileResponse
from db import connect,audit
from security import User,current_user,require_role,rate_limit
from services import EMBEDDING_MODEL
from storage import save_upload,storage_path
from pydantic import BaseModel,Field
from psycopg.types.json import Jsonb
from opentelemetry.propagate import inject

router=APIRouter()

@router.get('/documents/{document}/extraction')
def extraction(document:UUID,version:UUID|None=None,user:User=Depends(current_user)):
    with connect(user.id) as conn:
        doc=document_row(conn,document)
        if doc['deleted_at']:raise HTTPException(404,'Document was deleted.')
        selected=version or doc['active_version']
        rows=conn.execute('SELECT page,method,text_content,tables FROM rag_extracted_pages WHERE document_id=%s AND version_id=%s ORDER BY page',(document,selected)).fetchall()
        return {'version_id':str(selected) if selected else None,'pages':rows,
                'available':bool(rows),'note':'Extraction diagnostics exist for versions indexed after migration 007.'}

class DocumentPermissions(BaseModel):
    restricted:bool
    user_ids:list[UUID]=Field(default_factory=list,max_length=200)

@router.get('/documents/{document}/permissions')
def permissions(document:UUID,user:User=Depends(current_user)):
    with connect(user.id) as conn:
        doc=document_row(conn,document)
        require_role(conn,doc['workspace_id'],('admin',))
        rows=conn.execute('SELECT user_id FROM rag_document_access WHERE document_id=%s',(document,)).fetchall()
        return {'restricted':doc['restricted'],'user_ids':[str(r['user_id']) for r in rows]}

@router.put('/documents/{document}/permissions')
def change_permissions(document:UUID,body:DocumentPermissions,user:User=Depends(current_user)):
    with connect(user.id) as conn:
        doc=document_row(conn,document)
        require_role(conn,doc['workspace_id'],('admin',))
        ids=list({str(x) for x in body.user_ids})
        count=conn.execute('SELECT count(*) AS n FROM rag_memberships WHERE workspace_id=%s AND user_id=ANY(%s::uuid[])',(doc['workspace_id'],ids)).fetchone()['n']
        if count!=len(ids):raise HTTPException(422,'Select only current workspace members.')
        conn.execute('UPDATE rag_documents SET restricted=%s WHERE id=%s',(body.restricted,document))
        conn.execute('DELETE FROM rag_document_access WHERE document_id=%s',(document,))
        for target in ids:conn.execute('INSERT INTO rag_document_access VALUES(%s,%s)',(document,target))
        audit(conn,user.id,doc['workspace_id'],'document.permissions_changed',document)
    return {'message':'Document access updated. Administrators and the uploader retain access.'}

def document_row(conn,document):
    row=conn.execute("SELECT * FROM rag_documents WHERE id=%s",(document,)).fetchone()
    if not row:
        raise HTTPException(404,"Document not found.")
    return row

def queue_upload(workspace,file,user,document=None,trace_context=None):
    rate_limit("upload:"+user.id,10,60)
    name=Path((file.filename or "").replace("\\","/")).name
    if not name.lower().endswith(".pdf") or len(name)>255:
        raise HTTPException(400,"Choose a PDF with a filename of at most 255 characters.")
    # Check permissions before accepting or storing any bytes.
    with connect(user.id) as conn:
        require_role(conn,workspace,("admin","editor"))
        count=conn.execute("SELECT count(*) AS n FROM rag_jobs WHERE workspace_id=%s AND status IN ('queued','processing')",(workspace,)).fetchone()["n"]
        if count>=50:
            raise HTTPException(429,"The ingestion queue is full. Retry later.")
    key,checksum,size=save_upload(file)
    try:
        with connect(user.id) as conn:
            require_role(conn,workspace,("admin","editor"))
            conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",("queue:"+str(workspace),))
            queued=conn.execute("SELECT count(*) AS n FROM rag_jobs WHERE workspace_id=%s AND status IN ('queued','processing')",(workspace,)).fetchone()["n"]
            if queued>=50:
                raise HTTPException(429,"The ingestion queue is full. Retry later.")
            conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",(str(workspace)+":"+name,))
            if document:
                doc=document_row(conn,document)
                if str(doc["workspace_id"])!=str(workspace) or doc["deleted_at"]:
                    raise HTTPException(404,"Document not found.")
                doc_id=str(doc["id"])
            else:
                if conn.execute("SELECT 1 FROM rag_documents WHERE workspace_id=%s AND name=%s AND deleted_at IS NULL",(workspace,name)).fetchone():
                    raise HTTPException(409,"This filename already exists. Use Upload new version or delete the old document.")
                doc_id=str(uuid4())
                conn.execute("INSERT INTO rag_documents(id,workspace_id,name,created_by) VALUES(%s,%s,%s,%s)",(doc_id,workspace,name,user.id))
            conn.execute("SELECT id FROM rag_documents WHERE id=%s FOR UPDATE",(doc_id,))
            if conn.execute("SELECT 1 FROM rag_versions WHERE document_id=%s AND checksum=%s",(doc_id,checksum)).fetchone():
                raise HTTPException(409,"This exact document version has already been uploaded.")
            number=conn.execute("SELECT COALESCE(max(version),0)+1 AS n FROM rag_versions WHERE document_id=%s",(doc_id,)).fetchone()["n"]
            version,job=str(uuid4()),str(uuid4())
            conn.execute("""INSERT INTO rag_versions(id,document_id,workspace_id,version,checksum,storage_key,embedding_model,size_bytes)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",(version,doc_id,workspace,number,checksum,key,EMBEDDING_MODEL,size))
            context=dict(trace_context or {} )
            if not context:inject(context)
            conn.execute("INSERT INTO rag_jobs(id,workspace_id,version_id,trace_context) VALUES(%s,%s,%s,%s)",(job,workspace,version,Jsonb(context)))
            audit(conn,user.id,workspace,"document.uploaded",doc_id)
        return {"id":doc_id,"version_id":version,"job_id":job,"status":"queued","name":name}
    except BaseException:
        storage_path(key).unlink(missing_ok=True)
        raise

@router.post("/workspaces/{workspace}/documents",status_code=202)
def upload_document(workspace:UUID,request:Request,file:UploadFile=File(...),user:User=Depends(current_user)):
    return queue_upload(workspace,file,user,trace_context=getattr(request.state,'trace_context',{}))

@router.post("/workspaces/{workspace}/documents/{document}/versions",status_code=202)
def upload_version(workspace:UUID,document:UUID,request:Request,file:UploadFile=File(...),user:User=Depends(current_user)):
    return queue_upload(workspace,file,user,document,trace_context=getattr(request.state,'trace_context',{}))

@router.get("/workspaces/{workspace}/documents")
def documents(workspace:UUID,deleted:bool=False,user:User=Depends(current_user)):
    with connect(user.id) as conn:
        require_role(conn,workspace)
        return conn.execute("""
            SELECT d.id,d.name,d.restricted,d.deleted_at,d.active_version,v.version,v.chunk_count,v.storage_key IS NOT NULL AS original_available,
            COALESCE(j.status,'ready') AS job_status,j.progress,j.error,
            (SELECT count(*) FROM rag_versions vv WHERE vv.document_id=d.id) AS version_count
            FROM rag_documents d LEFT JOIN rag_versions v ON v.id=d.active_version
            LEFT JOIN LATERAL (
                SELECT jj.status,jj.progress,jj.error FROM rag_jobs jj JOIN rag_versions vv ON vv.id=jj.version_id
                WHERE vv.document_id=d.id ORDER BY jj.created_at DESC LIMIT 1
            ) j ON true WHERE d.workspace_id=%s AND (d.deleted_at IS NOT NULL)=%s ORDER BY d.created_at DESC
        """,(workspace,deleted)).fetchall()

@router.get("/documents/{document}/versions")
def versions(document:UUID,user:User=Depends(current_user)):
    with connect(user.id) as conn:
        document_row(conn,document)
        return conn.execute("""SELECT id,version,status,checksum,chunk_count,size_bytes,created_at,
            storage_key IS NOT NULL AS original_available FROM rag_versions WHERE document_id=%s ORDER BY version DESC""",(document,)).fetchall()

@router.get("/documents/{document}/file")
def original(document:UUID,version:UUID|None=None,user:User=Depends(current_user)):
    with connect(user.id) as conn:
        doc=document_row(conn,document)
        if doc["deleted_at"]:
            raise HTTPException(404,"Document was deleted.")
        record=conn.execute("SELECT * FROM rag_versions WHERE id=%s AND document_id=%s",(version or doc["active_version"],document)).fetchone()
        if not record or not record["storage_key"]:
            raise HTTPException(404,"The original PDF was not retained in the old index. Upload a new version to enable viewing.")
        path=storage_path(record["storage_key"])
        if not path.is_file():
            raise HTTPException(503,"The original PDF is missing from storage. Contact an administrator.")
    return FileResponse(path,media_type="application/pdf",filename=doc["name"],content_disposition_type="inline",
                        headers={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})

@router.delete("/documents/{document}")
def delete_document(document:UUID,user:User=Depends(current_user)):
    with connect(user.id) as conn:
        doc=document_row(conn,document)
        require_role(conn,doc["workspace_id"],("admin","editor"))
        conn.execute("UPDATE rag_documents SET deleted_at=now() WHERE id=%s",(document,))
        conn.execute("""UPDATE rag_jobs SET status='cancelled',updated_at=now() WHERE version_id IN
            (SELECT id FROM rag_versions WHERE document_id=%s) AND status IN ('queued','processing')""",(document,))
        audit(conn,user.id,doc["workspace_id"],"document.deleted",document)
    return {"message":"Document moved to trash. It is excluded from retrieval."}

@router.post("/documents/{document}/restore")
def restore_document(document:UUID,user:User=Depends(current_user)):
    with connect(user.id) as conn:
        doc=document_row(conn,document)
        require_role(conn,doc["workspace_id"],("admin","editor"))
        if conn.execute("SELECT 1 FROM rag_documents WHERE workspace_id=%s AND name=%s AND deleted_at IS NULL AND id<>%s",
                        (doc["workspace_id"],doc["name"],document)).fetchone():
            raise HTTPException(409,"An active document already uses this filename.")
        conn.execute("UPDATE rag_documents SET deleted_at=NULL WHERE id=%s",(document,))
        conn.execute("""UPDATE rag_jobs SET status='queued',attempts=0,progress=0,locked_by=NULL,
            lease_until=NULL,available_at=now(),updated_at=now() WHERE status='cancelled' AND version_id=(
            SELECT id FROM rag_versions WHERE document_id=%s AND status IN ('queued','processing')
            ORDER BY version DESC LIMIT 1)""",(document,))
        conn.execute("""UPDATE rag_versions SET status='queued' WHERE id IN
            (SELECT version_id FROM rag_jobs WHERE status='queued') AND document_id=%s""",(document,))
        audit(conn,user.id,doc["workspace_id"],"document.restored",document)
    return {"message":"Document restored."}

@router.get("/workspaces/{workspace}/jobs")
def jobs(workspace:UUID,user:User=Depends(current_user)):
    with connect(user.id) as conn:
        require_role(conn,workspace)
        return conn.execute("""SELECT j.*,d.name FROM rag_jobs j JOIN rag_versions v ON v.id=j.version_id
            JOIN rag_documents d ON d.id=v.document_id WHERE j.workspace_id=%s ORDER BY j.created_at DESC LIMIT 100""",(workspace,)).fetchall()

@router.post("/jobs/{job}/retry")
def retry_job(job:UUID,user:User=Depends(current_user)):
    with connect(user.id) as conn:
        row=conn.execute("""SELECT j.*,d.deleted_at FROM rag_jobs j JOIN rag_versions v ON v.id=j.version_id
            JOIN rag_documents d ON d.id=v.document_id WHERE j.id=%s FOR UPDATE OF j""",(job,)).fetchone()
        if not row:
            raise HTTPException(404,"Job not found.")
        require_role(conn,row["workspace_id"],("admin","editor"))
        if row["status"]!="failed" or row["deleted_at"]:
            raise HTTPException(409,"Only a failed job for an active document can be retried.")
        conn.execute("UPDATE rag_jobs SET status='queued',attempts=0,error=NULL,progress=0,available_at=now(),updated_at=now() WHERE id=%s",(job,))
        conn.execute("UPDATE rag_versions SET status='queued' WHERE id=%s",(row["version_id"],))
        audit(conn,user.id,row["workspace_id"],"job.retried",job)
    return {"message":"Job queued for retry."}
