"""Live additive checks: account actions, document ACL/RLS, OCR, and private chat tools."""
import io,json,os,secrets,sys,time
from pathlib import Path
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from smoke_test import login,checked,wait_job
from test_support import local_settings,fixture_pdf,mail_action

def main():
    env=local_settings();os.environ['RAW_DATABASE_URL']=f"postgresql://rag_app:{env['APP_DB_PASSWORD']}@127.0.0.1:5432/rag_db"
    from db import connect
    from psycopg.types.json import Jsonb
    base='http://localhost:8000';suffix=uuid4().hex[:10]
    admin=login(base,env['BOOTSTRAP_ADMIN_EMAIL'],env['BOOTSTRAP_ADMIN_PASSWORD'])
    import httpx
    client=httpx.Client(base_url=base,timeout=330)
    email=f'enterprise-{suffix}@example.com';password=secrets.token_urlsafe(24)
    checked(client.post('/auth/register',json={'email':email,'name':'Enterprise test','password':password}),201)
    checked(client.post('/auth/login',json={'email':email,'password':password}),403)
    raw=mail_action(email,'Verify')
    checked(client.post('/auth/verify-email',json={'token':raw}));checked(client.post('/auth/verify-email',json={'token':raw}),400)
    client.close();client=login(base,email,password);uid=checked(client.get('/auth/me'))['user']['id']
    old_session=login(base,email,password)
    checked(client.post('/auth/forgot-password',json={'email':email}))
    raw=mail_action(email,'Reset');new_password=secrets.token_urlsafe(24)
    checked(client.post('/auth/reset-password',json={'token':raw,'password':new_password}))
    checked(client.post('/auth/reset-password',json={'token':raw,'password':new_password}),400)
    checked(old_session.get('/auth/me'),401);old_session.close();client.close();client=login(base,email,new_password)
    print('PASS account verification, single-use recovery and session revocation')
    workspace=checked(admin.post('/workspaces',json={'name':'Enterprise acceptance '+suffix}),201)['id']
    checked(admin.post(f'/workspaces/{workspace}/invitations',json={'email':email,'role':'reader'}),202)
    invitation=mail_action(email,'invitation')
    checked(admin.post('/auth/accept-invitation',json={'token':invitation}),400)
    checked(client.post('/auth/accept-invitation',json={'token':invitation}));checked(client.post('/auth/accept-invitation',json={'token':invitation}),400)
    checked(client.post(f'/workspaces/{workspace}/invitations',json={'email':'other@example.com'}),403)
    doc=checked(admin.post(f'/workspaces/{workspace}/documents',files={'file':('acl-handbook.pdf',fixture_pdf(),'application/pdf')}),202)
    wait_job(admin,workspace,doc['job_id'])
    assert len(checked(client.get(f'/workspaces/{workspace}/documents')))==1
    conversation=checked(client.post(f'/workspaces/{workspace}/conversations',json={'title':'Searchable private test'}),201)['id']
    request_id=str(uuid4())
    with connect(uid) as conn:
        conn.execute("INSERT INTO rag_messages(id,conversation_id,workspace_id,user_id,role,content,sources,status,request_id) VALUES(%s,%s,%s,%s,'assistant','A restricted fact',%s,'complete',%s)",(str(uuid4()),conversation,workspace,uid,Jsonb([{'document_id':doc['id'],'version_id':doc['version_id'],'file':'acl-handbook.pdf','page':1}]),request_id))
    checked(admin.put('/documents/'+doc['id']+'/permissions',json={'restricted':True,'user_ids':[]}))
    assert checked(client.get(f'/workspaces/{workspace}/documents'))==[]
    assert checked(client.get(f'/workspaces/{workspace}/jobs'))==[]
    checked(client.get('/documents/'+doc['id']+'/file'),404);checked(client.get('/documents/'+doc['id']+'/versions'),404)
    checked(client.get('/documents/'+doc['id']+'/extraction'),404)
    assert checked(client.post(f'/workspaces/{workspace}/search',json={'question':'Cedar approval code'}))['sources']==[]
    history=checked(client.get('/conversations/'+conversation));assert history['messages'][0]['sources']==[] and 'A restricted fact' not in history['messages'][0]['content']
    checked(client.post('/query',json={'workspace_id':workspace,'conversation_id':conversation,'request_id':request_id,'question':'Replay'}),403)
    with connect(uid) as conn:
        assert conn.execute('SELECT count(*) AS n FROM rag_chunks WHERE document_id=%s',(doc['id'],)).fetchone()['n']==0
    checked(admin.put('/documents/'+doc['id']+'/permissions',json={'restricted':True,'user_ids':[uid]}))
    assert client.get('/documents/'+doc['id']+'/file').status_code==200
    assert 'A restricted fact' in checked(client.get('/conversations/'+conversation))['messages'][0]['content']
    checked(client.patch('/conversations/'+conversation+'/pin',json={'pinned':True}))
    assert checked(client.get(f'/workspaces/{workspace}/conversations?q=Searchable'))[0]['pinned']
    assert client.get('/conversations/'+conversation+'/export').status_code==200
    checked(admin.get('/conversations/'+conversation+'/export'),404)
    print('PASS invitations, document ACL, direct SQL row policies, historical answer redaction, replay checks and private chat tools')
    from PIL import Image,ImageDraw,ImageFont
    image=Image.new('RGB',(1500,600),'white');draw=ImageDraw.Draw(image)
    font_path=Path(r'C:\Windows\Fonts\arial.ttf')
    font=ImageFont.truetype(str(font_path),44) if font_path.exists() else ImageFont.load_default(size=44)
    draw.multiline_text((70,70),'Project Raven scanned handbook.\nThe launch code is RAVEN-5812.\nThe coordinator is Ada Morgan.',font=font,fill='black',spacing=30)
    output=io.BytesIO();image.save(output,format='PDF',resolution=144)
    scan=checked(admin.post(f'/workspaces/{workspace}/documents',files={'file':('scanned-handbook.pdf',output.getvalue(),'application/pdf')}),202)
    wait_job(admin,workspace,scan['job_id'],timeout=240)
    with connect(checked(admin.get('/auth/me'))['user']['id']) as conn:
        texts=conn.execute('SELECT content,page FROM rag_chunks WHERE document_id=%s',(scan['id'],)).fetchall()
        assert any('RAVEN-5812' in r['content'] and r['page']==1 for r in texts),texts
    print('PASS raster-only PDF OCR with original page provenance')
    with connect(uid) as conn:
        expired=secrets.token_urlsafe(32)
        from security import token_hash
        conn.execute("INSERT INTO rag_action_tokens(token_hash,purpose,email,user_id,expires_at) VALUES(%s,'reset',%s,%s,now()-interval '1 minute')",(token_hash(expired),email,uid))
    checked(client.post('/auth/reset-password',json={'token':expired,'password':secrets.token_urlsafe(24)}),400)
    with connect() as conn:
        token,lease=conn.execute('SELECT count(*) AS n FROM rag_model_leases WHERE expires_at>now()').fetchone()['n'],None
        assert token==0,'A model lease was leaked'
    trace=admin.get('/health/live');assert len(trace.headers.get('X-Trace-ID',''))==32
    with connect(uid) as conn:
        conn.execute('INSERT INTO rag_oidc_identities VALUES(%s,%s,%s)',('https://idp.example.test',str(uuid4()),uid))
        count=conn.execute('SELECT count(*) AS n FROM rag_mail_outbox WHERE recipient=%s',(email,)).fetchone()['n']
    checked(client.post('/auth/login',json={'email':email,'password':new_password}),403)
    checked(client.post('/auth/forgot-password',json={'email':email}))
    with connect(uid) as conn:
        assert conn.execute('SELECT count(*) AS n FROM rag_mail_outbox WHERE recipient=%s',(email,)).fetchone()['n']==count
    print('PASS SSO accounts cannot bypass provider MFA through local login/recovery')
    print('PASS expired tokens and trace correlation; isolated test workspace:',workspace)
    client.close();admin.close()

if __name__=='__main__':main()
