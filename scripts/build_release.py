#!/usr/bin/env python3
"""Build a reproducible source release from a clean committed checkout."""
import argparse
import gzip
import hashlib
import io
from pathlib import Path
import re
import subprocess
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tag', help='Reject a tag that differs from the package version')
    args = parser.parse_args()
    if git('status', '--porcelain').strip():
        raise SystemExit('Commit all changes before building a release.')
    version = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']['version']
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise SystemExit('Expected a stable major.minor.patch version')
    if args.tag and args.tag != f'v{version}':
        raise SystemExit('Git tag and package version do not match')
    bootstrap = (ROOT / 'scripts/download-install.sh').read_bytes()
    if f"version='{version}'".encode() not in bootstrap:
        raise SystemExit('Download installer version does not match package version')
    init = (ROOT / 'src/bible_search/__init__.py').read_text()
    if f"__version__ = '{version}'" not in init:
        raise SystemExit('Python package version does not match metadata')
    output = ROOT / 'dist'
    output.mkdir(exist_ok=True)
    archive_name = f'bible-search-{version}.tar.gz'
    tar = git('archive', '--format=tar', f'--prefix=bible-search-{version}/', 'HEAD')
    compressed = io.BytesIO()
    with gzip.GzipFile(filename='', mode='wb', fileobj=compressed, mtime=0) as stream:
        stream.write(tar)
    assets = {archive_name: compressed.getvalue(), 'install.sh': bootstrap}
    for name, data in assets.items():
        (output / name).write_bytes(data)
    (output / 'SHA256SUMS').write_text(''.join(
        f'{hashlib.sha256(data).hexdigest()}  {name}\n' for name, data in assets.items()))
    changelog = (ROOT / 'CHANGELOG.md').read_text()
    notes = re.search(rf'^## {re.escape(version)}[^\n]*\n(.*?)(?=^## |\Z)',
                      changelog, re.MULTILINE | re.DOTALL)
    if not notes:
        raise SystemExit('Missing changelog section for this release')
    (output / 'release-notes.md').write_text(notes.group(1).strip() + '\n\n'
        '### Install\n\n```bash\n'
        f'curl -fsSL https://github.com/TMuckler/bible-search/releases/download/v{version}/install.sh | bash\n'
        '```\n\nOr download the `.tar.gz` and `SHA256SUMS`, verify the archive, extract it, '
        'and run `./scripts/install.sh` from the extracted folder. '
        'Run from your logged-in Omarchy desktop. The package includes the original Bible '
        'script and license; required GTK/Wayland packages and Python dependencies '
        'are checked or installed during setup.\n')
    print(f'Built {archive_name}, install.sh, and SHA256SUMS in {output}')


if __name__ == '__main__':
    main()
