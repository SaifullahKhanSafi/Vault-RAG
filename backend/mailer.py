"""Retryable SMTP outbox. Local Compose sends exclusively to Mailpit."""
import logging
import os
import smtplib
import ssl
import time
from email.message import EmailMessage
from db import connect

def deliver_once():
    with connect() as conn:
        row=conn.execute("SELECT * FROM rag_mail_outbox WHERE sent_at IS NULL AND attempts<8 AND available_at<=now() ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1").fetchone()
        if not row:return False
        try:
            message=EmailMessage()
            message['From']=os.getenv('SMTP_FROM','Enterprise RAG <noreply@localhost>')
            message['To']=row['recipient'];message['Subject']=row['subject'];message.set_content(row['body'])
            with smtplib.SMTP(os.getenv('SMTP_HOST','mailpit'),int(os.getenv('SMTP_PORT','1025')),timeout=10) as smtp:
                if os.getenv('SMTP_STARTTLS','false').lower()=='true':smtp.starttls(context=ssl.create_default_context())
                if os.getenv('SMTP_USERNAME'):smtp.login(os.environ['SMTP_USERNAME'],os.environ['SMTP_PASSWORD'])
                smtp.send_message(message)
            conn.execute("UPDATE rag_mail_outbox SET sent_at=now(),body='' WHERE id=%s",(row['id'],))
        except (OSError,smtplib.SMTPException):
            conn.execute("UPDATE rag_mail_outbox SET attempts=attempts+1,available_at=now()+interval '30 seconds' WHERE id=%s",(row['id'],))
            logging.warning('mail_delivery_failed id=%s',row['id'])
        return True

if __name__=='__main__':
    while True:
        try:
            if not deliver_once():time.sleep(2)
        except Exception:
            logging.exception('mail_outbox_failed');time.sleep(5)
