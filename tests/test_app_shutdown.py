import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest


class ApplicationShutdownTests(unittest.TestCase):
    def exercise(self, mode):
        if not shutil.which('dbus-run-session'):
            self.skipTest('dbus-run-session is unavailable')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            harness = root / 'harness.py'
            controller = root / 'controller.py'
            harness.write_text(textwrap.dedent('''
                import pathlib, sys, threading, time
                from bible_search.app import BibleSearch
                from bible_search.process import run_backend

                parent_code = r"""
                import pathlib,subprocess,sys,time,os
                child = subprocess.Popen([sys.executable, '-c',
                    'import os,pathlib,sys,time; pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(30)',
                    sys.argv[2]])
                pathlib.Path(sys.argv[1]).write_text(str(os.getpid()))
                time.sleep(30)
                """

                class Harness(BibleSearch):
                    def make_window(self):
                        self.files = [pathlib.Path(item) for item in sys.argv[1:]]
                        def backend_work(arguments, cancel):
                            try:
                                run_backend(arguments, cancel)
                            except Exception:
                                pass
                        first_cancel = threading.Event()
                        self.cancel = first_cancel
                        first = [sys.executable, '-c', parent_code,
                                 str(self.files[0]), str(self.files[1])]
                        self.start_worker(backend_work, first, first_cancel, cancel=first_cancel)
                        def replace_request():
                            deadline = time.monotonic() + 5
                            while ((not self.files[0].exists() or not self.files[1].exists()) and
                                   time.monotonic() < deadline):
                                time.sleep(.01)
                            first_cancel.set()
                            second_cancel = threading.Event()
                            self.cancel = second_cancel
                            second = [sys.executable, '-c', parent_code,
                                      str(self.files[2]), str(self.files[3])]
                            self.start_worker(backend_work, second, second_cancel, cancel=second_cancel)
                        threading.Thread(target=replace_request, daemon=True).start()

                raise SystemExit(Harness().run([sys.argv[0], '--daemon']))
            '''))
            controller.write_text(textwrap.dedent('''
                import os,pathlib,subprocess,sys,time
                mode, harness, *files = sys.argv[1:]
                resident = subprocess.Popen([sys.executable, harness, *files])
                paths = [pathlib.Path(item) for item in files]
                deadline = time.monotonic() + 8
                while (not paths[2].exists() or not paths[3].exists()) and time.monotonic() < deadline:
                    if resident.poll() is not None:
                        raise SystemExit('resident exited before lookup started')
                    time.sleep(.02)
                if not paths[2].exists() or not paths[3].exists():
                    resident.kill()
                    raise SystemExit('second lookup did not start')
                if mode == 'quit':
                    command = ('import sys; from bible_search.app import main; '
                               'sys.argv=["bible-search","--quit"]; raise SystemExit(main())')
                    subprocess.run([sys.executable, '-c', command], check=True)
                else:
                    os.kill(resident.pid, 15)
                resident.wait(timeout=10)
                deadline = time.monotonic() + 3
                pids = [int(path.read_text()) for path in paths if path.exists()]
                while any(pathlib.Path('/proc', str(pid)).exists() for pid in pids) and time.monotonic() < deadline:
                    time.sleep(.02)
                live = [pid for pid in pids if pathlib.Path('/proc', str(pid)).exists()]
                if live:
                    raise SystemExit('backend processes remain: ' + repr(live))
            '''))
            files = [root / name for name in ('parent1', 'child1', 'parent2', 'child2')]
            source = Path(__file__).resolve().parents[1] / 'src'
            env = dict(os.environ, PYTHONPATH=str(source), GDK_BACKEND='headless',
                       BIBLE_SEARCH_APP_ID=f'io.github.bible_search.Shutdown{mode.title()}')
            result = subprocess.run(
                ['dbus-run-session', sys.executable, str(controller), mode, str(harness),
                 *(str(path) for path in files)], capture_output=True, text=True, env=env, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_quit_waits_for_backend_tree_cleanup(self):
        self.exercise('quit')

    def test_sigterm_waits_for_backend_tree_cleanup(self):
        self.exercise('sigterm')


if __name__ == '__main__':
    unittest.main()
