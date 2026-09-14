import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from bible_search.process import Cancelled, run_backend


class ProcessTests(unittest.TestCase):
    def test_cancel_kills_running_backend(self):
        cancel = threading.Event()
        errors = []
        with tempfile.TemporaryDirectory() as directory:
            pidfile = Path(directory) / 'pid'
            program = 'import os,time,pathlib; pathlib.Path(' + repr(str(pidfile)) + ').write_text(str(os.getpid())); time.sleep(20)'
            def work():
                try:
                    run_backend([sys.executable, '-c', program], cancel)
                except Exception as error:
                    errors.append(error)
            worker = threading.Thread(target=work)
            worker.start()
            deadline = time.monotonic() + 3
            while not pidfile.exists() and time.monotonic() < deadline:
                time.sleep(.01)
            try:
                self.assertTrue(pidfile.exists())
            finally:
                cancel.set()
                worker.join(3)
            self.assertFalse(worker.is_alive())
            self.assertIsInstance(errors[0], Cancelled)
            with self.assertRaises(ProcessLookupError):
                os.kill(int(pidfile.read_text()), 0)

    def test_timeout_and_success(self):
        cancel = threading.Event()
        with self.assertRaises(subprocess.TimeoutExpired):
            run_backend([sys.executable, '-c', 'import time; time.sleep(20)'], cancel, timeout=.15)
        result = run_backend([sys.executable, '-c', 'import sys; sys.stdout.buffer.write(b"text\\r\\n")'], cancel)
        self.assertEqual(result.stdout, b'text\r\n')
        self.assertEqual(result.returncode, 0)

    def test_cancel_before_start(self):
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(Cancelled):
            run_backend(['/does/not/exist'], cancel)
