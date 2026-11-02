"""Backup/restore verification, model warmup and explicit retention maintenance."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
from datetime import datetime,timezone
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from test_support import local_settings
env=local_settings()
docker=["docker","--config",str(ROOT/"backend"),"compose"]

def run(args,**kwargs):
    return subprocess.run(docker+["exec","-T","db"]+args,check=True,**kwargs)

def backup():
    destination=ROOT/"backups"/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination.mkdir(parents=True,exist_ok=False)
    with (destination/"database.dump").open("wb") as output:
        run(["pg_dump","-U","rag_user","-d","rag_db","-Fc"],stdout=output)
    with tarfile.open(destination/"originals.tar.gz","w:gz") as archive:
        if (ROOT/"storage").exists():archive.add(ROOT/"storage",arcname="storage")
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in destination.iterdir() if p.is_file()}
    (destination/"manifest.json").write_text(json.dumps({"created_at":datetime.now(timezone.utc).isoformat(),"sha256":hashes},indent=2),encoding="utf-8")
    print("Backup saved:",destination)
    return destination

def restore_check(path):
    path=Path(path).resolve()
    manifest=json.loads((path/"manifest.json").read_text())
    for name,expected in manifest["sha256"].items():
        candidate=(path/name).resolve()
        if not candidate.is_relative_to(path) or hashlib.sha256(candidate.read_bytes()).hexdigest()!=expected:
            raise RuntimeError("Backup checksum mismatch")
    # Restore only into an explicitly generated disposable database.
    scratch="rag_restore_check_"+uuid4().hex
    run(["createdb","-U","rag_user",scratch],stdout=subprocess.DEVNULL)
    try:
        with (path/"database.dump").open("rb") as dump:
            run(["pg_restore","-U","rag_user","-d",scratch,"--no-owner","--exit-on-error"],stdin=dump,stdout=subprocess.DEVNULL)
        result=run(["psql","-U","rag_user","-d",scratch,"-At","-c",
            "SELECT (SELECT count(*) FROM rag_users),(SELECT count(*) FROM rag_chunks),(SELECT count(*) FROM rag_schema_migrations);"],
            capture_output=True,text=True)
        counts=result.stdout.strip()
        with tarfile.open(path/"originals.tar.gz","r:gz") as archive:
            keys={member.name for member in archive.getmembers() if member.isfile()}
            stored=run(["psql","-U","rag_user","-d",scratch,"-At","-c","SELECT storage_key FROM rag_versions WHERE storage_key IS NOT NULL;"],capture_output=True,text=True)
            missing=[key for key in stored.stdout.splitlines() if "storage/"+key not in keys]
            if missing:raise RuntimeError("Missing original files in backup: "+str(len(missing)))
        print("RESTORE CHECK PASSED: users|chunks|migrations =",counts,"; original file coverage verified")
    finally:
        if not scratch.startswith("rag_restore_check_"):
            raise RuntimeError("Unsafe scratch database name")
        run(["dropdb","-U","rag_user",scratch],stdout=subprocess.DEVNULL)

def warmup():
    import httpx
    with httpx.Client(base_url=env.get("OLLAMA_BASE_URL","http://localhost:11434"),timeout=330) as client:
        r=client.post("/api/embed",json={"model":env.get("EMBEDDING_MODEL","nomic-embed-text"),"input":"warmup","keep_alive":"10m"});r.raise_for_status()
        r=client.post("/api/generate",json={"model":env.get("CHAT_MODEL","qwen2.5:7b-instruct"),"prompt":"Reply OK.","stream":False,"keep_alive":"10m","options":{"num_ctx":4096,"num_predict":4}});r.raise_for_status()
    print("Embedding and generation models warmed successfully")

parser=argparse.ArgumentParser()
sub=parser.add_subparsers(dest="command",required=True)
sub.add_parser("backup")
r=sub.add_parser("restore-check");r.add_argument("path")
sub.add_parser("warmup")
args=parser.parse_args()
if args.command=="backup":backup()
elif args.command=="restore-check":restore_check(args.path)
elif args.command=="warmup":warmup()
