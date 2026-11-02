"""Reusable disposable PDF fixtures and local test configuration."""
import io
import os
import re
import time
from pathlib import Path
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject,DictionaryObject,NameObject

def mail_action(email,subject,timeout=30):
    """Read a test token from local Mailpit only. Never print the message or token."""
    import httpx
    from urllib.parse import urlparse,parse_qs
    deadline=time.monotonic()+timeout
    with httpx.Client(base_url='http://localhost:8025',timeout=5) as client:
        while time.monotonic()<deadline:
            result=client.get('/api/v1/messages').json()
            for summary in result.get('messages',[]):
                if subject.lower() not in summary.get('Subject','').lower():continue
                if not any(recipient.get('Address','').lower()==email.lower() for recipient in summary.get('To',[])):continue
                message=client.get('/api/v1/message/'+summary['ID']).json()
                match=re.search(r'https?://[^\s]+',message.get('Text',''))
                if match:return parse_qs(urlparse(match.group()).fragment)['token'][0]
            time.sleep(.5)
    raise AssertionError('Expected test email did not arrive in local Mailpit.')

def local_settings():
    result={}
    path=Path(__file__).resolve().parents[1]/".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key,value=line.split("=",1);result[key]=value
    return {**result,**os.environ}

def fixture_pdf(code="CEDAR-7421",blank=False):
    writer=PdfWriter()
    page=writer.add_blank_page(width=612,height=792)
    if not blank:
        font=DictionaryObject({NameObject("/Type"):NameObject("/Font"),NameObject("/Subtype"):NameObject("/Type1"),NameObject("/BaseFont"):NameObject("/Helvetica")})
        page[NameObject("/Resources")]=DictionaryObject({NameObject("/Font"):DictionaryObject({NameObject("/F1"):writer._add_object(font)})})
        content=DecodedStreamObject()
        lines=["Project Cedar acceptance handbook.",f"The approval code for Project Cedar is {code}.",
               "Project Cedar is coordinated by Mira Shah.","Project Cedar launches on 12 November 2026.",
               "Project Cedar has a budget of 42000 dollars.","The review interval is fourteen days.",
               "The support email is cedar@example.test.","Project Cedar uses encrypted PostgreSQL backups.",
               "The document retention period is ninety days.","The escalation contact is Omar Reed.",
               "No office safe PIN or employee salary is provided in this handbook."]
        commands="BT /F1 11 Tf 40 750 Td "+" 0 -20 Td ".join("("+x+") Tj" for x in lines)+" ET"
        content.set_data(commands.encode("ascii"))
        page[NameObject("/Contents")]=writer._add_object(content)
    output=io.BytesIO();writer.write(output)
    return output.getvalue()
