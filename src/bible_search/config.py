"""XDG configuration, read afresh for every lookup."""
import json
import os
from pathlib import Path
import shutil
import tomllib
from dataclasses import dataclass


def xdg_path(variable, fallback):
    value = os.environ.get(variable, '')
    return Path(value) if value and Path(value).is_absolute() else Path.home() / fallback


def config_path():
    return xdg_path('XDG_CONFIG_HOME', '.config') / 'bible-search/config.toml'


def discover_backend():
    found = shutil.which('bible')
    if found:
        return str(Path(found).absolute())
    for path in (Path.home() / '.local/bin/bible', Path.cwd() / 'bible'):
        if path.is_file() and os.access(path, os.X_OK):
            return str(path.absolute())
    raise ValueError('Cannot find bible. Run install.sh --bible /absolute/path/to/bible')


def ensure_config(command=None):
    path = config_path()
    if not path.exists():
        command = command or discover_backend()
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open('x') as stream:
                stream.write('# BibleGateway translation. Changes apply to the next search.\n'
                             'translation = "CSB"\n\n'
                             '# Absolute path to your existing executable Bible script.\n'
                             f'bible_command = {json.dumps(command)}\n\n'
                             '# Pass the corresponding options to the existing script.\n'
                             'verse_numbers = false\nascii = true\n')
        except FileExistsError:
            pass
    return path


@dataclass(frozen=True)
class Config:
    translation: str
    bible_command: str
    verse_numbers: bool = False
    ascii: bool = True


def read_config():
    try:
        data = tomllib.loads(ensure_config().read_text())
        translation = data.get('translation', 'CSB')
        command = data['bible_command']
        if not isinstance(translation, str) or not translation.strip():
            raise ValueError('translation must be a nonempty string')
        if not isinstance(command, str) or not command:
            raise ValueError('bible_command must be an executable path')
        command = os.path.expandvars(os.path.expanduser(command))
        if not Path(command).is_absolute():
            raise ValueError('bible_command must be an absolute path')
        for option in ('verse_numbers', 'ascii'):
            if type(data.get(option, option == 'ascii')) is not bool:
                raise ValueError(f'{option} must be true or false')
        return Config(translation, command, data.get('verse_numbers', False), data.get('ascii', True))
    except (OSError, KeyError, tomllib.TOMLDecodeError) as error:
        raise ValueError(f'Unable to read config: {error}') from error
