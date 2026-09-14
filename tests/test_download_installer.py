import hashlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/download-install.sh'


class DownloadInstallerTests(unittest.TestCase):
    def exercise(self, bad_checksum=False, missing_checksum=False, download_failure=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = root / 'fixture'
            fixture.mkdir()
            archive = fixture / 'bible-search-1.0.1.tar.gz'
            installer = b'#!/bin/bash\nprintf "%s\\n" "$@" > "$INSTALL_MARKER"\n'
            with tarfile.open(archive, 'w:gz') as output:
                member = tarfile.TarInfo('bible-search-1.0.1/scripts/install.sh')
                member.size = len(installer)
                member.mode = 0o755
                output.addfile(member, io.BytesIO(installer))
            digest = '0' * 64 if bad_checksum else hashlib.sha256(archive.read_bytes()).hexdigest()
            name = 'wrong-file.tar.gz' if missing_checksum else archive.name
            (fixture / 'SHA256SUMS').write_text(f'{digest}  {name}\n')
            fakebin = root / 'bin'
            fakebin.mkdir()
            curl = fakebin / 'curl'
            curl.write_text(f'#!{sys.executable}\n' + '''import os, pathlib, shutil, sys
if os.environ.get('FAIL_DOWNLOAD'):
    sys.exit(22)
args = sys.argv[1:]
source = pathlib.Path(os.environ['FIXTURE']) / args[-1].rsplit('/', 1)[-1]
shutil.copyfile(source, args[args.index('--output') + 1])
''')
            curl.chmod(0o755)
            scratch = root / 'scratch'
            scratch.mkdir()
            marker = root / 'installed'
            env = dict(os.environ, PATH=str(fakebin) + os.pathsep + os.environ['PATH'],
                       FIXTURE=str(fixture), TMPDIR=str(scratch), INSTALL_MARKER=str(marker))
            if download_failure:
                env['FAIL_DOWNLOAD'] = '1'
            result = subprocess.run(['bash', str(SCRIPT), '--bible', '/backend with spaces/bible'],
                                    capture_output=True, text=True, env=env)
            if bad_checksum or missing_checksum or download_failure:
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(marker.exists())
            else:
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(marker.read_text(), '--bible\n/backend with spaces/bible\n')
            self.assertEqual(list(scratch.iterdir()), [], 'temporary files were not cleaned up')

    def test_verified_archive_installs_and_forwards_arguments(self):
        self.exercise()

    def test_corrupt_archive_never_installs(self):
        self.exercise(bad_checksum=True)

    def test_missing_checksum_never_installs(self):
        self.exercise(missing_checksum=True)

    def test_download_failure_never_installs(self):
        self.exercise(download_failure=True)
