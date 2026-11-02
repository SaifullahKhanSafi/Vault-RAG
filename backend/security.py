"""Password hashing, opaque revocable sessions, CSRF, roles and shared limits."""
import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from fastapi import Depends, HTTPException, Request
from db import connect

COOKIE = "rag_session"
SECRET = os.environ.get("AUTH_SECRET", "")
SECURE_COOKIE = os.getenv("COOKIE_SECURE","false").lower() == "true"
ORIGINS = set(os.getenv("CORS_ORIGINS","http://localhost:3000,http://127.0.0.1:3000").split(","))

def password_hash(password):
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode(), salt=salt, n=32768,r=8,p=1,maxmem=64*1024*1024)
    return "scrypt$" + salt.hex() + "$" + derived.hex()

def password_matches(password, encoded):
    try:
        _,salt,expected = encoded.split("$")
        value = hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=32768,r=8,p=1,maxmem=64*1024*1024)
        return hmac.compare_digest(value.hex(),expected)
    except (ValueError,TypeError):
        return False

def validate_password(password):
    if not 12 <= len(password) <= 256:
        raise HTTPException(422,"Use a password containing 12 to 256 characters.")

def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()

def csrf_token(token):
    return hmac.new(SECRET.encode(),token.encode(),hashlib.sha256).hexdigest()

def check_origin(request):
    if request.headers.get("origin") and request.headers["origin"] not in ORIGINS:
        raise HTTPException(403,"Request origin is not allowed.")

@dataclass
class User:
    id: str
    email: str
    name: str
    session_hash: str

def current_user(request: Request):
    token = request.cookies.get(COOKIE,"")
    if not token:
        raise HTTPException(401,"Please sign in.")
    with connect() as conn:
        row = conn.execute("""
            SELECT u.id,u.email,u.name FROM rag_sessions s JOIN rag_users u ON u.id=s.user_id
            WHERE s.token_hash=%s AND s.expires_at>now() AND NOT u.disabled
        """,(token_hash(token),)).fetchone()
    if not row:
        raise HTTPException(401,"Your session expired. Please sign in again.")
    if request.method not in ("GET","HEAD","OPTIONS"):
        check_origin(request)
        supplied = request.headers.get("x-csrf-token","")
        if not hmac.compare_digest(csrf_token(token),supplied):
            raise HTTPException(403,"Invalid CSRF token. Refresh and try again.")
    return User(str(row["id"]),row["email"],row["name"],token_hash(token))

def require_role(conn, workspace, roles=("admin","editor","reader")):
    row=conn.execute("SELECT rag_role(%s::uuid) AS role",(str(workspace),)).fetchone()
    if not row or row["role"] not in roles:
        raise HTTPException(403,"You do not have permission in this workspace.")
    return row["role"]

def rate_limit(key, limit, seconds=60):
    # Atomic across API processes; expiration resets the bucket.
    with connect() as conn:
        row=conn.execute("""
            INSERT INTO rag_rate_limits(key,count,expires_at) VALUES(%s,1,now()+(%s * interval '1 second'))
            ON CONFLICT(key) DO UPDATE SET
            count=CASE WHEN rag_rate_limits.expires_at<now() THEN 1 ELSE rag_rate_limits.count+1 END,
            expires_at=CASE WHEN rag_rate_limits.expires_at<now() THEN EXCLUDED.expires_at ELSE rag_rate_limits.expires_at END
            RETURNING count
        """,(key,seconds)).fetchone()
    if row["count"]>limit:
        raise HTTPException(429,"Too many requests. Please try again shortly.",headers={"Retry-After":str(seconds)})

def acquire_model(owner):
    lease=str(uuid4())
    with connect() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(723491)")
        conn.execute("DELETE FROM rag_model_leases WHERE expires_at<now()")
        count=conn.execute("SELECT count(*) AS n FROM rag_model_leases").fetchone()["n"]
        if count>=int(os.getenv("MODEL_CONCURRENCY","1")):
            raise HTTPException(503,"The model is busy. Please retry shortly.",headers={"Retry-After":"5"})
        conn.execute("INSERT INTO rag_model_leases VALUES(%s,%s,now()+interval '6 minutes')",(lease,owner))
    return lease

def renew_model(lease):
    with connect() as conn:
        conn.execute("UPDATE rag_model_leases SET expires_at=now()+interval '6 minutes' WHERE id=%s",(lease,))

def release_model(lease):
    with connect() as conn:
        conn.execute("DELETE FROM rag_model_leases WHERE id=%s",(lease,))
