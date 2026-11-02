import hashlib
import os
import re
import secrets
from datetime import datetime,timedelta,timezone
from typing import Literal
from uuid import UUID,uuid4

from fastapi import APIRouter,Depends,HTTPException,Request,Response
from pydantic import BaseModel,Field,field_validator
from psycopg.errors import UniqueViolation
from db import connect,audit
from account_mail import issue_action
from security import (COOKIE,SECURE_COOKIE,User,current_user,check_origin,csrf_token,
                      password_hash,password_matches,rate_limit,require_role,token_hash,validate_password)

router=APIRouter()

class Login(BaseModel):
    email:str=Field(max_length=254)
    password:str=Field(max_length=256)

class Registration(Login):
    name:str=Field(min_length=1,max_length=120)

    @field_validator("name")
    @classmethod
    def clean_name(cls,value):
        if not value.strip():
            raise ValueError("Enter your name.")
        return value.strip()

    @field_validator("email")
    @classmethod
    def clean_email(cls,value):
        value=value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",value):
            raise ValueError("Enter a valid email address.")
        return value

@router.post("/auth/register",status_code=201)
def register(body:Registration,request:Request):
    check_origin(request)
    if os.getenv("ALLOW_REGISTRATION","true").lower()!="true":
        raise HTTPException(403,"Self-service registration is disabled. Contact your administrator.")
    address=request.client.host if request.client else "unknown"
    rate_limit("register:"+hashlib.sha256(address.encode()).hexdigest(),5,60)
    validate_password(body.password)
    user_id=str(uuid4())
    encoded=password_hash(body.password)
    try:
        with connect(user_id) as conn:
            conn.execute("INSERT INTO rag_users(id,email,name,password_hash) VALUES(%s,%s,%s,%s)",
                         (user_id,body.email,body.name,encoded))
            workspace=conn.execute("SELECT rag_create_workspace(%s) AS id",(f"{body.name[:98]}'s workspace",)).fetchone()["id"]
            audit(conn,user_id,workspace,"account.registered",user_id)
            issue_action(conn,'verify',body.email,user_id)
    except UniqueViolation:
        raise HTTPException(409,"An account with this email already exists. Sign in instead.") from None
    return {"message":"Account created. Check your email to verify your address before signing in."}

class WorkspaceInput(BaseModel):
    name:str=Field(min_length=1,max_length=120)

class MemberInput(BaseModel):
    email:str=Field(max_length=254)
    role:Literal["admin","editor","reader"]="reader"

class UserInput(MemberInput):
    name:str=Field(min_length=1,max_length=120)
    password:str=Field(min_length=12,max_length=256)

class RoleInput(BaseModel):
    role:Literal["admin","editor","reader"]

class PasswordInput(BaseModel):
    current_password:str=Field(max_length=256)
    new_password:str=Field(min_length=12,max_length=256)

@router.post("/auth/login")
def login(body:Login,request:Request,response:Response):
    check_origin(request)
    address=request.client.host if request.client else "unknown"
    rate_limit("login:"+hashlib.sha256(address.encode()).hexdigest(),10,60)
    with connect() as conn:
        user=conn.execute("SELECT * FROM rag_users WHERE email=%s",(body.email.strip().lower(),)).fetchone()
        encoded=user["password_hash"] if user else "scrypt$00000000000000000000000000000000$"+"0"*128
        valid=password_matches(body.password,encoded)
        if not valid or not user or user["disabled"]:
            raise HTTPException(401,"Incorrect email or password.")
        if not user['email_verified']:
            raise HTTPException(403,"Verify your email before signing in. Use Resend verification if you need a new link.")
        if conn.execute('SELECT 1 FROM rag_oidc_identities WHERE user_id=%s',(user['id'],)).fetchone():
            raise HTTPException(403,'Use organization SSO for this account.')
        token=secrets.token_urlsafe(48)
        conn.execute("DELETE FROM rag_sessions WHERE expires_at<now()")
        conn.execute("INSERT INTO rag_sessions(token_hash,user_id,expires_at) VALUES(%s,%s,%s)",
                     (token_hash(token),user["id"],datetime.now(timezone.utc)+timedelta(hours=8)))
    response.set_cookie(COOKIE,token,max_age=8*3600,httponly=True,secure=SECURE_COOKIE,samesite="lax",path="/")
    return {"user":{"id":str(user["id"]),"email":user["email"],"name":user["name"]},"csrf_token":csrf_token(token)}

@router.get("/auth/me")
def me(request:Request,user:User=Depends(current_user)):
    return {"user":{"id":user.id,"email":user.email,"name":user.name},"csrf_token":csrf_token(request.cookies[COOKIE])}

@router.post("/auth/logout")
def logout(response:Response,user:User=Depends(current_user)):
    with connect(user.id) as conn:
        conn.execute("DELETE FROM rag_sessions WHERE token_hash=%s",(user.session_hash,))
    response.delete_cookie(COOKIE,path="/",secure=SECURE_COOKIE,httponly=True,samesite="lax")
    return {"message":"Signed out."}

@router.post("/auth/password")
def change_password(body:PasswordInput,response:Response,user:User=Depends(current_user)):
    validate_password(body.new_password)
    with connect(user.id) as conn:
        old=conn.execute("SELECT password_hash FROM rag_users WHERE id=%s FOR UPDATE",(user.id,)).fetchone()
        if not password_matches(body.current_password,old["password_hash"]):
            raise HTTPException(403,"Current password is incorrect.")
        conn.execute("UPDATE rag_users SET password_hash=%s WHERE id=%s",(password_hash(body.new_password),user.id))
        conn.execute("DELETE FROM rag_sessions WHERE user_id=%s",(user.id,))
    response.delete_cookie(COOKIE,path="/")
    return {"message":"Password changed. Sign in again."}

@router.get("/workspaces")
def workspaces(user:User=Depends(current_user)):
    with connect(user.id) as conn:
        return conn.execute("""SELECT w.id,w.name,m.role FROM rag_workspaces w JOIN rag_memberships m ON m.workspace_id=w.id
            WHERE m.user_id=%s ORDER BY w.created_at""",(user.id,)).fetchall()

@router.post("/workspaces",status_code=201)
def create_workspace(body:WorkspaceInput,user:User=Depends(current_user)):
    with connect(user.id) as conn:
        workspace=conn.execute("SELECT rag_create_workspace(%s) AS id",(body.name,)).fetchone()["id"]
        audit(conn,user.id,workspace,"workspace.created",workspace)
    return {"id":str(workspace),"name":body.name.strip(),"role":"admin"}

@router.get("/workspaces/{workspace}/members")
def members(workspace:UUID,user:User=Depends(current_user)):
    with connect(user.id) as conn:
        require_role(conn,workspace,("admin",))
        return conn.execute("""SELECT u.id,u.email,u.name,m.role FROM rag_memberships m JOIN rag_users u ON u.id=m.user_id
            WHERE m.workspace_id=%s ORDER BY u.email""",(workspace,)).fetchall()

@router.post("/workspaces/{workspace}/members",status_code=201)
def add_member(workspace:UUID,body:MemberInput,user:User=Depends(current_user)):
    with connect(user.id) as conn:
        require_role(conn,workspace,("admin",))
        member=conn.execute("SELECT id FROM rag_users WHERE email=%s AND NOT disabled",(body.email.strip().lower(),)).fetchone()
        if not member:
            raise HTTPException(404,"Account not found. Create an account first.")
        conn.execute("""INSERT INTO rag_memberships(workspace_id,user_id,role) VALUES(%s,%s,%s)
            ON CONFLICT DO NOTHING""",(workspace,member["id"],body.role))
        audit(conn,user.id,workspace,"member.added",member["id"])
    return {"message":"Membership added."}

@router.post("/workspaces/{workspace}/users",status_code=201)
def create_user(workspace:UUID,body:UserInput,user:User=Depends(current_user)):
    validate_password(body.password)
    email=body.email.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+",email):
        raise HTTPException(422,"Enter a valid email address.")
    with connect(user.id) as conn:
        require_role(conn,workspace,("admin",))
        if conn.execute("SELECT id FROM rag_users WHERE email=%s",(email,)).fetchone():
            raise HTTPException(409,"This account already exists. Add it as a member instead.")
        target=str(uuid4())
        conn.execute("INSERT INTO rag_users(id,email,name,password_hash,email_verified) VALUES(%s,%s,%s,%s,true)",(target,email,body.name,password_hash(body.password)))
        conn.execute("INSERT INTO rag_memberships VALUES(%s,%s,%s)",(workspace,target,body.role))
        audit(conn,user.id,workspace,"account.created",target)
    return {"id":target,"email":email,"name":body.name,"role":body.role}

def protect_last_admin(conn,workspace,target):
    conn.execute("SELECT id FROM rag_workspaces WHERE id=%s FOR UPDATE",(workspace,))
    current=conn.execute("SELECT role FROM rag_memberships WHERE workspace_id=%s AND user_id=%s",(workspace,target)).fetchone()
    if not current:
        raise HTTPException(404,"Membership not found.")
    if current["role"]=="admin" and conn.execute(
        "SELECT count(*) AS n FROM rag_memberships WHERE workspace_id=%s AND role='admin'",(workspace,)).fetchone()["n"]<=1:
        raise HTTPException(409,"A workspace must retain at least one administrator.")

@router.patch("/workspaces/{workspace}/members/{target}")
def update_member(workspace:UUID,target:UUID,body:RoleInput,user:User=Depends(current_user)):
    with connect(user.id) as conn:
        require_role(conn,workspace,("admin",))
        if not conn.execute("SELECT 1 FROM rag_memberships WHERE workspace_id=%s AND user_id=%s",(workspace,target)).fetchone():
            raise HTTPException(404,"Membership not found.")
        if body.role!="admin":
            protect_last_admin(conn,workspace,target)
        conn.execute("UPDATE rag_memberships SET role=%s WHERE workspace_id=%s AND user_id=%s",(body.role,workspace,target))
        audit(conn,user.id,workspace,"member.role_changed",target)
    return {"message":"Role updated."}

@router.delete("/workspaces/{workspace}/members/{target}")
def remove_member(workspace:UUID,target:UUID,user:User=Depends(current_user)):
    with connect(user.id) as conn:
        require_role(conn,workspace,("admin",))
        protect_last_admin(conn,workspace,target)
        conn.execute("DELETE FROM rag_memberships WHERE workspace_id=%s AND user_id=%s",(workspace,target))
        audit(conn,user.id,workspace,"member.removed",target)
    return {"message":"Membership removed."}
