import hashlib
import json
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.package_release import allowed,archive,package,sources
from tools.verify_release import verify
from tools.version import valid,check

class ReleaseTests(unittest.TestCase):
    def fixture(self,root):
        names=['VERSION','backend/VERSION','frontend/package.json','frontend/package-lock.json','CHANGELOG.md',
          'deploy/compose.production.yaml','deploy/nginx.conf','deploy/prometheus.yml','deploy/alerts.yml','deploy/DEPLOYMENT.md','deploy/production.env.example','tools/setup_env.py']
        for name in names:
            dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
        for name in ('VERSION','backend/VERSION'):(root/name).write_text('0.1.0\n')
        for name in ('frontend/package.json','frontend/package-lock.json'):
            file=root/name;data=json.loads(file.read_text());data['version']='0.1.0'
            if 'packages' in data:data['packages']['']['version']='0.1.0'
            file.write_text(json.dumps(data))
        (root/'CHANGELOG.md').write_text('## [0.1.0]\nFixture release\n')

    def test_allowlist_excludes_private_and_generated_files(self):
        for name in ['.env','.env.production','backend/.env.local','backend/venv/secret.py','backend/data/key.txt',
          'frontend/node_modules/package/index.js','frontend/.next/server.js','evals/private/custom.json','docs/private/key.json',
          'storage/report.pdf','backups/database.dump','output/report.json','backend/../tools/setup_env.py']:
            self.assertFalse(allowed(Path(name)),name)
        for name in ['.env.example','backend/VERSION','backend/main.py','frontend/components/document-card.tsx',
          'frontend/scripts/start-e2e.mjs','deploy/production.env.example','.github/workflows/ci.yml','docs/benchmarks/pilot-summary.json']:
            self.assertTrue(allowed(Path(name)),name)

    def test_deterministic_archives_and_private_file_omission(self):
        with tempfile.TemporaryDirectory(prefix='rag-release-test-') as temp:
            root=Path(temp)/'source';self.fixture(root)
            (root/'.env').write_text('AUTH_SECRET=must-never-be-packaged')
            private=root/'backend/data';private.mkdir();(private/'credentials.txt').write_text('private')
            one=Path(temp)/'one';two=Path(temp)/'two'
            package(one,root=root,epoch=1234);package(two,root=root,epoch=1234)
            for name in ['enterprise-rag-0.1.0-source.tar.gz','enterprise-rag-0.1.0-deploy.tar.gz']:
                self.assertEqual((one/name).read_bytes(),(two/name).read_bytes())
            with tarfile.open(one/'enterprise-rag-0.1.0-source.tar.gz') as bundle:
                names=bundle.getnames();self.assertFalse(any(n.endswith('/.env') or '/data/' in n for n in names))
            verify(one)
            with self.assertRaisesRegex(ValueError,'Preview'):verify(one,require_deployable=True)
            with self.assertRaises(ValueError):package(one,root=root)

    def test_digest_pinned_bundle_and_tamper_detection(self):
        with tempfile.TemporaryDirectory(prefix='rag-release-test-') as temp:
            root=Path(temp)/'source';self.fixture(root);out=Path(temp)/'package'
            package(out,backend_digest='sha256:'+'a'*64,frontend_digest='sha256:'+'b'*64,revision='c'*40,root=root)
            result=verify(out,tag='v0.1.0',revision='c'*40,registry='ghcr.io/example/enterprise-rag',require_deployable=True)
            self.assertTrue(result['backend_image'].endswith('@sha256:'+'a'*64))
            file=out/result['archive'];file.write_bytes(file.read_bytes()+b'tampered')
            with self.assertRaisesRegex(ValueError,'checksum'):verify(out)

    def test_archive_path_traversal_is_rejected_even_with_updated_outer_hash(self):
        with tempfile.TemporaryDirectory(prefix='rag-release-test-') as temp:
            root=Path(temp)/'source';self.fixture(root);out=Path(temp)/'package';package(out,root=root)
            name='enterprise-rag-0.1.0-deploy.tar.gz';file=out/name
            with tarfile.open(file) as bundle:contents={item.name.split('/',1)[1]:bundle.extractfile(item).read() for item in bundle}
            file.unlink();contents['../escape']=b'bad';archive(file,contents,'enterprise-rag-0.1.0')
            sums=(out/'SHA256SUMS').read_text();old=next(line.split()[0] for line in sums.splitlines() if line.endswith(name))
            (out/'SHA256SUMS').write_text(sums.replace(old,hashlib.sha256(file.read_bytes()).hexdigest()))
            with self.assertRaisesRegex(ValueError,'Unsafe'):verify(out)

    def test_source_checksum_and_deployment_only_download(self):
        with tempfile.TemporaryDirectory(prefix='rag-release-test-') as temp:
            root=Path(temp)/'source';self.fixture(root);out=Path(temp)/'package';package(out,root=root)
            source=out/'enterprise-rag-0.1.0-source.tar.gz';original=source.read_bytes()
            source.write_bytes(original+b'tampered')
            with self.assertRaisesRegex(ValueError,'checksum'):verify(out)
            source.unlink() # Deployment downloads contain only metadata and the deploy archive.
            verify(out)

    def test_semver_and_version_drift(self):
        for value in ['0.1.0','1.2.3-rc.1','1.2.3+build.7']:self.assertTrue(valid(value))
        for value in ['v0.1.0','01.2.3','1.2','1.2.3-01','1.2.3\n','1\u0662.2.3']:self.assertFalse(valid(value))
        with tempfile.TemporaryDirectory(prefix='rag-release-test-') as temp:
            root=Path(temp);self.fixture(root);check(root)
            (root/'backend/VERSION').write_text('99.0.0\n')
            with self.assertRaisesRegex(ValueError,'Version drift'):check(root)

if __name__=='__main__':unittest.main()
