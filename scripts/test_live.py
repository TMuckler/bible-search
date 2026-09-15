#!/usr/bin/python
"""Exercise the installed launcher through real Hyprland keyboard events."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from manage import session_environment, ROOT
sys.path.insert(0, str(ROOT / 'src'))
from bible_search.backend import lookup
from bible_search.config import config_path

session_environment()
APP = str(Path.home() / '.local/bin/bible-search')
CLASS = 'io.github.bible_search.Launcher'


def call(*args):
    return subprocess.check_output(args)


def windows():
    return [w for w in json.loads(call('hyprctl', 'clients', '-j')) if w['class'] == CLASS and w['mapped']]


def wait_for(predicate, timeout=35):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(.05)
    raise AssertionError('Timed out waiting for launcher state')


def key(mods, key):
    args = ['wtype']
    if mods:
        args += ['-M', mods.lower()]
    args += ['-k', key]
    if mods:
        args += ['-m', mods.lower()]
    call(*args)


def show():
    if windows():
        key('', 'Escape')
        wait_for(lambda: not windows())
    call(APP, '--show')
    wait_for(lambda: windows() and json.loads(call('hyprctl', 'activewindow', '-j')).get('class') == CLASS)


def paste(reference):
    call('wtype', '--', reference)
    time.sleep(.15)


def clipboard():
    return call('wl-paste', '--no-newline')


def restore_clipboard(saved, mime):
    if saved is None:
        subprocess.run(['wl-copy', '--clear'], check=True, start_new_session=True)
        return
    # Detach the Wayland owner so automation runners do not reap it with this test.
    subprocess.run(['wl-copy', '--type', mime], input=saved, check=True,
                   start_new_session=True)
    time.sleep(.15)
    restored = call('wl-paste', '--no-newline', '--type', mime)
    if restored != saved:
        raise AssertionError('Failed to restore the pre-test clipboard exactly')


def main():
    config = config_path()
    original = config.read_bytes()
    types = subprocess.run(['wl-paste', '--list-types'], capture_output=True, text=True).stdout.splitlines()
    mime = next((t for t in types if t.startswith('text/plain')), types[0] if types else None)
    saved = call('wl-paste', '--no-newline', '--type', mime) if mime else None
    resolve = json.loads(call('hyprctl', 'getoption', 'input.resolve_binds_by_sym', '-j'))['bool']
    try:
        pid = call(APP, '--status')
        for reference in ('John 1:1', 'John 1:1-3', 'John 3:16', 'John 1:1-7', '1 John 4:7-12', 'Psalm 23', 'Romans 8:28-39'):
            expected = lookup(reference)
            show()
            w = windows()[0]
            assert w['floating'] and not w['xwayland'] and w['size'][0] == 650
            paste(reference)
            key('', 'Return')
            key('', 'Return')
            wait_for(lambda: not windows())
            assert clipboard() == expected, reference + ': clipboard mismatch'
            print('PASS passage and exact clipboard:', reference, flush=True)
        config.write_bytes(original.replace(b'translation = "CSB"', b'translation = "ESV"'))
        expected = lookup('John 3:16')
        show()
        paste('John 3:16')
        key('', 'Return')
        wait_for(lambda: not windows())
        assert clipboard() == expected
        assert call(APP, '--status') == pid
        print('PASS translation ESV without restarting', flush=True)
        config.write_bytes(original)
        show()
        paste('NotABibleBook 999:999')
        before = clipboard()
        key('', 'Return')
        time.sleep(2)
        assert windows(), 'failed lookup hid launcher'
        assert clipboard() == before, 'failed lookup overwrote clipboard'
        print('PASS failure keeps window and clipboard', flush=True)
        key('CTRL', 'a')
        paste('John 3:16')
        key('', 'Return')
        wait_for(lambda: not windows())
        assert clipboard() == lookup('John 3:16')
        print('PASS correction after failure', flush=True)
        show()
        paste('John 1:1')
        key('', 'Escape')
        wait_for(lambda: not windows())
        show()
        key('', 'Return')
        time.sleep(.3)
        assert windows(), 'Escape did not clear input'
        key('', 'Escape')
        wait_for(lambda: not windows())
        print('PASS Escape hides and clears', flush=True)
        # wtype uses a generated keymap; resolve symbols during virtual shortcut testing.
        # Physical keyboards use the normal layout. Restore the setting below.
        call('hyprctl', 'eval', 'hl.config({input = {resolve_binds_by_sym = true}})')
        for index in range(8):
            call('wtype', '-M', 'alt', '-k', 'space', '-m', 'alt')
            time.sleep(.1)
            assert call(APP, '--status') == pid
            assert len(windows()) == (1 if index % 2 == 0 else 0)
        if windows():
            key('', 'Escape')
        print('PASS repeated Alt+Space retains one resident PID', flush=True)
        show()
        others = [w for w in json.loads(call('hyprctl', 'clients', '-j')) if w['class'] != CLASS and w['mapped']]
        if others:
            call('hyprctl', 'eval', 'hl.dispatch(hl.dsp.focus({window = ' + json.dumps('address:' + others[0]['address']) + '}))')
            wait_for(lambda: not windows())
            print('PASS focus loss hides launcher', flush=True)
        bindings = json.loads(call('hyprctl', 'binds', '-j'))
        assigned = [b for b in bindings if b['modmask'] == 8 and b['key'].lower() == 'space']
        assert len(assigned) == 1 and assigned[0]['description'] == 'Bible Search'
        print('PASS one live Alt+Space binding', flush=True)
    finally:
        config.write_bytes(original)
        call('hyprctl', 'eval', 'hl.config({input = {resolve_binds_by_sym = ' + str(resolve).lower() + '}})')
        if windows():
            key('', 'Escape')
        restore_clipboard(saved, mime)


if __name__ == '__main__':
    main()
