#!/usr/bin/python
"""Transactional user installation and reversible Omarchy integration."""
import argparse
from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from bible_search.backend import build_command
from bible_search.config import Config, config_path, discover_backend, ensure_config, read_config, xdg_path

START = '-- BEGIN Bible Search (managed)'
END = '-- END Bible Search (managed)'
APPLICATION_ENTRIES = ('src', 'scripts', 'third_party', 'assets', 'README.md',
                       'CHANGELOG.md', 'LICENSE', 'pyproject.toml')
MANAGED_ENTRIES = APPLICATION_ENTRIES + ('backend', 'backend-venv')
BACKEND_PACKAGES = ('beautifulsoup4', 'requests', 'Unidecode')
BACKEND_IMPORTS = ('bs4', 'requests', 'unidecode')


@dataclass(frozen=True)
class FileState:
    data: bytes | None
    mode: int | None


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def session_environment():
    try:
        result = subprocess.run(['systemctl', '--user', 'show-environment'],
                                capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        return
    allowed = {'WAYLAND_DISPLAY', 'HYPRLAND_INSTANCE_SIGNATURE', 'XDG_RUNTIME_DIR',
               'DBUS_SESSION_BUS_ADDRESS', 'XDG_CURRENT_DESKTOP'}
    for line in result.stdout.splitlines():
        key, _, value = line.partition('=')
        if key in allowed:
            os.environ.setdefault(key, value)


def file_state(path):
    if not path.exists():
        return FileState(None, None)
    return FileState(path.read_bytes(), stat.S_IMODE(path.stat().st_mode))


def restore_file(path, original):
    if original.data is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.bible-search.restore')
    temporary.write_bytes(original.data)
    temporary.chmod(original.mode)
    temporary.replace(path)


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
        backup = path.with_name(path.name + '.bak.bible-search.' +
                                datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
        shutil.copy2(path, backup)
        print(f'Backup: {backup}')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.bible-search.tmp')
    temporary.write_text(updated)
    if path.exists():
        shutil.copymode(path, temporary)
    temporary.replace(path)


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
    originals = {path: file_state(path) for path in changes}
    try:
        for path, content in changes.items():
            edit_block(path, content)
        reload_hypr(required=required)
    except Exception:
        for path, original in originals.items():
            restore_file(path, original)
        try:
            reload_hypr(required=False)
        except Exception as error:
            print(f'Original Lua files restored; reload reported: {error}', file=sys.stderr)
        raise


def copy_application(target):
    if ROOT.resolve() == target.resolve():
        return
    target.mkdir(parents=True, exist_ok=True)
    for name in APPLICATION_ENTRIES:
        source = ROOT / name
        destination = target / name
        if source.is_dir():
            shutil.copytree(source, destination, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns('__pycache__'), symlinks=True)
        else:
            shutil.copy2(source, destination)


def preserve_unmanaged_entries(previous, staging):
    if not previous.is_dir():
        return
    for source in previous.iterdir():
        if source.name in MANAGED_ENTRIES or source.name.startswith('.bible-search-'):
            continue
        destination = staging / source.name
        if source.is_symlink():
            destination.symlink_to(os.readlink(source), target_is_directory=source.is_dir())
        elif source.is_dir():
            shutil.copytree(source, destination, symlinks=True)
        else:
            shutil.copy2(source, destination)


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


def python_check(python, code, timeout=15):
    try:
        result = subprocess.run([str(python), '-c', code], capture_output=True,
                                timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def backend_environment_healthy(environment):
    python = environment / 'bin/python'
    imports = '; '.join(f'import {name}' for name in BACKEND_IMPORTS)
    return (python_check(python, 'import sys; assert sys.prefix != sys.base_prefix') and
            python_check(python, 'import pip') and python_check(python, imports))


def build_backend_environment(environment):
    run(['/usr/bin/python', '-m', 'venv', str(environment)])
    python = environment / 'bin/python'
    if not python_check(python, 'import sys; assert sys.prefix != sys.base_prefix'):
        raise RuntimeError('Managed backend Python environment is unusable')
    if not python_check(python, 'import pip'):
        run([str(python), '-m', 'ensurepip', '--upgrade'])
    if not python_check(python, 'import pip'):
        raise RuntimeError('Managed backend Python environment has no working pip')
    run([str(python), '-m', 'pip', 'install', '--disable-pip-version-check',
         *BACKEND_PACKAGES])
    if not backend_environment_healthy(environment):
        raise RuntimeError('Managed backend dependencies did not install completely')


def write_backend_wrapper(target):
    python = target / 'backend-venv/bin/python'
    vendor = target / 'third_party/bible-fetch/bible'
    wrapper = target / 'backend/bible'
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    wrapper.write_text('#!/bin/sh\nexec ' + shlex.quote(str(python)) + ' ' +
                       shlex.quote(str(vendor)) + ' "$@"\n')
    wrapper.chmod(0o755)
    return str(wrapper)


def setup_bundled_backend(target):
    vendor = target / 'third_party/bible-fetch'
    vendor.parent.mkdir(parents=True, exist_ok=True)
    source_vendor = ROOT / 'third_party/bible-fetch'
    if source_vendor.resolve() != vendor.resolve():
        shutil.copytree(source_vendor, vendor, dirs_exist_ok=True, symlinks=True)
    environment = target / 'backend-venv'
    if not backend_environment_healthy(environment):
        candidate = target / f'.backend-venv.stage-{uuid.uuid4().hex}'
        previous = target / f'.backend-venv.previous-{uuid.uuid4().hex}'
        moved_previous = False
        installed_candidate = False
        try:
            build_backend_environment(candidate)
            if environment.exists() or environment.is_symlink():
                environment.rename(previous)
                moved_previous = True
            candidate.rename(environment)
            installed_candidate = True
            if not backend_environment_healthy(environment):
                raise RuntimeError('Staged managed backend failed validation after installation')
        except Exception:
            if installed_candidate and environment.exists():
                remove_path(environment)
            if moved_previous and previous.exists():
                previous.rename(environment)
            raise
        finally:
            if candidate.exists():
                remove_path(candidate)
            if previous.exists():
                remove_path(previous)
    return write_backend_wrapper(target)


def configure_backend(target, explicit=None):
    """Preserve the public setup helper used by downstream installer checks."""
    managed = target / 'backend/bible'
    if config_path().exists():
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


def _proc_identity(pid):
    try:
        stat_fields = (Path('/proc') / str(pid) / 'stat').read_text().split()
        status = (Path('/proc') / str(pid) / 'status').read_text().splitlines()
        uid_line = next(line for line in status if line.startswith('Uid:'))
        return stat_fields[21], stat_fields[2], int(uid_line.split()[1])
    except (OSError, IndexError, StopIteration, ValueError):
        return None


def resident_processes(executable):
    """Find only this user's Python processes executing the exact managed launcher."""
    expected = str(executable.absolute())
    matches = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            args = (proc / 'cmdline').read_bytes().split(b'\0')
            args = [item.decode() for item in args if item]
        except (OSError, UnicodeError):
            continue
        identity = _proc_identity(int(proc.name))
        if not identity or identity[1] == 'Z' or identity[2] != os.getuid():
            continue
        launcher_index = 0 if args and args[0] == expected else 1
        if len(args) <= launcher_index or args[launcher_index] != expected:
            continue
        trailing = args[launcher_index + 1:]
        if trailing not in ([], ['--daemon'], ['--show']):
            continue
        matches.append((int(proc.name), identity[0]))
    return matches


def _same_process(pid, started):
    identity = _proc_identity(pid)
    return bool(identity and identity[0] == started and identity[1] != 'Z')


def stop_resident(executable, timeout=4):
    """Stop an exact managed process without executing installed application code."""
    processes = resident_processes(executable)
    if not processes:
        return False
    for pid, started in processes:
        if _same_process(pid, started):
            os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not any(_same_process(pid, started) for pid, started in processes):
            return True
        time.sleep(.05)
    live = [str(pid) for pid, started in processes if _same_process(pid, started)]
    raise RuntimeError('Bible Search resident did not stop after SIGTERM (PID ' +
                       ', '.join(live) + ')')


def validate_application(staging):
    code = ('import sys; sys.path.insert(0, ' + repr(str(staging / 'src')) + '); '
            'import bible_search.app, bible_search.backend, bible_search.clipboard')
    run(['/usr/bin/python', '-c', code], capture_output=True, timeout=15)


def validate_backend(command, config):
    candidate = Config(config.translation, command, config.verse_numbers, config.ascii)
    result = subprocess.run(build_command('John 3:16', candidate), stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=30)
    if result.returncode or not result.stdout.strip():
        detail = result.stderr.decode(errors='replace')[-1000:]
        raise RuntimeError('Backend validation failed' + (': ' + detail if detail else ''))
    return len(result.stdout)


def validate_clipboard():
    clipboard = subprocess.run(['wl-paste', '--list-types'], capture_output=True, text=True)
    if clipboard.returncode and 'Nothing is copied' not in clipboard.stderr:
        raise RuntimeError('Wayland clipboard unavailable: ' + clipboard.stderr)


def prepare_backend(staging, target, explicit=None):
    managed = target / 'backend/bible'
    if config_path().exists():
        config = read_config()
        if Path(config.bible_command) == managed:
            current_environment = target / 'backend-venv'
            if backend_environment_healthy(current_environment):
                shutil.copytree(current_environment, staging / 'backend-venv', symlinks=True)
            return config, setup_bundled_backend(staging), True
        return config, config.bible_command, False
    if explicit:
        command = str(explicit.resolve())
        managed_backend = False
    else:
        try:
            command = discover_backend()
            managed_backend = False
        except ValueError:
            command = str(managed)
            managed_backend = True
    ensure_config(command)
    config = read_config()
    staged_command = setup_bundled_backend(staging) if managed_backend else command
    return config, staged_command, managed_backend


def launcher_contents(target):
    return ('#!/usr/bin/python\nimport sys\nsys.path.insert(0, ' + repr(str(target / 'src')) +
            ')\nfrom bible_search.app import main\nraise SystemExit(main())\n').encode()


def write_launcher(executable, target):
    executable.parent.mkdir(parents=True, exist_ok=True)
    temporary = executable.with_name(executable.name + '.bible-search.new')
    temporary.write_bytes(launcher_contents(target))
    temporary.chmod(0o755)
    temporary.replace(executable)


def integration_content(executable):
    command = shlex.quote(str(executable))
    binding = (
        'hl.unbind("ALT + SPACE")\n' +
        'o.bind("ALT + SPACE", "Bible Search", ' + json.dumps(command + ' --show', ensure_ascii=False) + ')\n' +
        'o.window("^io\\\\.github\\\\.bible_search\\\\.Launcher$", {\n'
        '  float = true, center = true, border_size = 0, rounding = 14,\n'
        '  no_anim = true, decorate = false, opacity = "1.0 override 1.0 override",\n'
        '})')
    startup = 'o.launch_on_start(' + json.dumps(command + ' --daemon', ensure_ascii=False) + ')'
    return binding, startup


def commit_application(staging, target):
    previous = target.with_name(target.name + f'.bible-search.previous-{uuid.uuid4().hex}')
    if target.exists() or target.is_symlink():
        target.rename(previous)
    try:
        staging.rename(target)
    except Exception:
        if previous.exists():
            previous.rename(target)
        raise
    return previous if previous.exists() else None


def remove_path(path):
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.exists():
        shutil.rmtree(path)


def rollback_application(target, previous):
    remove_path(target)
    if previous and previous.exists():
        previous.rename(target)


def start_resident(executable):
    state = xdg_path('XDG_STATE_HOME', '.local/state') / 'bible-search'
    state.mkdir(parents=True, exist_ok=True)
    with (state / 'session.log').open('ab') as log:
        subprocess.Popen([str(executable), '--daemon'], stdin=subprocess.DEVNULL,
                         stdout=log, stderr=log, start_new_session=True)
    for _ in range(50):
        result = subprocess.run([str(executable), '--status'], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
        time.sleep(.1)
    raise RuntimeError(f'Daemon failed to start; inspect {state}/session.log')


def after_old_stop():
    """Fault-injection seam used by transaction regression tests."""


def after_application_commit():
    """Fault-injection seam used by transaction regression tests."""


def install(args, target, executable, bindings, autostart):
    dependencies()
    if not bindings.is_file() or not autostart.is_file():
        raise RuntimeError('Expected Omarchy Lua bindings.lua and autostart.lua; refusing to guess')
    if args.bible and (not args.bible.is_file() or not os.access(args.bible, os.X_OK)):
        raise RuntimeError('--bible must point to an executable script')
    reload_hypr()
    validate_clipboard()

    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.bible-search-stage-', dir=target.parent))
    config_original = file_state(config_path())
    executable_original = file_state(executable)
    integration_originals = {bindings: file_state(bindings), autostart: file_state(autostart)}
    backup_directories = {path: set(path.parent.glob(path.name + '.bak.bible-search.*'))
                          for path in integration_originals}
    previous = None
    was_running = False
    committed = False
    try:
        copy_application(staging)
        preserve_unmanaged_entries(target, staging)
        config, validation_command, managed_backend = prepare_backend(staging, target, args.bible)
        validate_application(staging)
        passage_size = validate_backend(validation_command, config)
        print(f'Backend verified: {config.bible_command} ({config.translation}, {passage_size} bytes)')

        was_running = stop_resident(executable)
        after_old_stop()
        previous = commit_application(staging, target)
        committed = True
        if managed_backend:
            write_backend_wrapper(target)
        write_launcher(executable, target)
        after_application_commit()
        binding_content, startup_content = integration_content(executable)
        update_integration({bindings: binding_content, autostart: startup_content})
        resident_status = start_resident(executable)
        print(resident_status)
    except Exception as install_error:
        rollback_errors = []
        if committed:
            try:
                stop_resident(executable)
            except Exception as error:
                rollback_errors.append(f'new resident: {error}')
        try:
            for path, original in integration_originals.items():
                restore_file(path, original)
            reload_hypr(required=False)
        except Exception as error:
            rollback_errors.append(f'integration: {error}')
        try:
            if committed:
                rollback_application(target, previous)
                previous = None
            restore_file(executable, executable_original)
            restore_file(config_path(), config_original)
        except Exception as error:
            rollback_errors.append(f'application: {error}')
        for path, before in backup_directories.items():
            for backup in set(path.parent.glob(path.name + '.bak.bible-search.*')) - before:
                backup.unlink(missing_ok=True)
        if was_running:
            try:
                start_resident(executable)
            except Exception as error:
                rollback_errors.append(f'previous resident restart: {error}')
        detail = '; '.join(rollback_errors)
        if detail:
            raise RuntimeError(f'{install_error}; rollback problems: {detail}') from install_error
        raise
    finally:
        if staging.exists():
            remove_path(staging)
    if previous and previous.exists():
        remove_path(previous)
    print(f'Installed: {executable}\nConfig: {config_path()}\nAlt+Space and login autostart configured.')


def uninstall(target, executable, bindings, autostart):
    stop_resident(executable)
    update_integration({bindings: '', autostart: ''}, required=False)
    executable.unlink(missing_ok=True)
    if target.exists():
        remove_path(target)
    print(f'Uninstalled. Original bible backend untouched. Config preserved: {config_path()}')


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
        uninstall(target, executable, bindings, autostart)
    else:
        install(args, target, executable, bindings, autostart)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'Bible Search: {error}', file=sys.stderr)
        sys.exit(1)
