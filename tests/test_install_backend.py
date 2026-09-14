import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import manage


class BackendInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.target = Path(self.temp.name) / 'application'
        self.env = patch.dict(os.environ, {'XDG_CONFIG_HOME': self.temp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_existing_backend_is_preserved(self):
        manage.ensure_config('/existing/bible')
        with patch('manage.setup_bundled_backend') as setup:
            manage.configure_backend(self.target)
            setup.assert_not_called()
        self.assertEqual(manage.read_config().bible_command, '/existing/bible')

    def test_discovered_backend_is_preferred(self):
        with patch('manage.discover_backend', return_value='/existing/bible'), patch('manage.setup_bundled_backend') as setup:
            manage.configure_backend(self.target)
            setup.assert_not_called()
        self.assertEqual(manage.read_config().bible_command, '/existing/bible')

    def test_missing_backend_uses_bundle(self):
        managed = str(self.target / 'backend/bible')
        with patch('manage.discover_backend', side_effect=ValueError), patch('manage.setup_bundled_backend', return_value=managed) as setup:
            manage.configure_backend(self.target)
            setup.assert_called_once_with(self.target)
        self.assertEqual(manage.read_config().bible_command, managed)

    def test_retained_managed_config_is_restored(self):
        manage.ensure_config(str(self.target / 'backend/bible'))
        original = manage.config_path().read_bytes()
        with patch('manage.setup_bundled_backend') as setup:
            manage.configure_backend(self.target)
            setup.assert_called_once_with(self.target)
        self.assertEqual(manage.config_path().read_bytes(), original)
