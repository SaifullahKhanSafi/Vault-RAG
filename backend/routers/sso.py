"""OIDC authorization-code login with PKCE, validated nonce/state and issuer/subject binding."""
import os,secrets
import httpx2 as httpx
from datetime import datetime,timedelta,timezone
from uuid import uuid4
from authlib.integrations.starlette_client import OAuth
from authlib.integrations.base_client.errors import OAuthError
from joserfc.errors import JoseError
from fastapi import APIRouter,HTTPException,Request
from fastapi.responses import RedirectResponse
from psycopg.errors import UniqueViolation
from db import connect,audit
from security import COOKIE,SECURE_COOKIE,password_hash,token_hash,rate_limit

router=APIRouter()
oauth=OAuth()
issuer=os.getenv('OIDC_ISSUER','').rstrip('/')
class IssuerTransport(httpx.AsyncBaseTransport):
    """Local Docker split routing keeps the public issuer identity intact."""
    def __init__(self):self.transport=httpx.AsyncHTTPTransport()
    async def handle_async_request(self,request):
        internal=os.getenv('OIDC_INTERNAL_ISSUER','').rstrip('/')
        if internal and str(request.url).startswith(issuer+'/'):
            request.url=httpx.URL(internal+str(request.url)[len(issuer):])
            request.headers['host']=request.url.netloc.decode()
        return await self.transport.handle_async_request(request)
    async def aclose(self):await self.transport.aclose()
if issuer:
    oauth.register('enterprise',client_id=os.environ['OIDC_CLIENT_ID'],client_secret=os.getenv('OIDC_CLIENT_SECRET'),
                   server_metadata_url=issuer+'/.well-known/openid-configuration',
                   client_kwargs={'scope':'openid email profile','code_challenge_method':'S256','transport':IssuerTransport()})

@router.get('/auth/options')
def options():return {'sso_enabled':bool(issuer)}

@router.get('/auth/sso/login')
async def login(request:Request):
    if not issuer:raise HTTPException(404,'SSO is not configured.')
    rate_limit('sso:'+str(request.client.host),20,60)
    return await oauth.enterprise.authorize_redirect(request,os.environ['OIDC_REDIRECT_URI'])

@router.get('/auth/sso/callback')
async def callback(request:Request):
    if not issuer:raise HTTPException(404,'SSO is not configured.')
    try:
        token=await oauth.enterprise.authorize_access_token(request)
        info=token.get('userinfo',{})
        if info.get('iss')!=issuer or not info.get('sub') or info.get('email_verified') is not True:
            raise HTTPException(403,'Your identity provider must verify your email address.')
        email=str(info.get('email','')).strip().lower()
        if not email or len(email)>254:raise HTTPException(403,'A valid verified email is required.')
        from routers.accounts import Registration
        email=Registration.clean_email(email)
        with connect() as conn:
            row=conn.execute('SELECT u.* FROM rag_oidc_identities i JOIN rag_users u ON u.id=i.user_id WHERE i.issuer=%s AND i.subject=%s',(issuer,info['sub'])).fetchone()
            if not row:
                # Never silently merge by email with a pre-existing local account.
                if conn.execute('SELECT 1 FROM rag_users WHERE email=%s',(email,)).fetchone():raise HTTPException(409,'An account already uses this email. Sign in with its existing method.')
                uid=str(uuid4());name=str(info.get('name') or email)[:120]
                conn.execute('INSERT INTO rag_users(id,email,name,password_hash,email_verified) VALUES(%s,%s,%s,%s,true)',(uid,email,name,password_hash(secrets.token_urlsafe(48))))
                conn.execute('INSERT INTO rag_oidc_identities VALUES(%s,%s,%s)',(issuer,info['sub'],uid))
                conn.execute("SELECT set_config('app.user_id',%s,true)",(uid,))
                workspace=conn.execute('SELECT rag_create_workspace(%s) AS id',(name[:98]+"'s workspace",)).fetchone()['id']
                audit(conn,uid,workspace,'account.sso_created',uid)
            else:uid=str(row['id'])
            if row and row['disabled']:raise HTTPException(403,'Account disabled.')
            raw=secrets.token_urlsafe(48)
            conn.execute('INSERT INTO rag_sessions(token_hash,user_id,expires_at) VALUES(%s,%s,%s)',(token_hash(raw),uid,datetime.now(timezone.utc)+timedelta(hours=8)))
        request.session.clear()
        response=RedirectResponse(os.getenv('APP_ORIGIN','http://localhost:3000'),status_code=303)
        response.set_cookie(COOKIE,raw,max_age=8*3600,httponly=True,secure=SECURE_COOKIE,samesite='lax',path='/')
        return response
    except (OAuthError,JoseError,UniqueViolation,httpx.HTTPError,ValueError):
        request.session.clear()
        raise HTTPException(400,'SSO sign-in could not be validated. Start sign-in again.') from None
