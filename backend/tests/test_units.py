import asyncio
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.datastructures import UploadFile
from security import password_hash,password_matches,validate_password,require_role,csrf_token
from storage import save_upload,storage_path
from main import app
from routers.query import QueryRequest,source_for
from test_support import fixture_pdf

class SecurityTests(unittest.TestCase):
    def test_registration_validation_and_disable_switch(self):
        from routers.accounts import Registration
        from pydantic import ValidationError
        result=Registration(name=" New User ",email=" PERSON@EXAMPLE.COM ",password="a long test password")
        self.assertEqual(result.name,"New User")
        self.assertEqual(result.email,"person@example.com")
        for invalid in [{"name":" ","email":"person@example.com"},{"name":"Person","email":"invalid"}]:
            with self.assertRaises(ValidationError):Registration(**invalid,password="a long test password")
        with patch("main.record_http"),patch.dict(os.environ,{"ALLOW_REGISTRATION":"false"}):
            response=TestClient(app).post("/auth/register",json=result.model_dump(),headers={"Origin":"http://localhost:3000"})
            self.assertEqual(response.status_code,403)

    def test_registration_rejects_untrusted_origin(self):
        with patch("main.record_http"):
            response=TestClient(app).post("/auth/register",json={"name":"Person","email":"person@example.com","password":"a long test password"},headers={"Origin":"https://untrusted.example"})
            self.assertEqual(response.status_code,403)

    def test_password_hash_is_salted_and_verified(self):
        first=password_hash("Example test password 29")
        second=password_hash("Example test password 29")
        self.assertNotEqual(first,second)
        self.assertTrue(password_matches("Example test password 29",first))
        self.assertFalse(password_matches("wrong",first))
        self.assertFalse(password_matches("wrong","malformed"))

    def test_password_policy(self):
        for password in ["short","x"*257]:
            with self.assertRaises(HTTPException):validate_password(password)

    def test_csrf_is_session_specific(self):
        self.assertNotEqual(csrf_token("one"),csrf_token("two"))
        self.assertEqual(csrf_token("one"),csrf_token("one"))

    def test_reader_cannot_write(self):
        conn=Mock()
        conn.execute.return_value.fetchone.return_value={"role":"reader"}
        with self.assertRaises(HTTPException):require_role(conn,"workspace",("admin","editor"))

    def test_anonymous_api_is_blocked(self):
        with patch("main.record_http"):
            client=TestClient(app)
            for path in ["/workspaces","/auth/me","/documents/00000000-0000-0000-0000-000000000001/file",
                         "/documents/00000000-0000-0000-0000-000000000001/extraction",
                         "/conversations/00000000-0000-0000-0000-000000000001"]:
                self.assertEqual(client.get(path).status_code,401)

    def test_query_contract_does_not_accept_client_history_as_authority(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):QueryRequest(workspace_id="bad",question="hello")
        with self.assertRaises(ValidationError):QueryRequest(workspace_id="00000000-0000-0000-0000-000000000001",question=" ")
        result=QueryRequest(workspace_id="00000000-0000-0000-0000-000000000001",question=" question ")
        self.assertEqual(result.question,"question")

class StorageTests(unittest.TestCase):
    def test_storage_traversal_rejected(self):
        with self.assertRaises(ValueError):storage_path("../escape.pdf")

    def test_valid_file_saved_with_checksum_and_closed(self):
        import hashlib
        data=fixture_pdf()
        with tempfile.TemporaryDirectory() as directory,patch("storage.ROOT",Path(directory).resolve()):
            stream=io.BytesIO(data)
            key,digest,size=save_upload(UploadFile(stream,filename="../../example.pdf"))
            self.assertEqual(storage_path(key).read_bytes(),data)
            self.assertEqual(digest,hashlib.sha256(data).hexdigest())
            self.assertEqual(size,len(data))
            self.assertTrue(stream.closed)

    def test_invalid_or_oversized_upload_leaves_no_file(self):
        for data,limit,status in [(b"invalid",100,400),(b"%PDF-"+b"x"*20,10,413)]:
            with tempfile.TemporaryDirectory() as directory,patch("storage.ROOT",Path(directory).resolve()),patch("storage.MAX_UPLOAD_BYTES",limit):
                with self.assertRaises(HTTPException) as caught:save_upload(UploadFile(io.BytesIO(data),filename="x.pdf"))
                self.assertEqual(caught.exception.status_code,status)
                self.assertEqual(list(Path(directory).iterdir()),[])

if __name__=="__main__":unittest.main()
