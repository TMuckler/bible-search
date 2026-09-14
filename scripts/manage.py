#!/usr/bin/python
"""User installation and reversible, marked Omarchy configuration edits."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from bible_search.config import config_path, discover_backend, ensure_config, read_config, xdg_path
from bible_search.backend import lookup

START = '-- BEGIN Bible Search (managed)'
END = '-- END Bible Search (managed)'


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def session_environment():
    # Agent shells may lack the compositor environment already held by systemd.
    result = subprocess.run(['systemctl', '--user', 'show-environment'], capture_output=True, text=True)
    allowed = {'WAYLAND_DISPLAY', 'HYPRLAND_INSTANCE_SIGNATURE', 'XDG_RUNTIME_DIR',
               'DBUS_SESSION_BUS_ADDRESS', 'XDG_CURRENT_DESKTOP'}
    for line in result.stdout.splitlines():
        key, _, value = line.partition('=')
        if key in allowed:
            os.environ.setdefault(key, value)


def edit_block(path, content):
    original = path.read_text() if path.exists() else ''
    updated = original
    if START in original or END in original:
        if original.count(START) != 1 or original.count(END) != 1:
            raise RuntimeError(f'Invalid managed markers in {path}; refusing to edit')
        begin = original.index(START)
        finish = original.index(END, begin) + len(END)
        if original[finish:finish+1] == '\n':
            finish += 1
        updated = original[:begin] + original[finish:]
    if content:
        updated = updated.rstrip('\n') + '\n\n' + START + '\n' + content + '\n' + END + '\n'
    if updated == original:
        return
    if path.exists():
        backup = path.with_name(path.name + '.bak.bible-search.' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
        shutil.copy2(path, backup)
        print(f'Backup: {backup}')
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.bible-search.tmp')
    temp.write_text(updated)
    if path.exists():
        shutil.copymode(path, temp)
    temp.replace(path)


def reload_hypr(required=True):
    if os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'):
        run(['hyprctl', 'reload'], stdout=subprocess.DEVNULL)
        result = run(['hyprctl', 'configerrors'], capture_output=True, text=True)
        if result.stdout.strip():
            raise RuntimeError('Hyprland config errors: ' + result.stdout)
    elif required:
        raise RuntimeError('No active Hyprland session; log in and rerun installation to verify integration')
    else:
        print('No active Hyprland session; changes apply at next login.')


def update_integration(changes, required=True):
    """Restore both user files if an edit or compositor validation fails."""
    originals = {path: path.read_bytes() if path.exists() else None for path in changes}
    try:
        for path, content in changes.items():
            edit_block(path, content)
        reload_hypr(required=required)
    except Exception:
        for path, original in originals.items():
            if original is None:
                path.unlink(missing_ok=True)
            elif not path.exists() or path.read_bytes() != original:
                path.write_bytes(original)
        try:
            reload_hypr(required=False)
        except Exception as error:
            print(f'Original Lua files restored; reload reported: {error}', file=sys.stderr)
        raise


def copy_application(target):
    # The installed scripts remain usable after the original checkout is removed.
    if ROOT.resolve() == target.resolve():
        return
    target.mkdir(parents=True, exist_ok=True)
    for name in ('src', 'scripts', 'third_party', 'assets'):
        shutil.copytree(ROOT / name, target / name, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__'))
    for name in ('README.md', 'LICENSE', 'pyproject.toml'):
        shutil.copy2(ROOT / name, target / name)


def dependencies():
    missing = []
    check = subprocess.run(['/usr/bin/python', '-c',
                            "import gi; gi.require_version('Gtk','4.0'); from gi.repository import Gtk"],
                           capture_output=True)
    if check.returncode:
        missing += ['python-gobject', 'gtk4']
    if not shutil.which('wl-copy') or not shutil.which('wl-paste'):
        missing.append('wl-clipboard')
    if missing:
        print('Missing Arch packages: ' + ' '.join(missing), flush=True)
        privilege = 'sudo' if sys.stdin.isatty() else 'pkexec'
        run([privilege, 'pacman', '-S', '--needed', *missing])
    if not shutil.which('hyprctl'):
        raise RuntimeError('This installer requires Omarchy/Hyprland')



def setup_bundled_backend(target):
    """Install only our bundled copy and private dependencies; never touch ~/bin/bible."""
    vendor = target / 'third_party/bible-fetch'
    vendor.parent.mkdir(parents=True, exist_ok=True)
    if (ROOT / 'third_party/bible-fetch').resolve() != vendor.resolve():
        shutil.copytree(ROOT / 'third_party/bible-fetch', vendor, dirs_exist_ok=True)
    environment = target / 'backend-venv'
    python = environment / 'bin/python'
    if not python.exists():
        run(['/usr/bin/python', '-m', 'venv', str(environment)])
    check = subprocess.run([str(python), '-c', 'import bs4, requests, unidecode'], capture_output=True)
    if check.returncode:
        run([str(python), '-m', 'pip', 'install', 'beautifulsoup4', 'requests', 'Unidecode'])
    wrapper = target / 'backend/bible'
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    wrapper.write_text('#!/bin/sh\nexec ' + shlex.quote(str(python)) + ' ' +
                       shlex.quote(str(vendor / 'bible')) + ' "$@"\n')
    wrapper.chmod(0o755)
    return str(wrapper)


def configure_backend(target, explicit=None):
    managed = target / 'backend/bible'
    if config_path().exists():
        # Restore a retained managed config after an uninstall, and refresh dependencies.
        if Path(read_config().bible_command) == managed:
            setup_bundled_backend(target)
        return
    if explicit:
        command = str(explicit.resolve())
    else:
        try:
            command = discover_backend()
        except ValueError:
            command = setup_bundled_backend(target)
    ensure_config(command)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['install', 'uninstall'])
    parser.add_argument('--bible', type=Path, help='Existing executable backend (used for a new config)')
    args = parser.parse_args()
    session_environment()
    config_root = xdg_path('XDG_CONFIG_HOME', '.config')
    target = xdg_path('XDG_DATA_HOME', '.local/share') / 'bible-search'
    executable = Path.home() / '.local/bin/bible-search'
    bindings = config_root / 'hypr/bindings.lua'
    autostart = config_root / 'hypr/autostart.lua'
    if args.action == 'uninstall':
        if executable.exists():
            run([str(executable), '--quit'])
        update_integration({bindings: '', autostart: ''}, required=False)
        executable.unlink(missing_ok=True)
        if target.exists():
            shutil.rmtree(target)
        print(f'Uninstalled. Original bible backend untouched. Config preserved: {config_path()}')
        return
    dependencies()
    if not bindings.is_file() or not autostart.is_file():
        raise RuntimeError('Expected Omarchy Lua bindings.lua and autostart.lua; refusing to guess')
    if args.bible and (not args.bible.is_file() or not os.access(args.bible, os.X_OK)):
        raise RuntimeError('--bible must point to an executable script')
    # Validate the current session before changing an installation or user files.
    reload_hypr()
    configure_backend(target, args.bible)
    config = read_config()
    passage = lookup('John 3:16')
    print(f'Backend verified: {config.bible_command} ({config.translation}, {len(passage)} bytes)')
    clipboard = subprocess.run(['wl-paste', '--list-types'], capture_output=True, text=True)
    if clipboard.returncode and 'Nothing is copied' not in clipboard.stderr:
        raise RuntimeError('Wayland clipboard unavailable: ' + clipboard.stderr)
    # Stop the previous installation only after dependencies/config/backend pass.
    if executable.exists():
        run([str(executable), '--quit'])
        for _ in range(30):
            result = subprocess.run([str(executable), '--status'], stdout=subprocess.DEVNULL)
            if result.returncode:
                break
            time.sleep(.1)
    copy_application(target)
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_text('#!/usr/bin/python\nimport sys\nsys.path.insert(0, ' + repr(str(target / 'src')) +
                          ')\nfrom bible_search.app import main\nraise SystemExit(main())\n')
    executable.chmod(0o755)
    command = shlex.quote(str(executable))
    binding_content = (
        'hl.unbind("ALT + SPACE")\n' +
        'o.bind("ALT + SPACE", "Bible Search", ' + json.dumps(command + ' --show', ensure_ascii=False) + ')\n' +
        'o.window("^io\\\\.github\\\\.bible_search\\\\.Launcher$", {\n'
        '  float = true, center = true, border_size = 0, rounding = 14,\n'
        '  no_anim = true, decorate = false, opacity = "1.0 override 1.0 override",\n'
        '})')
    startup_content = 'o.launch_on_start(' + json.dumps(command + ' --daemon', ensure_ascii=False) + ')'
    update_integration({bindings: binding_content, autostart: startup_content})
    state = xdg_path('XDG_STATE_HOME', '.local/state') / 'bible-search'
    state.mkdir(parents=True, exist_ok=True)
    with (state / 'session.log').open('ab') as log:
        subprocess.Popen([str(executable), '--daemon'], stdin=subprocess.DEVNULL,
                         stdout=log, stderr=log, start_new_session=True)
    for _ in range(40):
        result = subprocess.run([str(executable), '--status'], capture_output=True, text=True)
        if result.returncode == 0:
            print(result.stdout.strip())
            print(f'Installed: {executable}\nConfig: {config_path()}\nAlt+Space and login autostart configured.')
            return
        time.sleep(.1)
    raise RuntimeError(f'Daemon failed to start; inspect {state}/session.log')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'Bible Search: {error}', file=sys.stderr)
        sys.exit(1)
