import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

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

    def local_wheels(self):
        wheels = []
        for distribution, module in (('beautifulsoup4', 'bs4'), ('requests', 'requests'),
                                     ('Unidecode', 'unidecode')):
            normalized = distribution.replace('-', '_')
            wheel = Path(self.temp.name) / f'{normalized}-1.0-py3-none-any.whl'
            dist_info = f'{normalized}-1.0.dist-info'
            with zipfile.ZipFile(wheel, 'w') as archive:
                archive.writestr(f'{module}/__init__.py', 'HEALTHY = True\n')
                archive.writestr(f'{dist_info}/METADATA',
                                 f'Metadata-Version: 2.1\nName: {distribution}\nVersion: 1.0\n')
                archive.writestr(f'{dist_info}/WHEEL',
                                 'Wheel-Version: 1.0\nGenerator: tests\nRoot-Is-Purelib: true\nTag: py3-none-any\n')
                archive.writestr(f'{dist_info}/RECORD', '')
            wheels.append(str(wheel))
        return tuple(wheels)

    def exercise_real_environment_repair(self, damage):
        environment = self.target / 'backend-venv'
        environment.parent.mkdir(parents=True, exist_ok=True)
        if damage == 'missing-pip':
            subprocess.run(['/usr/bin/python', '-m', 'venv', '--without-pip', str(environment)],
                           check=True)
        elif damage == 'unusable-python':
            (environment / 'bin').mkdir(parents=True)
            (environment / 'bin/python').write_text('not an interpreter')
            (environment / 'bin/python').chmod(0o755)
        elif damage == 'missing-imports':
            subprocess.run(['/usr/bin/python', '-m', 'venv', str(environment)], check=True)
            self.assertTrue(manage.python_check(environment / 'bin/python', 'import pip'))
            self.assertFalse(manage.backend_environment_healthy(environment))
        with patch.object(manage, 'BACKEND_PACKAGES', self.local_wheels()):
            wrapper = Path(manage.setup_bundled_backend(self.target))
        self.assertTrue(manage.backend_environment_healthy(environment))
        self.assertTrue(wrapper.is_file())
        self.assertEqual(list(self.target.glob('.backend-venv.*')), [])

    def test_real_environment_recovers_missing_pip(self):
        self.exercise_real_environment_repair('missing-pip')

    def test_real_environment_recovers_unusable_interpreter(self):
        self.exercise_real_environment_repair('unusable-python')

    def test_real_environment_recovers_interrupted_dependency_install(self):
        self.exercise_real_environment_repair('missing-imports')

    def test_failed_staged_rebuild_keeps_existing_environment(self):
        environment = self.target / 'backend-venv'
        (environment / 'bin').mkdir(parents=True)
        interpreter = environment / 'bin/python'
        interpreter.write_bytes(b'original damaged interpreter')
        interpreter.chmod(0o755)
        with patch('manage.build_backend_environment', side_effect=RuntimeError('interrupted')):
            with self.assertRaisesRegex(RuntimeError, 'interrupted'):
                manage.setup_bundled_backend(self.target)
        self.assertEqual(interpreter.read_bytes(), b'original damaged interpreter')
        self.assertEqual(list(self.target.glob('.backend-venv.*')), [])
