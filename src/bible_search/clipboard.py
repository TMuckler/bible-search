"""wl-copy owns the clipboard independently of the launcher window."""
import logging
import subprocess
from .backend import LookupError


def copy_passage(passage):
    if not passage.strip():
        raise LookupError('Passage not found')
    try:
        # Do not capture stdout: the forked clipboard owner would keep that pipe open.
        result = subprocess.run(['wl-copy', '--type', 'text/plain;charset=utf-8'],
                                input=passage, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, timeout=5)
        if result.returncode:
            raise OSError(f'wl-copy exited {result.returncode}')
    except (OSError, subprocess.TimeoutExpired) as error:
        logging.getLogger(__name__).warning('Clipboard failed: %s', error)
        raise LookupError('Unable to copy — check wl-clipboard') from error
