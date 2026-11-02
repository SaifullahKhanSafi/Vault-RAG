"""Durable PostgreSQL queue with leases, retries and atomic index publication."""
import logging
import os
import signal
import threading
import time
from uuid import uuid4,uuid5,NAMESPACE_URL
from pypdf.errors import PdfReadError
from langchain_text_splitters import RecursiveCharacterTextSplitter
from fastapi import HTTPException
from db import connect
from telemetry import configure,tracer
from opentelemetry.propagate import extract
configure('rag-worker')
from security import acquire_model,release_model,renew_model
from services import get_embeddings
from storage import storage_path
from psycopg.types.json import Jsonb
from pdf_extract import extract_pages

log=logging.getLogger("rag.worker")
worker_id=str(uuid4())
stopping=threading.Event()

def heartbeat(job=None,lease=None):
    with connect() as conn:
        conn.execute("""INSERT INTO rag_workers(id) VALUES(%s) ON CONFLICT(id)
            DO UPDATE SET heartbeat_at=now()""",(worker_id,))
        if job:
            conn.execute("""UPDATE rag_jobs SET lease_until=now()+interval '60 seconds',updated_at=now()
                WHERE id=%s AND locked_by=%s AND status='processing'""",(job,worker_id))
    if lease:
        renew_model(lease)

def pulse(stop,job,lease):
    while not stop.wait(5):
        try:
            heartbeat(job,lease)
        except Exception:
            log.exception("worker_heartbeat_failed")

def claim():
    with connect() as conn:
        # Recover work left by a crashed worker; do not retry forever.
        conn.execute("""UPDATE rag_jobs SET status=CASE WHEN attempts>=max_attempts THEN 'failed' ELSE 'queued' END,
            error='Worker lease expired',locked_by=NULL,lease_until=NULL,updated_at=now()
            WHERE status='processing' AND lease_until<now()""")
        conn.execute("""UPDATE rag_versions v SET status='failed' FROM rag_jobs j
            WHERE j.version_id=v.id AND j.status='failed' AND v.status='processing'""")
        return conn.execute("""WITH candidate AS (
            SELECT j.id FROM rag_jobs j JOIN rag_versions v ON v.id=j.version_id
            JOIN rag_documents d ON d.id=v.document_id
            WHERE j.status='queued' AND j.available_at<=now() AND d.deleted_at IS NULL
            ORDER BY j.created_at FOR UPDATE OF j SKIP LOCKED LIMIT 1)
            UPDATE rag_jobs j SET status='processing',progress=0,attempts=j.attempts+1,locked_by=%s,
            lease_until=now()+interval '60 seconds',updated_at=now()
            FROM candidate c WHERE c.id=j.id RETURNING j.*""",(worker_id,)).fetchone()

def process(job):
    with tracer.start_as_current_span('rag.ingestion',context=extract(job.get('trace_context') or {})) as span:
        span.set_attribute('job.id',str(job['id']))
        span.set_attribute('document.version_id',str(job['version_id']))
        return process_job(job)

def process_job(job):
    try:
        lease=acquire_model("ingest:"+str(job["id"]))
    except HTTPException:
        with connect() as conn:
            conn.execute("""UPDATE rag_jobs SET status='queued',attempts=attempts-1,available_at=now()+interval '5 seconds',
                locked_by=NULL,lease_until=NULL WHERE id=%s AND locked_by=%s""",(job["id"],worker_id))
        return
    stop=threading.Event()
    thread=threading.Thread(target=pulse,args=(stop,job["id"],lease),daemon=True)
    thread.start()
    version=None
    try:
        with connect() as conn:
            version=conn.execute("UPDATE rag_versions SET status='processing' WHERE id=%s RETURNING *",(job["version_id"],)).fetchone()
        pages=extract_pages(storage_path(version["storage_key"]))
        size=max(400,min(2000,int(os.getenv('CHUNK_SIZE','1000'))))
        overlap=max(0,min(size//2,int(os.getenv('CHUNK_OVERLAP','200'))))
        chunks=RecursiveCharacterTextSplitter(chunk_size=size,chunk_overlap=overlap).split_documents(pages)
        chunks=[c for c in chunks if c.page_content.strip()]
        if not chunks:
            raise ValueError("No readable text found, including OCR. Check that the PDF contains legible text.")
        indexed=[]
        for offset in range(0,len(chunks),8):
            batch=chunks[offset:offset+8]
            vectors=get_embeddings().embed_documents([c.page_content for c in batch])
            for position,(chunk,vector) in enumerate(zip(batch,vectors)):
                if len(vector)!=768:
                    raise ValueError("Embedding dimension mismatch. This index requires a 768-dimension embedding model.")
                indexed.append((str(uuid5(NAMESPACE_URL,str(version["id"])+":"+str(offset+position))),
                    str(version["workspace_id"]),str(version["document_id"]),str(version["id"]),
                    chunk.metadata["page"],chunk.metadata["page_label"],chunk.page_content,str(vector)))
            with connect() as conn:
                active=conn.execute("""UPDATE rag_jobs SET progress=%s,updated_at=now()
                    WHERE id=%s AND locked_by=%s AND status='processing' RETURNING id""",
                    (min(95,int(100*(offset+len(batch))/len(chunks))),job["id"],worker_id)).fetchone()
                if not active:
                    return
        with connect() as conn:
            valid=conn.execute("""SELECT j.id FROM rag_jobs j JOIN rag_versions v ON v.id=j.version_id
                JOIN rag_documents d ON d.id=v.document_id WHERE j.id=%s AND j.locked_by=%s
                AND j.status='processing' AND d.deleted_at IS NULL FOR UPDATE OF j,d""",(job["id"],worker_id)).fetchone()
            if not valid:
                return
            conn.execute("DELETE FROM rag_chunks WHERE version_id=%s",(version["id"],))
            conn.execute('DELETE FROM rag_extracted_pages WHERE version_id=%s',(version['id'],))
            with conn.cursor() as cur:
                cur.executemany('INSERT INTO rag_extracted_pages(version_id,document_id,workspace_id,page,method,text_content,tables) VALUES(%s,%s,%s,%s,%s,%s,%s)',
                    [(version['id'],version['document_id'],version['workspace_id'],p.metadata['page'],
                      p.metadata['extraction_method'],p.metadata['raw_text'],Jsonb(p.metadata['tables'])) for p in pages])
                cur.executemany("""INSERT INTO rag_chunks(id,workspace_id,document_id,version_id,page,page_label,content,embedding)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s::vector)""",indexed)
            conn.execute("UPDATE rag_versions SET status='ready',chunk_count=%s WHERE id=%s",(len(indexed),version["id"]))
            conn.execute("""UPDATE rag_documents d SET active_version=%s WHERE id=%s AND
                (active_version IS NULL OR (SELECT version FROM rag_versions WHERE id=d.active_version)<=%s)""",
                (version["id"],version["document_id"],version["version"]))
            conn.execute("""UPDATE rag_jobs SET status='ready',progress=100,error=NULL,lease_until=NULL,
                locked_by=NULL,updated_at=now() WHERE id=%s""",(job["id"],))
        log.info("ingestion_complete",extra={"job_id":str(job["id"]),"chunks":len(indexed)})
    except Exception as exc:
        permanent=isinstance(exc,(ValueError,PdfReadError))
        message=str(exc) if permanent else "Indexing service unavailable. Automatic retry scheduled; inspect worker logs."
        with connect() as conn:
            changed=conn.execute("""UPDATE rag_jobs SET status=CASE WHEN %s OR attempts>=max_attempts THEN 'failed' ELSE 'queued' END,
                error=%s,locked_by=NULL,lease_until=NULL,available_at=now()+interval '15 seconds',updated_at=now()
                WHERE id=%s AND locked_by=%s AND status='processing' RETURNING status""",(permanent,message,job["id"],worker_id)).fetchone()
            if version and changed:
                conn.execute("UPDATE rag_versions SET status=%s WHERE id=%s",("failed" if changed["status"]=="failed" else "queued",version["id"]))
        log.exception("ingestion_failed",extra={"job_id":str(job["id"])})
    finally:
        stop.set()
        thread.join(timeout=6)
        release_model(lease)

def main():
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    for sig in (signal.SIGTERM,signal.SIGINT):
        signal.signal(sig,lambda *_: stopping.set())
    while not stopping.is_set():
        try:
            heartbeat()
            job=claim()
            if job:
                process(job)
            else:
                stopping.wait(2)
        except Exception:
            log.exception("worker_loop_failed")
            stopping.wait(5)
    with connect() as conn:
        conn.execute("DELETE FROM rag_workers WHERE id=%s",(worker_id,))

if __name__=="__main__":
    main()
