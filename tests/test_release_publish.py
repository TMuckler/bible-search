import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/publish_release.sh'


class ReleasePublishTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'scripts').mkdir()
        (self.root / 'dist').mkdir()
        (self.root / 'bin').mkdir()
        (self.root / 'remote/assets').mkdir(parents=True)
        shutil.copy2(SCRIPT, self.root / 'scripts/publish_release.sh')
        self.assets = {
            'bible-search-1.0.2.tar.gz': b'archive',
            'install.sh': b'installer',
            'SHA256SUMS': b'checksums',
        }
        for name, data in self.assets.items():
            (self.root / 'dist' / name).write_bytes(data)
        (self.root / 'dist/release-notes.md').write_text('notes')
        gh = self.root / 'bin/gh'
        gh.write_text('#!' + sys.executable + '\n' + textwrap.dedent('''
            import os, pathlib, shutil, sys
            root = pathlib.Path(os.environ['FAKE_RELEASE'])
            args = sys.argv[1:]
            if args[:2] == ['release', 'view']:
                if not (root / 'exists').exists():
                    raise SystemExit(1)
                if '--json' in args:
                    print('\\n'.join(path.name for path in (root / 'assets').iterdir()))
            elif args[:2] == ['release', 'download']:
                name = args[args.index('--pattern') + 1]
                destination = pathlib.Path(args[args.index('--dir') + 1])
                shutil.copy2(root / 'assets' / name, destination / name)
            elif args[:2] == ['release', 'upload']:
                for item in args[3:]:
                    source = pathlib.Path(item)
                    destination = root / 'assets' / source.name
                    if destination.exists():
                        raise SystemExit(2)
                    shutil.copy2(source, destination)
            elif args[:2] == ['release', 'create']:
                (root / 'exists').touch()
                for item in args[3:]:
                    if item.startswith('--'):
                        break
                    source = pathlib.Path(item)
                    shutil.copy2(source, root / 'assets' / source.name)
            else:
                raise SystemExit('unexpected gh arguments: ' + repr(args))
        '''))
        gh.chmod(0o755)
        subprocess.run(['git', 'init', '-q'], cwd=self.root, check=True)
        subprocess.run(['git', 'config', 'user.email', 'test@example.com'], cwd=self.root, check=True)
        subprocess.run(['git', 'config', 'user.name', 'Test'], cwd=self.root, check=True)
        subprocess.run(['git', 'add', '.'], cwd=self.root, check=True)
        subprocess.run(['git', 'commit', '-qm', 'release'], cwd=self.root, check=True)
        subprocess.run(['git', 'tag', 'v1.0.2'], cwd=self.root, check=True)
        self.env = dict(os.environ, PATH=str(self.root / 'bin') + os.pathsep + os.environ['PATH'],
                        FAKE_RELEASE=str(self.root / 'remote'), RELEASE_TAG='v1.0.2')

    def tearDown(self):
        self.temp.cleanup()

    def run_publish(self):
        return subprocess.run(['bash', 'scripts/publish_release.sh'], cwd=self.root,
                              capture_output=True, text=True, env=self.env)

    def test_existing_release_verifies_assets_and_uploads_only_missing(self):
        (self.root / 'remote/exists').touch()
        for name in ('bible-search-1.0.2.tar.gz', 'install.sh'):
            (self.root / 'remote/assets' / name).write_bytes(self.assets[name])
        first = self.run_publish()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual((self.root / 'remote/assets/SHA256SUMS').read_bytes(), b'checksums')
        second = self.run_publish()
        self.assertEqual(second.returncode, 0, second.stderr)

    def test_existing_different_asset_is_never_overwritten(self):
        (self.root / 'remote/exists').touch()
        archive = self.root / 'remote/assets/bible-search-1.0.2.tar.gz'
        archive.write_bytes(b'different published bytes')
        result = self.run_publish()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('refusing to overwrite', result.stderr)
        self.assertEqual(archive.read_bytes(), b'different published bytes')

    def test_new_release_publishes_all_assets(self):
        result = self.run_publish()
        self.assertEqual(result.returncode, 0, result.stderr)
        published = {path.name: path.read_bytes() for path in (self.root / 'remote/assets').iterdir()}
        self.assertEqual(published, self.assets)


if __name__ == '__main__':
    unittest.main()
