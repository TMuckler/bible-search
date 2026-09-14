import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import manage


class IntegrationEditTests(unittest.TestCase):
    def test_invalid_lua_restores_both_files(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / name for name in ('bindings.lua', 'autostart.lua')]
            for path in paths:
                path.write_text('-- existing user settings\n')
            with patch('manage.reload_hypr', side_effect=[RuntimeError('invalid Lua'), None]):
                with self.assertRaisesRegex(RuntimeError, 'invalid Lua'):
                    manage.update_integration(dict.fromkeys(paths, 'invalid syntax'))
            for path in paths:
                self.assertEqual(path.read_text(), '-- existing user settings\n')
                self.assertEqual(len(list(path.parent.glob(path.name + '.bak.*'))), 1)

    def test_partial_edit_error_restores_first_file(self):
        with tempfile.TemporaryDirectory() as directory:
            first, second = Path(directory) / 'first', Path(directory) / 'second'
            first.write_text('-- first\n')
            second.write_text(manage.END + '\n')
            with patch('manage.reload_hypr'):
                with self.assertRaises(RuntimeError):
                    manage.update_integration({first: 'new', second: 'new'})
            self.assertEqual(first.read_text(), '-- first\n')
            self.assertEqual(second.read_text(), manage.END + '\n')

    def test_reinstall_from_installed_directory_skips_self_copy(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(manage, 'ROOT', Path(directory)), patch('manage.shutil.copytree') as copy:
            manage.copy_application(Path(directory))
            copy.assert_not_called()

    def test_offline_uninstall_does_not_require_compositor(self):
        with patch.dict(os.environ, {}, clear=True), patch('manage.run') as run:
            manage.reload_hypr(required=False)
            run.assert_not_called()
