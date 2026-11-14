"""Consent/cancellation are exercised at the shared GUI/CLI USB boundary."""
import copy,json,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import flash

class SessionTests(unittest.TestCase):
    def manifest(self):
        return json.loads((Path(__file__).resolve().parents[1]/'board/release-manifest.json').read_text())

    def test_install_cannot_open_usb_without_confirmation(self):
        with patch('flasher.fel.Fel') as device:
            with self.assertRaises(PermissionError):flash.install(Path('unused'),self.manifest())
            device.assert_not_called()

    def test_cancelled_preparation_never_downloads_or_opens_usb(self):
        cancel=threading.Event();cancel.set()
        with tempfile.TemporaryDirectory() as folder,patch('flash.download') as download,patch('flasher.fel.Fel') as device:
            with self.assertRaises(flash.Cancelled):flash.prepare_assets(Path(folder),cancel=cancel)
            download.assert_not_called();device.assert_not_called()

    def test_corrupt_asset_rejected_before_usb(self):
        with tempfile.TemporaryDirectory() as folder,patch('flasher.fel.Fel') as device,patch('flash.ctypes') as native,patch('flash.os.geteuid',return_value=0,create=True):
            native.windll.shell32.IsUserAnAdmin.return_value=True
            manifest=self.manifest();asset=manifest['files']['image'];(Path(folder)/asset['name']).write_bytes(b'corrupt')
            with self.assertRaises(ValueError):flash.install(Path(folder),manifest,confirmed=True)
            device.assert_not_called()

    def test_version_mismatch_cannot_trigger_downloads(self):
        with tempfile.TemporaryDirectory() as folder,patch('flash.download') as download:
            manifest=self.manifest();manifest['version']='wrong-version';path=Path(folder)/'manifest.json';path.write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):flash.prepare_assets(Path(folder)/'cache',path)
            download.assert_not_called()

if __name__=='__main__':unittest.main()
