"""Host checks for refusing unsafe package transactions, without accessing a GPU."""
import importlib.util
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest


def module(name):
    path = Path(__file__).resolve().parents[1] / 'gpu' / (name + '.py')
    spec = importlib.util.spec_from_file_location('gpu_' + name, path)
    value = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    spec.loader.exec_module(value)
    return value


installer = module('install')
soak = module('soak')
packages = module('fetch_packages')


class GPUUpdateSafety(unittest.TestCase):
    def test_new_dependencies_are_accepted(self):
        installer.reject_package_replacements('Inst clinfo (3.0.25.02.14-1 Debian:13.0/stable [arm64])\n')

    def test_mesa_upgrade_and_removal_are_refused(self):
        for text in ('Inst libegl-mesa0 [25.0.7] (26.0.0 Debian [arm64])\n',
                     'Remv lightdm [1.32.0-6]\n',
                     'Inst libllvm19:arm64 [1:19.1.7-3] (1:19.1.7-4 Debian [arm64])\n'):
            with self.subTest(plan=text), self.assertRaises(RuntimeError):
                installer.reject_package_replacements(text)

    def test_hardware_faults_are_not_classified_as_clean(self):
        for text in ('panfrost 1800000.gpu: gpu sched timeout, js=1',
                     'panfrost 1800000.gpu: Unhandled Page fault in AS0',
                     'BUG: Bad page state in process firefox',
                     'EXT4-fs error (device mmcblk0p2)',
                     'Out of memory: Killed process 123 (python3)',
                     'SError Interrupt on CPU4, code 0xbf000002'):
            with self.subTest(message=text):
                self.assertIsNotNone(soak.KERNEL_FAILURE.search(text))
        self.assertIsNone(soak.KERNEL_FAILURE.search('panfrost 1800000.gpu: mali-g57 id 0x9093'))

    def test_offline_packages_reject_corruption_and_path_escape(self):
        data = b'test Debian payload'
        entry = {'file': 'test_arm64.deb', 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                 'architecture': 'arm64', 'url': 'https://deb.debian.org/debian/pool/main/t/test/test_arm64.deb'}
        manifest = {'files': [entry]}
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / entry['file']).write_bytes(data)
            self.assertEqual(len(packages.verify(folder, manifest)), 1)
            (folder / entry['file']).write_bytes(data[:-1] + b'!')
            with self.assertRaises(RuntimeError):
                packages.verify(folder, manifest)
            for name in ('../escape.deb', '..\\escape.deb', '/tmp/escape.deb'):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    packages.validated_entries({'files': [dict(entry, file=name)]})


if __name__ == '__main__':
    unittest.main()
