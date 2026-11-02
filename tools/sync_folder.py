"""Incremental PDF folder connector. Operator-run; never follows external symlinks."""
import argparse,hashlib,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from smoke_test import login,checked
from test_support import local_settings

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--folder',required=True)
    parser.add_argument('--workspace',required=True)
    parser.add_argument('--email',help='Defaults to the bootstrap admin; password comes from RAG_SYNC_PASSWORD or local configuration.')
    parser.add_argument('--apply-deletions',action='store_true',help='Move connector-managed documents missing from the source into trash.')
    parser.add_argument('--base-url',default='http://localhost:8000')
    args=parser.parse_args();folder=Path(args.folder).resolve(strict=True)
    if not folder.is_dir():raise SystemExit('Source must be a directory.')
    env=local_settings();client=login(args.base_url,args.email or env['BOOTSTRAP_ADMIN_EMAIL'],os.getenv('RAG_SYNC_PASSWORD',env['BOOTSTRAP_ADMIN_PASSWORD']))
    membership=next((w for w in checked(client.get('/workspaces')) if w['id']==args.workspace),None)
    if not membership or membership['role']!='admin':raise SystemExit('The connector requires administrator access to the target workspace.')
    root=Path(__file__).resolve().parents[1];state_dir=root/'storage'/'connectors';state_dir.mkdir(parents=True,exist_ok=True)
    key=hashlib.sha256((args.workspace+'\0'+str(folder)).encode()).hexdigest()
    destination=state_dir/(key+'.json');state=json.loads(destination.read_text()) if destination.exists() else {}
    present=set();changes=0
    # Checkpoint each successful API mutation. Re-running reconciles duplicate upload responses.
    def save():
        temporary=destination.with_suffix('.tmp');temporary.write_text(json.dumps(state,indent=2));temporary.replace(destination)
    for path in sorted(folder.iterdir()):
        if path.suffix.lower()!='.pdf' or not path.is_file():continue
        if not path.resolve().is_relative_to(folder):raise SystemExit('Refusing a source symlink outside the selected folder.')
        if path.stat().st_size>50*1024*1024:raise SystemExit('Source PDF exceeds the 50 MB upload limit: '+path.name)
        present.add(path.name);digest=hashlib.sha256(path.read_bytes()).hexdigest();old=state.get(path.name)
        if old and old['checksum']==digest and not old.get('deleted'):continue
        if changes>=8:print('Batch limit reached. Run again to continue.');break
        if old and old.get('deleted'):checked(client.post('/documents/'+old['id']+'/restore'))
        endpoint=f"/workspaces/{args.workspace}/documents"+(f"/{old['id']}/versions" if old else '')
        with path.open('rb') as stream:response=client.post(endpoint,files={'file':(path.name,stream,'application/pdf')})
        if response.status_code==409 and old:
            versions=checked(client.get('/documents/'+old['id']+'/versions'))
            if not versions or versions[0]['checksum']!=digest or versions[0]['status']=='failed':response.raise_for_status()
            identity=old['id']
        else:identity=checked(response,202)['id']
        state[path.name]={'id':identity,'checksum':digest,'deleted':False};save();changes+=1
        print('Queued:',path.name)
    else:
        if args.apply_deletions:
            for name,entry in state.items():
                if name not in present and not entry.get('deleted'):
                    checked(client.delete('/documents/'+entry['id']));entry['deleted']=True;save();print('Moved to trash:',name)
    client.close();print('Folder sync complete. New accounts and source folder permissions are not synchronized.')

if __name__=='__main__':main()
