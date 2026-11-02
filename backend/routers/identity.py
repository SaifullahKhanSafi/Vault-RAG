import hashlib
from typing import Literal
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Request
from pydantic import BaseModel,Field,field_validator
from account_mail import issue_action,consume_action
from db import connect,audit
from security import User,current_user,check_origin,rate_limit,password_hash,validate_password,require_role

router=APIRouter()
class EmailInput(BaseModel):
    email:str=Field(max_length=254)
class TokenInput(BaseModel):
    token:str=Field(min_length=20,max_length=200)
class ResetInput(TokenInput):
    password:str=Field(min_length=12,max_length=256)
class InviteInput(EmailInput):
    role:Literal['reader','editor']='reader'
    @field_validator('email')
    @classmethod
    def valid_email(cls,value):
        from routers.accounts import Registration
        return Registration.clean_email(value)

def public_limit(request):
    check_origin(request)
    address=request.client.host if request.client else 'unknown'
    rate_limit('account-action:'+hashlib.sha256(address.encode()).hexdigest(),10,60)

@router.post('/auth/forgot-password')
def forgot(body:EmailInput,request:Request):
    public_limit(request)
    with connect() as conn:
        user=conn.execute('SELECT id,email FROM rag_users u WHERE email=%s AND NOT disabled AND email_verified AND NOT EXISTS(SELECT 1 FROM rag_oidc_identities i WHERE i.user_id=u.id)',(body.email.strip().lower(),)).fetchone()
        if user:issue_action(conn,'reset',user['email'],user['id'])
    return {'message':'If an eligible account exists, a recovery email will arrive shortly.'}

@router.post('/auth/resend-verification')
def resend(body:EmailInput,request:Request):
    public_limit(request)
    with connect() as conn:
        user=conn.execute('SELECT id,email FROM rag_users WHERE email=%s AND NOT disabled AND NOT email_verified',(body.email.strip().lower(),)).fetchone()
        if user:issue_action(conn,'verify',user['email'],user['id'])
    return {'message':'If verification is needed, an email will arrive shortly.'}

@router.post('/auth/verify-email')
def verify(body:TokenInput,request:Request):
    public_limit(request)
    with connect() as conn:
        action=consume_action(conn,body.token,'verify')
        if not action:raise HTTPException(400,'This link is invalid, expired, or already used.')
        conn.execute('UPDATE rag_users SET email_verified=true WHERE id=%s',(action['user_id'],))
    return {'message':'Email verified. You can now sign in.'}

@router.post('/auth/reset-password')
def reset(body:ResetInput,request:Request):
    public_limit(request);validate_password(body.password)
    encoded=password_hash(body.password)
    with connect() as conn:
        action=consume_action(conn,body.token,'reset')
        if not action:raise HTTPException(400,'This link is invalid, expired, or already used.')
        if conn.execute('SELECT 1 FROM rag_oidc_identities WHERE user_id=%s',(action['user_id'],)).fetchone():
            raise HTTPException(400,'Use your organization identity provider to recover this account.')
        conn.execute('UPDATE rag_users SET password_hash=%s WHERE id=%s AND NOT disabled',(encoded,action['user_id']))
        conn.execute('DELETE FROM rag_sessions WHERE user_id=%s',(action['user_id'],))
        conn.execute("UPDATE rag_action_tokens SET used_at=now() WHERE user_id=%s AND purpose='reset' AND used_at IS NULL",(action['user_id'],))
    return {'message':'Password updated. Sign in again on each device.'}

@router.post('/workspaces/{workspace}/invitations',status_code=202)
def invite(workspace:UUID,body:InviteInput,user:User=Depends(current_user)):
    email=body.email
    rate_limit('invite:'+user.id,10,60)
    with connect(user.id) as conn:
        require_role(conn,workspace,('admin',))
        issue_action(conn,'invite',email,workspace=workspace,role=body.role)
        audit(conn,user.id,workspace,'invitation.sent')
    return {'message':'Invitation queued. The recipient must sign in with a verified account to accept.'}

@router.post('/auth/accept-invitation')
def accept(body:TokenInput,user:User=Depends(current_user)):
    with connect(user.id) as conn:
        # Scope the update before consuming the one-time token.
        from security import token_hash
        action=conn.execute("SELECT * FROM rag_action_tokens WHERE token_hash=%s AND purpose='invite' AND email=%s AND used_at IS NULL AND expires_at>now() FOR UPDATE",(token_hash(body.token),user.email)).fetchone()
        approved=conn.execute('SELECT email_verified FROM rag_users WHERE id=%s',(user.id,)).fetchone()
        if not action or not approved['email_verified']:raise HTTPException(400,'Sign in with the verified email address this invitation was sent to.')
        # A narrowly scoped security-definer function creates the membership under RLS.
        conn.execute('SELECT rag_accept_invitation(%s)',(token_hash(body.token),))
    return {'message':'Invitation accepted. Open your workspace selector after reloading.'}
