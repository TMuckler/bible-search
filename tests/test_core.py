import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from bible_search.backend import LookupError, build_command, lookup
from bible_search.clipboard import copy_passage
from bible_search.config import Config, read_config, ensure_config


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'XDG_CONFIG_HOME': self.temp.name})
        self.env.start()
        self.path = ensure_config('/fake/bible')

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_options_and_multiword_reference(self):
        config = Config('CSB', '/fake/bible', True, True)
        self.assertEqual(build_command('1 John 4:7-12', config),
                         ['/fake/bible', '--version', 'CSB', '--verse-numbers', '--ascii', '--', '1 John 4:7-12'])
        self.assertEqual(build_command('--help; $(touch /tmp/no)', Config('ESV', '/fake/bible', False, False)),
                         ['/fake/bible', '--version', 'ESV', '--', '--help; $(touch /tmp/no)'])

    def test_live_config_and_citation(self):
        payload = b'Text\nSecond paragraph\r\n\n'
        with patch('bible_search.backend.subprocess.run', return_value=subprocess.CompletedProcess([], 0, payload, b'')) as run:
            self.assertEqual(lookup('John 1:1'), payload.rstrip() + b'\n\n(John 1:1 CSB)')
            self.assertIn('CSB', run.call_args.args[0])
            self.path.write_text(self.path.read_text().replace('"CSB"', '"NASB"'))
            self.assertEqual(lookup('John 1:1'), payload.rstrip() + b'\n\n(John 1:1 NASB)')
            self.assertIn('NASB', run.call_args.args[0])
            self.assertNotIn('shell', run.call_args.kwargs)

    def test_failure_and_empty_never_reach_clipboard(self):
        for result in (subprocess.CompletedProcess([], 1, b'garbage', b'failure'),
                       subprocess.CompletedProcess([], 0, b' \n', b'')):
            with patch('bible_search.backend.subprocess.run', return_value=result), patch('bible_search.clipboard.copy_passage') as copy:
                with self.assertRaises(LookupError):
                    copy(lookup('bad'))
                copy.assert_not_called()

    def test_range_without_numbers_and_single_config_snapshot(self):
        def backend(args, **kwargs):
            self.assertNotIn('--verse-numbers', args)
            self.path.write_text(self.path.read_text().replace('"CSB"', '"ESV"'))
            return subprocess.CompletedProcess(args, 0, b'First verse. Second verse. Third verse.\n', b'')
        with patch('bible_search.backend.subprocess.run', side_effect=backend):
            self.assertEqual(lookup('John 1:1-3'),
                             b'First verse. Second verse. Third verse.\n\n(John 1:1-3 CSB)')

    def test_timeout(self):
        with patch('bible_search.backend.subprocess.run', side_effect=subprocess.TimeoutExpired('bible', 30)):
            with self.assertRaisesRegex(LookupError, 'Unable to reach'):
                lookup('John 1:1')

    def test_invalid_config(self):
        self.path.write_text('translation = "ESV"\nbible_command = "/fake/bible"\nascii = "true"\n')
        with self.assertRaises(ValueError):
            read_config()

    def test_clipboard_bytes(self):
        payload = b'Verse\n\n'
        with patch('bible_search.clipboard.subprocess.run', return_value=subprocess.CompletedProcess([], 0)) as run:
            copy_passage(payload)
            self.assertEqual(run.call_args.kwargs['input'], payload)
            self.assertEqual(run.call_args.args[0], ['wl-copy', '--type', 'text/plain;charset=utf-8'])


if __name__ == '__main__':
    unittest.main()
