"""Recheck cited document access when reading saved answers or replaying a request."""
def evidence_visible(conn,sources):
    ids={str(s['document_id']) for s in sources if s.get('document_id')}
    if not ids:return True
    rows=conn.execute('SELECT id FROM rag_documents WHERE id=ANY(%s::uuid[]) AND deleted_at IS NULL',(list(ids),)).fetchall()
    return len(rows)==len(ids)

def redact_messages(conn,messages):
    for message in messages:
        if message.get('sources') and not evidence_visible(conn,message['sources']):
            message['content']='This answer references documents you can no longer access.'
            message['sources']=[]
    return messages
