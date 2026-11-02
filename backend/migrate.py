"""Transactional, checksum-checked schema migrations and one-time legacy import."""
import hashlib
import os
from pathlib import Path
from uuid import uuid4,uuid5,NAMESPACE_URL
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from security import password_hash

def migrate():
    uri=os.environ["MIGRATION_DATABASE_URL"]
    with psycopg.connect(uri,row_factory=dict_row) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(723490)")
        for role,key in [("rag_app","APP_DB_PASSWORD"),("rag_worker","WORKER_DB_PASSWORD")]:
            if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s",(role,)).fetchone():
                conn.execute(sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS").format(sql.Identifier(role)))
            conn.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(sql.Identifier(role),sql.Literal(os.environ[key])))
        conn.execute("CREATE TABLE IF NOT EXISTS rag_schema_migrations(name text PRIMARY KEY,checksum text NOT NULL,applied_at timestamptz DEFAULT now())")
        for path in sorted((Path(__file__).parent/"migrations").glob("*.sql")):
            content=path.read_text(encoding="utf-8")
            checksum=hashlib.sha256(content.encode()).hexdigest()
            previous=conn.execute("SELECT checksum FROM rag_schema_migrations WHERE name=%s",(path.name,)).fetchone()
            if previous:
                if previous["checksum"]!=checksum:
                    raise RuntimeError("Applied migration changed: "+path.name)
                continue
            conn.execute(content,prepare=False)
            conn.execute("INSERT INTO rag_schema_migrations(name,checksum) VALUES(%s,%s)",(path.name,checksum))
        conn.execute("GRANT SELECT ON rag_schema_migrations TO rag_app,rag_worker")
        if not conn.execute("SELECT 1 FROM rag_users LIMIT 1").fetchone():
            password=os.environ["BOOTSTRAP_ADMIN_PASSWORD"]
            if len(password)<12:
                raise RuntimeError("Bootstrap password must contain at least 12 characters")
            user,workspace=str(uuid4()),str(uuid4())
            conn.execute("INSERT INTO rag_users(id,email,name,password_hash,email_verified) VALUES(%s,%s,'Administrator',%s,true)",
                         (user,os.environ.get("BOOTSTRAP_ADMIN_EMAIL","admin@localhost").lower(),password_hash(password)))
            conn.execute("INSERT INTO rag_workspaces(id,name,created_by) VALUES(%s,'Initial workspace',%s)",(workspace,user))
            conn.execute("INSERT INTO rag_memberships VALUES(%s,%s,'admin')",(workspace,user))
            legacy=conn.execute("SELECT to_regclass('public.langchain_pg_embedding') AS t").fetchone()["t"]
            if legacy:
                rows=conn.execute("""
                    SELECT e.id,e.document,e.embedding::text,e.cmetadata
                    FROM langchain_pg_embedding e JOIN langchain_pg_collection c ON c.uuid=e.collection_id
                    WHERE c.name=%s AND e.cmetadata->>'source_file' IS NOT NULL
                """,(os.getenv("COLLECTION_NAME","enterprise_docs_v2"),)).fetchall()
                names={}
                for row in rows:
                    name=row["cmetadata"]["source_file"]
                    if name not in names:
                        doc,version=str(uuid4()),str(uuid4())
                        conn.execute("INSERT INTO rag_documents(id,workspace_id,name,created_by) VALUES(%s,%s,%s,%s)",(doc,workspace,name,user))
                        conn.execute("""INSERT INTO rag_versions(id,document_id,workspace_id,version,embedding_model,status)
                            VALUES(%s,%s,%s,1,%s,'ready')""",(version,doc,workspace,os.getenv("EMBEDDING_MODEL","nomic-embed-text")))
                        conn.execute("UPDATE rag_documents SET active_version=%s WHERE id=%s",(version,doc))
                        names[name]=(doc,version)
                    doc,version=names[name]
                    conn.execute("""INSERT INTO rag_chunks(id,workspace_id,document_id,version_id,page,page_label,content,embedding)
                        VALUES(%s,%s,%s,%s,%s,%s,%s,%s::vector)""",
                        (str(uuid5(NAMESPACE_URL,"legacy:"+str(row["id"]))),workspace,doc,version,
                         int(row["cmetadata"].get("page",0))+1,str(row["cmetadata"].get("page_label","")),
                         row["document"],row["embedding"]))
                for doc,version in names.values():
                    conn.execute("UPDATE rag_versions SET chunk_count=(SELECT count(*) FROM rag_chunks WHERE version_id=%s) WHERE id=%s",(version,version))
                print("Imported",len(rows),"legacy vectors; original tables preserved",flush=True)
    print("Migrations and bootstrap complete",flush=True)

if __name__=="__main__":
    migrate()
