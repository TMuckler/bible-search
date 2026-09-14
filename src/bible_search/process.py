"""Cancellable execution of a backend and any subprocesses it starts."""
import os
import signal
import subprocess
import time


class Cancelled(Exception):
    pass


def run_backend(args, cancel=None, timeout=30):
    if cancel is None:
        return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    if cancel.is_set():
        raise Cancelled()
    with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          start_new_session=True) as process:
        deadline = time.monotonic() + timeout
        try:
            while True:
                if cancel.is_set():
                    raise Cancelled()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(args, timeout)
                try:
                    stdout, stderr = process.communicate(timeout=min(.1, remaining))
                    if cancel.is_set():
                        raise Cancelled()
                    return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
                except subprocess.TimeoutExpired:
                    continue
        except BaseException:
            # Kill the owned process group, including descendants holding our pipes.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()
            raise
