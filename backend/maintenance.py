"""Explicit operator retention purge. Dry run by default; never targets active documents."""
import argparse
import os
import psycopg
from psycopg.rows import dict_row
from storage import storage_path

parser=argparse.ArgumentParser()
parser.add_argument("--days",type=int,default=90)
parser.add_argument("--confirm",action="store_true")
args=parser.parse_args()
if not 1<=args.days<=3650:raise SystemExit("Retention must be 1 to 3650 days.")
with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"],row_factory=dict_row) as conn:
    rows=conn.execute("""SELECT id FROM rag_documents WHERE deleted_at<now()-(%s*interval '1 day')
        FOR UPDATE SKIP LOCKED""",(args.days,)).fetchall()
    identities=[str(row["id"]) for row in rows]
    files=conn.execute("SELECT storage_key FROM rag_versions WHERE document_id=ANY(%s::uuid[]) AND storage_key IS NOT NULL",(identities,)).fetchall() if identities else []
    print("Eligible deleted documents:",len(identities),"retained PDFs:",len(files))
    if args.confirm and identities:
        conn.execute("UPDATE rag_documents SET active_version=NULL WHERE id=ANY(%s::uuid[])",(identities,))
        conn.execute("DELETE FROM rag_documents WHERE id=ANY(%s::uuid[])",(identities,))
if args.confirm:
    for row in files:
        storage_path(row["storage_key"]).unlink(missing_ok=True)
    print("Retention purge complete. Active documents and legacy index tables were not touched.")
else:print("Dry run only. Add --confirm to permanently purge these deleted documents.")
