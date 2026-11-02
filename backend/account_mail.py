"""Transactional, single-use account actions. Tokens are never returned by public APIs."""
import os
import secrets
from datetime import datetime,timedelta,timezone
from urllib.parse import urlencode
from security import token_hash

def issue_action(conn,purpose,email,user_id=None,workspace=None,role=None):
    raw=secrets.token_urlsafe(40)
    lifetime=timedelta(hours=48) if purpose=='invite' else timedelta(minutes=30)
    # Supersede earlier recovery/verification links without affecting unrelated invitations.
    conn.execute("UPDATE rag_action_tokens SET used_at=now() WHERE purpose=%s AND email=%s AND used_at IS NULL AND workspace_id IS NOT DISTINCT FROM %s::uuid",(purpose,email,workspace))
    conn.execute("INSERT INTO rag_action_tokens(token_hash,purpose,email,user_id,workspace_id,role,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                 (token_hash(raw),purpose,email,user_id,workspace,role,datetime.now(timezone.utc)+lifetime))
    origin=os.getenv('APP_ORIGIN','http://localhost:3000').rstrip('/')
    link=origin+'/#'+urlencode({'action':purpose,'token':raw})
    subject={'verify':'Verify your Enterprise RAG email','reset':'Reset your Enterprise RAG password','invite':'Enterprise RAG workspace invitation'}[purpose]
    conn.execute("INSERT INTO rag_mail_outbox(recipient,subject,body) VALUES(%s,%s,%s)",
                 (email,subject,f'{subject}\n\nOpen this link:\n{link}\n\nThis link expires and can be used once. If you did not request it, ignore this email.'))

def consume_action(conn,raw,purpose):
    return conn.execute("UPDATE rag_action_tokens SET used_at=now() WHERE token_hash=%s AND purpose=%s AND used_at IS NULL AND expires_at>now() RETURNING *",(token_hash(raw),purpose)).fetchone()
