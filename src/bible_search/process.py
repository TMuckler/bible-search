"""Cancellable execution of a backend and any subprocesses it starts."""
import ctypes
import os
import signal
import subprocess
import sys
import threading
import time


class Cancelled(Exception):
    pass


_owned_lock = threading.Lock()
_owned_processes = set()
_subreaper_enabled = False


def _enable_subreaper():
    """Adopt orphaned backend descendants so this process can reap them."""
    global _subreaper_enabled
    if _subreaper_enabled or not sys.platform.startswith('linux'):
        return
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(36, 1, 0, 0, 0) == 0:  # PR_SET_CHILD_SUBREAPER
            _subreaper_enabled = True
    except (AttributeError, OSError):
        pass


def _terminate_group(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _reap_group(process_group, timeout=1):
    deadline = time.monotonic() + timeout
    while True:
        try:
            pid, _ = os.waitpid(-process_group, os.WNOHANG)
        except ChildProcessError:
            return
        if pid:
            continue
        if time.monotonic() >= deadline:
            return
        time.sleep(.01)


def terminate_owned_processes():
    """Request immediate termination of every backend process group we own.

    The worker that called communicate remains responsible for reaping its direct
    child. This function is safe to call while that communicate is in progress.
    """
    with _owned_lock:
        processes = tuple(_owned_processes)
    for process in processes:
        _terminate_group(process)
    return len(processes)


def run_backend(args, cancel=None, timeout=30):
    if cancel is None:
        return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    if cancel.is_set():
        raise Cancelled()
    _enable_subreaper()
    with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          start_new_session=True) as process:
        with _owned_lock:
            _owned_processes.add(process)
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
            _terminate_group(process)
            process.communicate()
            _reap_group(process.pid)
            raise
        finally:
            with _owned_lock:
                _owned_processes.discard(process)
