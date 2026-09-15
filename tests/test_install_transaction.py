import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import manage


class InstallationTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.target = self.root / 'data/bible-search'
        self.executable = self.root / 'home/.local/bin/bible-search'
        self.bindings = self.root / 'config/hypr/bindings.lua'
        self.autostart = self.root / 'config/hypr/autostart.lua'
        self.backend = self.root / 'external/bible'
        for path in (self.bindings, self.autostart, self.backend):
            path.parent.mkdir(parents=True, exist_ok=True)
        self.bindings.write_text('-- original bindings\n')
        self.autostart.write_text('-- original autostart\n')
        self.backend.write_text('#!/bin/sh\nprintf passage\n')
        self.backend.chmod(0o755)
        self.args = SimpleNamespace(bible=self.backend)
        self.env = patch.dict(os.environ, {
            'XDG_CONFIG_HOME': str(self.root / 'config'),
            'XDG_DATA_HOME': str(self.root / 'data'),
            'XDG_STATE_HOME': str(self.root / 'state'),
        }, clear=True)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def common_patches(self, **extra):
        patches = {
            'dependencies': patch('manage.dependencies'),
            'reload': patch('manage.reload_hypr'),
            'clipboard': patch('manage.validate_clipboard'),
            'application': patch('manage.validate_application'),
            'backend': patch('manage.validate_backend', return_value=7),
        }
        patches.update(extra)
        return patches

    def run_with(self, patches):
        entered = []
        try:
            for item in patches.values():
                entered.append(item)
                item.start()
            manage.install(self.args, self.target, self.executable,
                           self.bindings, self.autostart)
        finally:
            for item in reversed(entered):
                item.stop()

    def seed_previous_install(self):
        (self.target / 'src').mkdir(parents=True)
        (self.target / 'src/old.py').write_text('old application')
        (self.target / 'user-note.txt').write_text('keep me')
        self.executable.parent.mkdir(parents=True)
        self.executable.write_bytes(b'old launcher')
        manage.ensure_config(str(self.backend))
        return {
            'target': {path.relative_to(self.target): path.read_bytes()
                       for path in self.target.rglob('*') if path.is_file()},
            'executable': self.executable.read_bytes(),
            'bindings': self.bindings.read_bytes(),
            'autostart': self.autostart.read_bytes(),
            'config': manage.config_path().read_bytes(),
        }

    def assert_previous_restored(self, before):
        files = {path.relative_to(self.target): path.read_bytes()
                 for path in self.target.rglob('*') if path.is_file()}
        self.assertEqual(files, before['target'])
        self.assertEqual(self.executable.read_bytes(), before['executable'])
        self.assertEqual(self.bindings.read_bytes(), before['bindings'])
        self.assertEqual(self.autostart.read_bytes(), before['autostart'])
        self.assertEqual(manage.config_path().read_bytes(), before['config'])
        self.assertEqual(list(self.root.glob('data/.bible-search-stage-*')), [])
        self.assertEqual(list(self.root.glob('data/bible-search.bible-search.previous-*')), [])

    def test_normal_reinstall_commits_complete_tree_and_preserves_user_entry(self):
        self.seed_previous_install()
        patches = self.common_patches(
            stop=patch('manage.stop_resident', return_value=True),
            start=patch('manage.start_resident', return_value='resident ready'))
        self.run_with(patches)
        self.assertTrue((self.target / 'src/bible_search/app.py').is_file())
        self.assertFalse((self.target / 'src/old.py').exists())
        self.assertEqual((self.target / 'user-note.txt').read_text(), 'keep me')
        self.assertIn(manage.START, self.bindings.read_text())
        self.assertIn(manage.START, self.autostart.read_text())
        self.assertEqual(manage.read_config().bible_command, str(self.backend))

    def test_install_repairs_launcher_with_missing_application_imports(self):
        self.target.mkdir(parents=True)
        (self.target / 'application-is-missing').write_text('damaged')
        self.executable.parent.mkdir(parents=True)
        self.executable.write_text('#!/usr/bin/python\nfrom missing_application import main\n')
        self.executable.chmod(0o755)
        patches = self.common_patches(
            start=patch('manage.start_resident', return_value='resident ready'))
        self.run_with(patches)
        self.assertTrue((self.target / 'src/bible_search/app.py').is_file())
        self.assertNotIn(b'missing_application', self.executable.read_bytes())

    def test_copy_failure_happens_before_old_resident_stops(self):
        before = self.seed_previous_install()
        stop = patch('manage.stop_resident')
        patches = self.common_patches(
            copy=patch('manage.copy_application', side_effect=OSError('copy fault')),
            stop=patch('manage.stop_resident', side_effect=AssertionError('resident stopped too early')))
        with self.assertRaisesRegex(OSError, 'copy fault'):
            self.run_with(patches)
        self.assert_previous_restored(before)

    def test_fault_after_old_stop_restores_and_restarts_previous_resident(self):
        before = self.seed_previous_install()
        start = patch('manage.start_resident', return_value='old restarted')
        patches = self.common_patches(
            stop=patch('manage.stop_resident', return_value=True),
            fault=patch('manage.after_old_stop', side_effect=RuntimeError('after stop')),
            start=start)
        with self.assertRaisesRegex(RuntimeError, 'after stop'):
            self.run_with(patches)
        self.assert_previous_restored(before)

    def test_fault_after_application_commit_restores_complete_previous_install(self):
        before = self.seed_previous_install()
        patches = self.common_patches(
            stop=patch('manage.stop_resident', side_effect=[True, False]),
            fault=patch('manage.after_application_commit', side_effect=RuntimeError('after commit')),
            start=patch('manage.start_resident', return_value='old restarted'))
        with self.assertRaisesRegex(RuntimeError, 'after commit'):
            self.run_with(patches)
        self.assert_previous_restored(before)

    def test_integration_failure_restores_complete_previous_install(self):
        before = self.seed_previous_install()
        def fail_integration(changes, required=True):
            manage.edit_block(self.bindings, changes[self.bindings])
            raise RuntimeError('integration validation')
        patches = self.common_patches(
            stop=patch('manage.stop_resident', side_effect=[True, False]),
            integration=patch('manage.update_integration', side_effect=fail_integration),
            start=patch('manage.start_resident', return_value='old restarted'))
        with self.assertRaisesRegex(RuntimeError, 'integration validation'):
            self.run_with(patches)
        self.assert_previous_restored(before)

    def test_daemon_start_failure_rolls_back_and_restarts_previous_resident(self):
        before = self.seed_previous_install()
        patches = self.common_patches(
            stop=patch('manage.stop_resident', side_effect=[True, False]),
            start=patch('manage.start_resident', side_effect=[RuntimeError('new daemon'), 'old restarted']))
        with self.assertRaisesRegex(RuntimeError, 'new daemon'):
            self.run_with(patches)
        self.assert_previous_restored(before)

    def test_failed_first_install_removes_only_attempt_changes(self):
        patches = self.common_patches(
            stop=patch('manage.stop_resident', return_value=False),
            fault=patch('manage.after_application_commit', side_effect=RuntimeError('injected')),
            start=patch('manage.start_resident'))
        with self.assertRaisesRegex(RuntimeError, 'injected'):
            self.run_with(patches)
        self.assertFalse(self.target.exists())
        self.assertFalse(self.executable.exists())
        self.assertFalse(manage.config_path().exists())
        self.assertEqual(self.bindings.read_text(), '-- original bindings\n')
        self.assertEqual(self.autostart.read_text(), '-- original autostart\n')


if __name__ == '__main__':
    unittest.main()
