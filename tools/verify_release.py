"""Verify release checksums, archive paths and immutable application image references."""
import argparse
import hashlib
import io
import json
from pathlib import Path,PurePosixPath
import re
import subprocess
import tarfile
import tempfile

try:
    from .version import valid
except ImportError:
    from version import valid

def verify(directory,tag=None,revision=None,registry=None,require_deployable=False):
    directory=Path(directory);metadata=json.loads((directory/'release.json').read_text(encoding='utf-8'))
    version=metadata['version']
    if not valid(version) or metadata.get('tag')!='v'+version:raise ValueError('Invalid release version/tag.')
    if tag and tag!=metadata['tag']:raise ValueError('Release tag mismatch.')
    if revision and revision!=metadata.get('revision'):raise ValueError('Release commit mismatch.')
    if metadata.get('schema_version')!=1 or metadata.get('platform')!='linux/amd64':raise ValueError('Unsupported release format/platform.')
    if require_deployable and metadata.get('deployable') is not True:raise ValueError('Preview bundles cannot be deployed; release requires image digests.')
    for component in ('backend','frontend'):
        image=metadata[component+'_image']
        prefix=(registry+'/'+component) if registry else r'ghcr\.io/[a-z0-9._-]+/[a-z0-9._-]+/'+component
        pattern=(re.escape(prefix) if registry else prefix)+(r'@sha256:[0-9a-f]{64}' if metadata['deployable'] else r':[A-Za-z0-9_.-]+')
        if not re.fullmatch(pattern,image):raise ValueError('Unexpected image reference.')
    checksums={}
    for line in (directory/'SHA256SUMS').read_text(encoding='utf-8').splitlines():
        digest,name=line.split('  ',1)
        if not re.fullmatch(r'[0-9a-f]{64}',digest) or '/' in name or '\\' in name or name in checksums:raise ValueError('Invalid external checksum manifest.')
        checksums[name]=digest
    name=f'enterprise-rag-{version}-deploy.tar.gz'
    source_name=f'enterprise-rag-{version}-source.tar.gz'
    if set(checksums)!={name,source_name,'release.json'}:raise ValueError('Unexpected release checksum manifest contents.')
    for required in (name,'release.json'):
        if required not in checksums or hashlib.sha256((directory/required).read_bytes()).hexdigest()!=checksums[required]:raise ValueError('Release checksum mismatch: '+required)
    # Deployment downloads omit the source archive; local/full release checks verify it when present.
    if (directory/source_name).exists() and hashlib.sha256((directory/source_name).read_bytes()).hexdigest()!=checksums[source_name]:raise ValueError('Release checksum mismatch: '+source_name)
    contents={};prefix=f'enterprise-rag-{version}/'
    with tarfile.open(directory/name,'r:gz') as archive:
        for item in archive:
            path=PurePosixPath(item.name)
            if not item.isfile() or not item.name.startswith(prefix) or '..' in path.parts or '\\' in item.name or path.is_absolute():raise ValueError('Unsafe archive member.')
            relative=item.name[len(prefix):]
            if relative in contents:raise ValueError('Duplicate archive member.')
            contents[relative]=archive.extractfile(item).read()
    if contents.get('release.json')!=(directory/'release.json').read_bytes():raise ValueError('Embedded metadata mismatch.')
    if contents.get('VERSION',b'').decode().strip()!=version:raise ValueError('Embedded version mismatch.')
    expected_env=f"RAG_BACKEND_IMAGE={metadata['backend_image']}\nRAG_FRONTEND_IMAGE={metadata['frontend_image']}\n".encode()
    if contents.get('release.env')!=expected_env:raise ValueError('Embedded image configuration mismatch.')
    expected={}
    for line in contents['checksums.sha256'].decode().splitlines():
        digest,filename=line.split('  ',1)
        if filename in expected or not re.fullmatch(r'[0-9a-f]{64}',digest):raise ValueError('Invalid embedded checksum manifest.')
        expected[filename]=digest
    if set(expected)!=set(contents)-{'checksums.sha256'}:raise ValueError('Incomplete embedded checksum manifest.')
    if any(hashlib.sha256(contents[file]).hexdigest()!=digest for file,digest in expected.items()):raise ValueError('Embedded content checksum mismatch.')
    return {**metadata,'archive':name,'archive_sha256':checksums[name]}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory');parser.add_argument('--tag');parser.add_argument('--revision');parser.add_argument('--registry')
    parser.add_argument('--require-deployable',action='store_true');parser.add_argument('--github-output')
    parser.add_argument('--check-compose',action='store_true',help='Validate the released Compose configuration using its public template, never private credentials.');args=parser.parse_args()
    result=verify(args.directory,args.tag,args.revision,args.registry,args.require_deployable)
    if args.check_compose:
        with tempfile.TemporaryDirectory(prefix='rag-compose-check-') as temp:
            with tarfile.open(Path(args.directory)/result['archive'],'r:gz') as bundle:bundle.extractall(temp,filter='data')
            root=Path(temp)/('enterprise-rag-'+result['version'])
            subprocess.run(['docker','compose','--env-file',str(root/'deploy/production.env.example'),'--env-file',str(root/'release.env'),
              '-f',str(root/'deploy/compose.release.yaml'),'config','--quiet'],check=True)
    if args.github_output:
        with Path(args.github_output).open('a',encoding='utf-8') as stream:
            for key in ('version','archive','archive_sha256'):stream.write(f'{key}={result[key]}\n')
    print('Verified release',result['tag'],'commit',result['revision'],'deployable:',result['deployable'])

if __name__=='__main__':main()
