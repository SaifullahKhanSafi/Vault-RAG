"""Generate private local or production credentials, preserving existing real values."""
import argparse
from pathlib import Path
import secrets

parser=argparse.ArgumentParser()
parser.add_argument("--production",action="store_true")
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
path=root/(".env.production" if args.production else ".env")
existing={}
if path.exists():
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k,v=line.split("=",1);existing[k]=v
defaults={"BOOTSTRAP_ADMIN_EMAIL":"admin@localhost","BOOTSTRAP_ADMIN_PASSWORD":secrets.token_urlsafe(24),
          "APP_DB_PASSWORD":secrets.token_urlsafe(24),"WORKER_DB_PASSWORD":secrets.token_urlsafe(24),
          "AUTH_SECRET":secrets.token_urlsafe(48),"METRICS_TOKEN":secrets.token_urlsafe(32),
          "KEYCLOAK_ADMIN_PASSWORD":secrets.token_urlsafe(24)}
if args.production:
    defaults.update(POSTGRES_PASSWORD=secrets.token_urlsafe(32),PUBLIC_ORIGIN="https://rag.example.com")
for key,value in defaults.items():
    if not existing.get(key) or existing[key].startswith(("GENERATE_","CHANGE_")):
        existing[key]=value
path.write_text("\n".join(f"{k}={v}" for k,v in existing.items())+"\n",encoding="utf-8")
directory=root/(".secrets.production" if args.production else ".secrets")
directory.mkdir(exist_ok=True)
token=directory/"metrics_token"
token.write_text(existing["METRICS_TOKEN"],encoding="utf-8")
try:path.chmod(0o600);directory.chmod(0o700);token.chmod(0o644)
except OSError:pass
print(f"Credentials are in {path.name}; secret values were not printed. Keep that file private.")
if args.production:print("Set PUBLIC_ORIGIN to your actual HTTPS origin before deploying.")
