import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import manage


class ManagedProcessTests(unittest.TestCase):
    def wait_for(self, predicate, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(.02)
        return False

    def test_exact_managed_process_is_stopped_without_executing_launcher(self):
        with tempfile.TemporaryDirectory() as directory:
            launcher = Path(directory) / 'bible-search'
            ready = Path(directory) / 'ready'
            launcher.write_text(
                'import pathlib,signal,sys,time\n'
                f'pathlib.Path({str(ready)!r}).write_text("ready")\n'
                'signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))\n'
                'while True: time.sleep(.1)\n')
            process = subprocess.Popen([sys.executable, str(launcher), '--daemon'])
            try:
                self.assertTrue(self.wait_for(ready.exists))
                self.assertTrue(manage.resident_processes(launcher))
                self.assertTrue(manage.stop_resident(launcher, timeout=2))
                process.wait(2)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()

    def test_absent_resident_is_distinct_and_unrelated_process_is_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            launcher = Path(directory) / 'bible-search'
            launcher.write_text('broken application')
            unrelated = subprocess.Popen(
                [sys.executable, '-c', 'import time; time.sleep(20)', str(launcher), '--daemon'])
            try:
                self.assertFalse(manage.stop_resident(launcher, timeout=.2))
                self.assertIsNone(unrelated.poll())
            finally:
                unrelated.terminate()
                unrelated.wait(2)

    def test_genuine_shutdown_failure_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            launcher = Path(directory) / 'bible-search'
            launcher.write_text(
                'import signal,time\n'
                'signal.signal(signal.SIGTERM, signal.SIG_IGN)\n'
                'while True: time.sleep(.1)\n')
            process = subprocess.Popen([sys.executable, str(launcher), '--daemon'])
            try:
                self.assertTrue(self.wait_for(lambda: bool(manage.resident_processes(launcher))))
                with self.assertRaisesRegex(RuntimeError, 'did not stop'):
                    manage.stop_resident(launcher, timeout=.15)
                self.assertIsNone(process.poll())
            finally:
                process.kill()
                process.wait(2)

    def test_broken_install_uninstalls_without_desktop_session(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'data/bible-search'
            executable = root / 'home/.local/bin/bible-search'
            bindings = root / 'config/hypr/bindings.lua'
            autostart = root / 'config/hypr/autostart.lua'
            config = root / 'config/bible-search/config.toml'
            for path in (executable, bindings, autostart, config):
                path.parent.mkdir(parents=True, exist_ok=True)
            executable.write_text('#!/usr/bin/python\nfrom missing_application import main\n')
            executable.chmod(0o755)
            target.mkdir(parents=True)
            (target / 'damaged').write_text('old')
            bindings.write_text('-- user bindings\n')
            autostart.write_text('-- user autostart\n')
            config.write_text('retained config')
            environment = {'XDG_CONFIG_HOME': str(root / 'config')}
            with patch.dict(os.environ, environment, clear=True):
                manage.uninstall(target, executable, bindings, autostart)
            self.assertFalse(executable.exists())
            self.assertFalse(target.exists())
            self.assertEqual(config.read_text(), 'retained config')


if __name__ == '__main__':
    unittest.main()
