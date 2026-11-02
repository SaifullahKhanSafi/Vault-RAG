"""CI-only Ollama protocol test double. Never use for answer-quality evaluation."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import re

MODELS=["qwen2.5:7b-instruct","nomic-embed-text:latest"]
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send(self,value,status=200,content_type="application/json"):
        body=value if isinstance(value,bytes) else json.dumps(value).encode()
        self.send_response(status);self.send_header("Content-Type",content_type);self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)
    def do_GET(self):
        if self.path in ("/api/tags","/api/ps"):return self.send({"models":[{"name":name,"model":name} for name in MODELS]})
        self.send({"error":"not found"},404)
    def do_POST(self):
        data=json.loads(self.rfile.read(int(self.headers.get("Content-Length","0"))))
        if self.path=="/api/embed":
            value=data.get("input",[])
            count=len(value) if isinstance(value,list) else 1
            return self.send({"embeddings":[[.01]*768 for _ in range(count)]})
        if self.path=="/api/chat":
            messages=data.get("messages",[])
            system=messages[0].get("content","") if messages else ""
            question=messages[-1].get("content","").lower() if messages else ""
            if system.startswith("Rewrite"):
                answer="Who coordinates Project Cedar?"
            elif "code" in question:
                code=re.search(r"CEDAR-[A-Z0-9-]+",system)
                answer="The approval code is "+(code.group() if code else "CEDAR-7421")+". [cedar.pdf, p. 1]"
            elif "coordinat" in question:
                answer="Project Cedar is coordinated by Mira Shah. [cedar.pdf, p. 1]"
            else:answer="I cannot find the answer in the provided documents."
            record={"model":data.get("model"),"created_at":"2026-01-01T00:00:00Z","message":{"role":"assistant","content":answer},"done":True}
            if data.get("stream",True):
                chunks=[{**record,"message":{"role":"assistant","content":word+" "},"done":False} for word in answer.split()]
                chunks.append({**record,"message":{"role":"assistant","content":""}})
                return self.send(("\n".join(json.dumps(c) for c in chunks)+"\n").encode(),content_type="application/x-ndjson")
            return self.send(record)
        self.send({"error":"not found"},404)

if __name__=="__main__":
    ThreadingHTTPServer(("127.0.0.1",11435),Handler).serve_forever()
