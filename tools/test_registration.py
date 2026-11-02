"""Live regression check. Creates two isolated test accounts and one private workspace."""
import secrets
import requests
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from test_support import mail_action

BASE = "http://localhost:8000"
tag = secrets.token_hex(6)
password = secrets.token_urlsafe(24)
email = f"registration-{tag}@example.com"
client = requests.Session()
client.headers["Origin"] = "http://localhost:3000"

def call(method, path, status=200, **kwargs):
    response = client.request(method, BASE + path, timeout=15, **kwargs)
    assert response.status_code == status, (path, response.status_code, response.text)
    return response.json()

call("POST", "/auth/register", 422, json={"name":"Test", "email":email, "password":"short"})
call("POST", "/auth/register", 201, json={"name":"Registration test", "email":email.upper(), "password":password})
call("POST", "/auth/register", 409, json={"name":"Duplicate", "email":email, "password":password})
call('POST','/auth/verify-email',json={'token':mail_action(email,'Verify')})
session = call("POST", "/auth/login", json={"email":email,"password":password})
client.headers["X-CSRF-Token"] = session["csrf_token"]
workspaces = call("GET", "/workspaces")
assert len(workspaces) == 1 and workspaces[0]["role"] == "admin", workspaces
workspace = workspaces[0]["id"]
assert call("GET", f"/workspaces/{workspace}/documents") == []
reader = f"reader-{tag}@example.com"
call("POST", f"/workspaces/{workspace}/users", 201, json={"email":reader,"name":"Reader test","password":password,"role":"reader"})
call("POST", "/auth/logout")
session = call("POST", "/auth/login", json={"email":reader,"password":password})
client.headers["X-CSRF-Token"] = session["csrf_token"]
assert call("GET", "/workspaces")[0]["role"] == "reader"
call("GET", f"/workspaces/{workspace}/documents")
call("POST", f"/workspaces/{workspace}/users", 403, json={"email":f"denied-{tag}@example.com","name":"Denied","password":password,"role":"admin"})
call("GET", "/workspaces/00000000-0000-0000-0000-000000000001/documents", 403)
call("POST", "/auth/logout")
print("PASS: registration, validation, duplicate handling, private workspace, reader login, and permission boundaries.")
