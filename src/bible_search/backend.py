"""Run the user's backend without a shell and append a passage citation."""
import logging
import subprocess
from .config import read_config

log = logging.getLogger(__name__)


class LookupError(Exception):
    pass


def build_command(reference, config):
    args = [config.bible_command, '--version', config.translation]
    if config.verse_numbers:
        args.append('--verse-numbers')
    if config.ascii:
        args.append('--ascii')
    # End option parsing so even option-like input remains a reference.
    return args + ['--', reference]


def lookup(reference):
    try:
        config = read_config()
    except ValueError as error:
        log.warning('%s', error)
        raise LookupError('Check config.toml') from error
    args = build_command(reference, config)
    log.info('Lookup: translation=%s verse_numbers=%s ascii=%s backend=%s',
             config.translation, config.verse_numbers, config.ascii, config.bible_command)
    try:
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    except subprocess.TimeoutExpired as error:
        log.warning('Backend timed out')
        raise LookupError('Unable to reach BibleGateway') from error
    except OSError as error:
        log.warning('Backend execution failed: %s', error)
        raise LookupError('Check the Bible script path') from error
    if result.returncode:
        detail = result.stderr.decode(errors='replace')
        log.warning('Backend exit %s: %s', result.returncode, detail[-4000:])
        network = any(word in detail for word in ('ConnectionError', 'Timeout', 'SSLError', 'Network'))
        raise LookupError('Unable to reach BibleGateway' if network else 'Passage not found')
    if not result.stdout.strip():
        log.info('Backend returned no passage')
        raise LookupError('Passage not found')
    # Use the same config snapshot for the query and citation, even if edited mid-request.
    citation = f'({reference.strip()} {config.translation})'.encode('utf-8')
    return result.stdout.rstrip() + b'\n\n' + citation
