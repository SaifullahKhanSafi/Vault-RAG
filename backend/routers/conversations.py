from uuid import UUID,uuid4
from fastapi import APIRouter,Depends,HTTPException
from fastapi.responses import Response
from pydantic import BaseModel,Field
from db import connect,audit
from security import User,current_user,require_role
from history_access import redact_messages

router=APIRouter()
class ConversationInput(BaseModel):
    title:str=Field(default="New chat",min_length=1,max_length=120)
class FeedbackInput(BaseModel):
    rating:int=Field(ge=-1,le=1)
    note:str=Field(default="",max_length=2000)
class PinInput(BaseModel):
    pinned:bool

@router.get("/workspaces/{workspace}/conversations")
def conversations(workspace:UUID,q:str='',user:User=Depends(current_user)):
    if len(q)>200:raise HTTPException(422,'Search text is too long.')
    with connect(user.id) as conn:
        require_role(conn,workspace)
        # Search titles and user-authored questions; do not expose restricted answers through snippets.
        return conn.execute("""SELECT id,title,pinned,created_at,updated_at FROM rag_conversations c WHERE workspace_id=%s
            AND (%s='' OR strpos(lower(title),lower(%s))>0 OR EXISTS(SELECT 1 FROM rag_messages m WHERE m.conversation_id=c.id AND m.role='user' AND strpos(lower(m.content),lower(%s))>0))
            ORDER BY pinned DESC,updated_at DESC""",(workspace,q,q,q)).fetchall()

@router.post("/workspaces/{workspace}/conversations",status_code=201)
def create_conversation(workspace:UUID,body:ConversationInput,user:User=Depends(current_user)):
    identity=str(uuid4())
    with connect(user.id) as conn:
        require_role(conn,workspace)
        conn.execute("INSERT INTO rag_conversations(id,workspace_id,user_id,title) VALUES(%s,%s,%s,%s)",(identity,workspace,user.id,body.title))
    return {"id":identity,"title":body.title,"messages":[]}

@router.get("/conversations/{conversation}")
def get_conversation(conversation:UUID,user:User=Depends(current_user)):
    with connect(user.id) as conn:
        row=conn.execute("SELECT * FROM rag_conversations WHERE id=%s",(conversation,)).fetchone()
        if not row:
            raise HTTPException(404,"Conversation not found.")
        messages=conn.execute("""SELECT id,role,content,sources,CASE WHEN status='streaming'
            AND %s<now() THEN 'failed' ELSE status END AS status FROM rag_messages
            WHERE conversation_id=%s ORDER BY sequence""",(row["busy_until"],conversation)).fetchall()
        return {"id":row["id"],"title":row["title"],"pinned":row['pinned'],"messages":redact_messages(conn,messages)}

@router.patch('/conversations/{conversation}/pin')
def pin(conversation:UUID,body:PinInput,user:User=Depends(current_user)):
    with connect(user.id) as conn:
        if not conn.execute('UPDATE rag_conversations SET pinned=%s WHERE id=%s RETURNING id',(body.pinned,conversation)).fetchone():raise HTTPException(404,'Conversation not found.')
    return {'pinned':body.pinned}

@router.get('/conversations/{conversation}/export')
def export(conversation:UUID,user:User=Depends(current_user)):
    data=get_conversation(conversation,user)
    content='# '+data['title']+'\n\n'+'\n\n'.join('## '+m['role'].title()+'\n\n'+m['content'] for m in data['messages'])
    return Response(content,media_type='text/markdown',headers={'Content-Disposition':f'attachment; filename="conversation-{conversation}.md"'})

@router.delete("/conversations/{conversation}")
def delete_conversation(conversation:UUID,user:User=Depends(current_user)):
    with connect(user.id) as conn:
        row=conn.execute("SELECT * FROM rag_conversations WHERE id=%s FOR UPDATE",(conversation,)).fetchone()
        if not row:
            raise HTTPException(404,"Conversation not found.")
        if row["busy_until"] and conn.execute("SELECT %s>now() AS busy",(row["busy_until"],)).fetchone()["busy"]:
            raise HTTPException(409,"Stop the current response before deleting this conversation.")
        conn.execute("DELETE FROM rag_conversations WHERE id=%s",(conversation,))
        audit(conn,user.id,row["workspace_id"],"conversation.deleted",conversation)
    return {"message":"Conversation deleted."}

@router.post("/messages/{message}/feedback")
def feedback(message:UUID,body:FeedbackInput,user:User=Depends(current_user)):
    if body.rating not in (-1,1):
        raise HTTPException(422,"Rating must be -1 or 1.")
    with connect(user.id) as conn:
        row=conn.execute("SELECT workspace_id FROM rag_messages WHERE id=%s AND role='assistant'",(message,)).fetchone()
        if not row:
            raise HTTPException(404,"Message not found.")
        conn.execute("""INSERT INTO rag_feedback(message_id,workspace_id,user_id,rating,note) VALUES(%s,%s,%s,%s,%s)
            ON CONFLICT(message_id) DO UPDATE SET rating=EXCLUDED.rating,note=EXCLUDED.note,updated_at=now()""",
            (message,row["workspace_id"],user.id,body.rating,body.note))
    return {"message":"Feedback saved."}
