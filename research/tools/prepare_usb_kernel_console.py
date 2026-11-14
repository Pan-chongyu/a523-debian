"""Replace only an unused UART early-console argument for USB diagnostics."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
source = root / 'build/cpu-tlbi-kernel'
parser = argparse.ArgumentParser()
parser.add_argument('--name', default='gpu-usb-console')
parser.add_argument('--secondary', action='store_true')
args = parser.parse_args()
assert args.name.startswith('gpu-usb-console') and all(c.isalnum() or c == '-' for c in args.name)
out = root / 'build' / args.name
bundle = (source / 'linux-bundle.bin').read_bytes()
original_sha = '32648d80d699892b3dcfe0be37fdc07a5ed30d95d8b9ad8cf2140bb6f3181799'
assert hashlib.sha256(bundle).hexdigest() == original_sha
manifest = json.loads((source / 'linux-bundle.json').read_text())
item = manifest['items'][1]
offset = (item['lba'] - 4096) * 512
dtb = bundle[offset:offset + item['bytes']]
before = b'earlycon=uart8250,mmio32,0x02500000,115200'
after = b'console=ttyGS0,115200'
if args.secondary:
    # Keep the ordinary UART as /dev/console. Only kernel messages also reach
    # USB, so systemd's status output does not depend on the host opening ACM.
    after = b'console=ttyGS0 console=ttyS0,115200'
assert dtb.count(before) == 1 and len(after) <= len(before)
patched = dtb.replace(before, after.ljust(len(before), b' '))
raw = root / 'build' / (args.name + '.dtb')
raw.write_bytes(patched)
subprocess.run([sys.executable, str(root / 'tools/make_same_slot_dtb.py'),
                str(source), str(raw), str(out)], check=True)
candidate = (out / 'linux-bundle.bin').read_bytes()
candidate_manifest = json.loads((out / 'linux-bundle.json').read_text())
candidate_manifest['base_bundle_verified_boot_ids'] = candidate_manifest.pop('verified_boot_ids', [])
candidate_manifest['verified_boot_ids'] = []
(out / 'linux-bundle.json').write_text(json.dumps(candidate_manifest, indent=2) + '\n')
changes = [i for i, pair in enumerate(zip(bundle, candidate)) if pair[0] != pair[1]]
argument_offset = dtb.index(before)
assert set(changes) <= set(range(16, 20)) | set(range(68, 72)) | set(
    range(offset + argument_offset, offset + argument_offset + len(before)))
experiment = {'purpose': 'USB_kernel_console_diagnostics_only',
              'original_bundle_sha256': original_sha,
              'candidate_bundle_sha256': hashlib.sha256(candidate).hexdigest(),
              'write_ranges': [{'lba': 4096, 'sectors': 1}, {'lba': 28594, 'sectors': 42}],
              'changed_byte_offsets': changes, 'unchanged_full_RAM_GiB': 4,
              'kernel_and_modules_changed': False, 'gpu_autostart_enabled': False}
(out / 'EXPERIMENT.json').write_text(json.dumps(experiment, indent=2) + '\n')
installer = (root / 'firmware/install_memory_window_trial.py').read_text()
needle = "parser.add_argument('--restore', action='store_true')"
assert installer.count(needle) == 1
installer = installer.replace(needle, needle + "\nparser.add_argument('--no-reboot', action='store_true')"
                              + "\nparser.add_argument('--console-warning-recovery', action='store_true')")
needle = "assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096"
assert installer.count(needle) == 1
installer = installer.replace(needle, '''taint = int(Path('/proc/sys/kernel/tainted').read_text())
if taint != 4096:
    assert taint == 4608 and args.console_warning_recovery
    warnings = [line for line in subprocess.check_output(['dmesg'], text=True).splitlines()
                if 'WARNING:' in line]
    assert warnings and all('drivers/usb/gadget/function/u_serial.c:703' in line for line in warnings)
''')
needle = "subprocess.run(['systemd-run'"
assert installer.count(needle) == 1
position = installer.index(needle)
installer = installer[:position] + 'if not args.no_reboot:\n' + ''.join(
    '    ' + line + '\n' for line in installer[position:].splitlines())
for old, new in (
    ('Switch the exact memory-extent DTB and header only; keep a checked full-RAM rollback.',
     'Switch only the USB console boot argument and header; keep the original full bundle.'),
    ('gpu-memory-window-3g', 'gpu-usb-console'),
    ('gpu-memory-window', 'gpu-usb-console'),
    ('full-4g-bundle.bin', 'baseline-bundle.bin'),
    ('MEMORY_WINDOW_FULL_READBACK_PASS', 'USB_CONSOLE_BUNDLE_FULL_READBACK_PASS'),
    ('FULL_4G_RESTORED', 'BASELINE_CONSOLE_RESTORED'),
    ('THREE_GIB_DIAGNOSTIC_INSTALLED_WITH_FULL_4G_ROLLBACK', 'USB_CONSOLE_DIAGNOSTIC_INSTALLED_WITH_BASELINE_ROLLBACK'),
    ('tzx-memory-window-', 'tzx-usb-console-')):
    assert old in installer, old
    installer = installer.replace(old, new)
compile(installer, 'install_usb_console_trial.py', 'exec')
(out / 'install_usb_console_trial.py').write_text(installer, newline='\n')
print('USB_CONSOLE_DIAGNOSTIC_PREPARED', experiment['candidate_bundle_sha256'], len(changes))
