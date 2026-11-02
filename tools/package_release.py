"""Build allowlisted, deterministic source and deployment archives. Never reads .env."""
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tarfile

import yaml
try:
    from .version import ROOT,check
except ImportError:
    from version import ROOT,check

ROOT_FILES={'VERSION','README.md','CHANGELOG.md','BENCHMARKING.md','BENCHMARK_RESULTS.md','OPEN_SOURCE_FEATURES.md',
  'FEATURE_ROADMAP.md','IMPLEMENTATION_NOTES.md','PROJECT_REVIEW.md','.env.example','.gitignore','.dockerignore','.gitattributes','docker-compose.yaml'}
WEB_FILES={'README.md','package.json','package-lock.json','tsconfig.json','next.config.ts','postcss.config.mjs','eslint.config.mjs',
  'Dockerfile','.dockerignore','.gitignore','playwright.config.ts'}
DENIED_PARTS={'node_modules','venv','.venv','__pycache__','.next','.git','private','test-results','playwright-report','data','storage','backups','output','tmp','dist'}
SECRET_SUFFIXES={'.pem','.key','.p12','.pfx','.pdf','.log','.dump'}

def allowed(path):
    parts=path.parts
    if path.is_absolute() or '..' in parts:return False
    if any(p in DENIED_PARTS or p.startswith('.secrets') for p in parts):return False
    if path.suffix.lower() in SECRET_SUFFIXES:return False
    if path.name.startswith('.env') and not path.name.endswith('.example'):return False
    if len(parts)==1:return path.name in ROOT_FILES
    top=parts[0]
    if top=='backend':return path.suffix in {'.py','.sql','.txt','.lock'} or path.name in {'VERSION','Dockerfile','.dockerignore'}
    if top=='frontend':return (len(parts)==2 and path.name in WEB_FILES) or (parts[1] in {'app','components','lib','public','tests','e2e','scripts'} and path.suffix in {'.ts','.tsx','.mjs','.js','.css','.svg','.png','.ico','.json'})
    if top=='tools':return len(parts)==2 and path.suffix=='.py'
    if top=='deploy':return path.suffix in {'.yaml','.yml','.conf','.json','.md','.sh'} or path.name.endswith('.env.example')
    if top=='evals':return len(parts)==2 and path.suffix=='.json'
    if top=='.github':return path.suffix in {'.yml','.yaml','.md'}
    if top=='docs':return path.suffix in {'.md','.png','.svg','.json','.csv'}
    return False

def sources(root=ROOT):
    result={}
    # Traverse only source directories, so ignored multi-GB caches are never scanned.
    for name in ROOT_FILES:
        file=root/name
        if file.is_file() and not file.is_symlink():result[name]=file.read_bytes()
    def visit(directory):
        for file in sorted(directory.iterdir()):
            if file.is_symlink():continue
            relative=file.relative_to(root)
            if file.is_dir():
                if file.name not in DENIED_PARTS and not file.name.startswith('.'):visit(file)
            elif allowed(relative):result[relative.as_posix()]=file.read_bytes()
    for name in ('backend','frontend','tools','deploy','evals','.github','docs'):
        if (root/name).is_dir():visit(root/name)
    return result

def archive(path,files,prefix,epoch=0):
    if path.exists():raise ValueError('Refusing to replace package: '+str(path))
    with path.open('wb') as raw,gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=epoch) as zipped,tarfile.open(fileobj=zipped,mode='w',format=tarfile.PAX_FORMAT) as bundle:
        for name,data in sorted(files.items()):
            item=tarfile.TarInfo(prefix+'/'+name);item.size=len(data);item.mtime=epoch;item.mode=0o755 if name.endswith('.sh') else 0o644
            bundle.addfile(item,io.BytesIO(data))

def package(out,registry='ghcr.io/example/enterprise-rag',backend_digest=None,frontend_digest=None,revision='unknown',epoch=0,root=ROOT):
    version=check(root)
    if not re.fullmatch(r'ghcr\.io/[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._-]*',registry):raise ValueError('Use a lowercase ghcr.io/owner/repository registry prefix.')
    if bool(backend_digest)!=bool(frontend_digest):raise ValueError('Supply both image digests or neither.')
    for digest in (backend_digest,frontend_digest):
        if digest and not re.fullmatch(r'sha256:[0-9a-f]{64}',digest):raise ValueError('Invalid image digest.')
    if revision!='unknown' and not re.fullmatch('[0-9a-f]{40}',revision):raise ValueError('Revision must be a full Git commit hash.')
    tag=version.replace('+','_');prefix='enterprise-rag-'+version
    image=lambda component,digest:registry+'/'+component+('@'+digest if digest else ':'+tag)
    metadata={'schema_version':1,'version':version,'tag':'v'+version,'revision':revision,'platform':'linux/amd64',
      'deployable':bool(backend_digest and frontend_digest),'backend_image':image('backend',backend_digest),'frontend_image':image('frontend',frontend_digest)}
    compose=yaml.safe_load((root/'deploy/compose.production.yaml').read_text(encoding='utf-8'))
    for name,service in compose['services'].items():
        service.pop('build',None)
        if name in ('backend','worker','migrate','mailer'):service['image']='${RAG_BACKEND_IMAGE:?Missing immutable backend image}'
        if name=='frontend':service['image']='${RAG_FRONTEND_IMAGE:?Missing immutable frontend image}'
    compose['services']['prometheus']['volumes']=[volume.replace('../.secrets.production/','${RAG_SECRETS_DIR:-../.secrets.production}/') for volume in compose['services']['prometheus']['volumes']]
    files={name:(root/name).read_bytes() for name in ('VERSION','tools/setup_env.py','deploy/nginx.conf','deploy/prometheus.yml','deploy/alerts.yml','deploy/DEPLOYMENT.md','deploy/production.env.example')}
    files['deploy/compose.release.yaml']=yaml.safe_dump(compose,sort_keys=False).encode()
    files['release.env']=(f"RAG_BACKEND_IMAGE={metadata['backend_image']}\nRAG_FRONTEND_IMAGE={metadata['frontend_image']}\n").encode()
    encoded=(json.dumps(metadata,indent=2)+'\n').encode();files['release.json']=encoded
    files['checksums.sha256']=''.join(f'{hashlib.sha256(data).hexdigest()}  {name}\n' for name,data in sorted(files.items())).encode()
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()):raise ValueError('Choose an empty output directory; existing files are preserved.')
    archive(out/(prefix+'-source.tar.gz'),sources(root),prefix,epoch)
    archive(out/(prefix+'-deploy.tar.gz'),files,prefix,epoch)
    (out/'release.json').write_bytes(encoded)
    (out/'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(file.read_bytes()).hexdigest()}  {file.name}\n' for file in sorted(out.iterdir()) if file.is_file() and file.name!='SHA256SUMS'),encoding='utf-8')
    return metadata

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',default='dist')
    parser.add_argument('--registry',default='ghcr.io/example/enterprise-rag');parser.add_argument('--backend-digest');parser.add_argument('--frontend-digest')
    parser.add_argument('--revision',default='unknown');args=parser.parse_args()
    metadata=package(args.output,args.registry,args.backend_digest,args.frontend_digest,args.revision,int(os.getenv('SOURCE_DATE_EPOCH','0')))
    print(json.dumps(metadata,indent=2));print('Packages and SHA256SUMS:',args.output)

if __name__=='__main__':main()
