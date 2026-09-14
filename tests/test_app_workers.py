import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from bible_search.app import BibleSearch


class ClipboardWorkerTests(unittest.TestCase):
    def test_slow_old_copy_cannot_overwrite_new_copy(self):
        started = threading.Event()
        release = threading.Event()
        copied = []
        state = SimpleNamespace(generation=1, clipboard_lock=threading.Lock(), finish=lambda *_: None)
        def copy(data):
            if data == b'old':
                started.set()
                release.wait(3)
            copied.append(data)
        with patch('bible_search.app.copy_passage', side_effect=copy), patch('bible_search.app.GLib.idle_add'):
            old = threading.Thread(target=BibleSearch.copy, args=(state, 1, b'old'))
            new = threading.Thread(target=BibleSearch.copy, args=(state, 2, b'new'))
            old.start()
            try:
                self.assertTrue(started.wait(2))
                state.generation = 2
                new.start()
                # Old holds the clipboard lock until its transfer finishes.
                self.assertTrue(state.clipboard_lock.locked())
            finally:
                release.set()
                old.join(3)
                if new.ident is not None:
                    new.join(3)
            self.assertEqual(copied, [b'old', b'new'])

    def test_cancelled_response_is_not_copied(self):
        state = SimpleNamespace(generation=2, clipboard_lock=threading.Lock())
        with patch('bible_search.app.copy_passage') as copy:
            BibleSearch.copy(state, 1, b'old')
            copy.assert_not_called()

    def test_unexpected_failure_finishes_request(self):
        state = SimpleNamespace(generation=1, clipboard_lock=threading.Lock(), finish=lambda *_: None)
        with patch('bible_search.app.copy_passage', side_effect=RuntimeError('unexpected')), patch('bible_search.app.GLib.idle_add') as idle:
            BibleSearch.copy(state, 1, b'text')
            idle.assert_called_once_with(state.finish, 1, 'Unable to copy passage')
