import hashlib
import os
from pathlib import Path
from uuid import uuid4
from fastapi import HTTPException

ROOT=Path(os.getenv("STORAGE_DIR",str(Path(__file__).parent/"data"))).resolve()
MAX_UPLOAD_BYTES=int(os.getenv("MAX_UPLOAD_MB","50"))*1024*1024

def storage_path(key):
    path=(ROOT/key).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("Invalid storage key")
    return path

def save_upload(upload):
    ROOT.mkdir(parents=True,exist_ok=True)
    key=str(uuid4())+".pdf"
    path=storage_path(key)
    checksum=hashlib.sha256()
    size=0
    try:
        with path.open("xb") as output:
            while block:=upload.file.read(1024*1024):
                size+=len(block)
                if size>MAX_UPLOAD_BYTES:
                    raise HTTPException(413,"PDF files must be 50 MB or smaller.")
                checksum.update(block)
                output.write(block)
        with path.open("rb") as saved:
            if not saved.read(1024).lstrip().startswith(b"%PDF-"):
                raise HTTPException(400,"This is not a valid PDF.")
        return key,checksum.hexdigest(),size
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        upload.file.close()
