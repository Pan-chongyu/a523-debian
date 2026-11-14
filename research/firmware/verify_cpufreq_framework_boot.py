"""Record the first #5 boot while checking the atomic header switch and old payload."""
import hashlib
import json
import mmap
import os
from pathlib import Path
import struct
import subprocess
import uuid
import zlib

assert os.geteuid() == 0
assert os.uname().release == '7.3.3-tzx-a523-accel1' and '#5 ' in os.uname().version
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
assert not Path('/sys/module/panfrost').exists()
assert not Path('/sys/module/tzx_cpufreq_divider').exists()
for unit in ('lightdm', 'tzx-display', 'tzx-touch', 'tzx-audio', 'tzx-wifi',
             'tzx-bluetooth', 'tzx-cpub', 'tzx-battery', 'tzx-tablet-keys'):
    assert subprocess.check_output(['systemctl', 'is-active', unit], text=True).strip() == 'active', unit
failed = subprocess.check_output(['systemctl', '--failed', '--no-legend'], text=True)
assert not failed.strip(), failed

new_sha = '3fa0fa94b70f7c4f7f08a9c3fb6dec7d4cef6ce4245338d73d4bb1aaf421b84c'
old_sha = '32648d80d699892b3dcfe0be37fdc07a5ed30d95d8b9ad8cf2140bb6f3181799'
new_size, old_size = 14876672, 14809088
with open('/dev/mmcblk0', 'rb', buffering=0) as disk:
    new = os.pread(disk.fileno(), new_size, 65536 * 512)
    active_header = os.pread(disk.fileno(), 512, 4096 * 512)
    old = (Path('/root/tzx-recovery/cpufreq-framework/bundle-before-cpufreq-framework.bin')
           .read_bytes())
    old_payload = os.pread(disk.fileno(), old_size - 512, 4097 * 512)
    gpt = os.pread(disk.fileno(), 512, 512)
assert hashlib.sha256(new).hexdigest() == new_sha
assert active_header == new[:512]
assert hashlib.sha256(old).hexdigest() == old_sha
assert old_payload == old[512:], 'The original #4 image payload must remain in its old slot'
assert gpt[:8] == b'EFI PART'
assert str(uuid.UUID(bytes_le=gpt[56:72])) == 'c9a3ed89-a30d-4fbc-ba53-208fa8617cbc'
table_lba, entries, stride, expected_crc = struct.unpack_from('<QIII', gpt, 72)
fd = os.open('/dev/mmcblk0', os.O_RDONLY)
try:
    table = os.pread(fd, entries * stride, table_lba * 512)
finally:
    os.close(fd)
assert zlib.crc32(table) == expected_crc
partitions = [table[n*stride:(n+1)*stride] for n in range(entries)
              if any(table[n*stride:n*stride+16])]
assert min(struct.unpack_from('<Q', item, 32)[0] for item in partitions) >= 131072

state_path = Path('/var/lib/tzx/cpufreq-framework-installed.json')
state = json.loads(state_path.read_text())
assert state['state'] == 'framework_5_installed_reboot_pending'
state.update(state='framework_5_booted_manual_test_pending', boot_id=
             Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
             boot_verified=True, old_payload_preserved=True, gpt_preserved=True,
             cpufreq_driver_loaded=False, gpu_loaded=False)
state_path.write_text(json.dumps(state, indent=2) + '\n')
os.sync()
print('CPUFREQ_FRAMEWORK_BOOT_AND_OLD_SLOT_ROLLBACK_PROOF_PASS', json.dumps(state), flush=True)
