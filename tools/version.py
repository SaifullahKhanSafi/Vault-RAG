"""Synchronize the monorepo's Semantic Version; no Git operations are performed."""
import argparse
import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SEMVER=re.compile(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?\Z')

def valid(value):
    match=SEMVER.fullmatch(value)
    return bool(match) and not any(part.isdigit() and len(part)>1 and part.startswith('0') for part in (match[4] or '').split('.'))

def check(root=ROOT):
    version=(root/'VERSION').read_text(encoding='utf-8').strip()
    if not valid(version):raise ValueError('VERSION must contain a valid Semantic Version.')
    values={'backend/VERSION':(root/'backend/VERSION').read_text(encoding='utf-8').strip(),
      'frontend/package.json':json.loads((root/'frontend/package.json').read_text(encoding='utf-8'))['version']}
    lock=json.loads((root/'frontend/package-lock.json').read_text(encoding='utf-8'))
    values.update({'frontend/package-lock.json':lock['version'],'frontend lock root package':lock['packages']['']['version']})
    if any(v!=version for v in values.values()):raise ValueError('Version drift: run python tools/version.py --set '+version)
    if f'## [{version}]' not in (root/'CHANGELOG.md').read_text(encoding='utf-8'):raise ValueError('Add a CHANGELOG.md entry for '+version)
    return version

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--set',dest='new_version');parser.add_argument('--check',action='store_true')
    parser.add_argument('--tag',help='Require an exact vVERSION Git tag.');parser.add_argument('--github-output')
    args=parser.parse_args()
    if args.new_version:
        if not valid(args.new_version):parser.error('Invalid Semantic Version.')
        for name in ('VERSION','backend/VERSION'):(ROOT/name).write_text(args.new_version+'\n',encoding='utf-8')
        for name in ('frontend/package.json','frontend/package-lock.json'):
            path=ROOT/name;data=json.loads(path.read_text(encoding='utf-8'));data['version']=args.new_version
            if 'packages' in data:data['packages']['']['version']=args.new_version
            path.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
        print('Updated versions. Add a matching CHANGELOG.md entry before release.');return
    version=check()
    if args.tag and args.tag!='v'+version:parser.error('Tag must exactly match v'+version)
    if args.github_output:
        with Path(args.github_output).open('a',encoding='utf-8') as stream:
            stream.write(f'version={version}\nimage_tag={version.replace("+","_")}\nprerelease={str(bool(SEMVER.fullmatch(version)[4])).lower()}\n')
    print(version)

if __name__=='__main__':main()
