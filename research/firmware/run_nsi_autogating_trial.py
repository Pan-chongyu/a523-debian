"""A523-only reversible comparison of upstream RA0/TA auto-gating settings."""
import argparse
import hashlib
import json
import mmap
import os
from pathlib import Path
import struct
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--restore',action='store_true')
args = parser.parse_args()
assert os.geteuid() == 0
assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == '3e01ff55454d20202010209170281b59'
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
state = Path('/run/tzx-nsi-autogating-trial.json')
fd = os.open('/dev/mem',os.O_RDWR|os.O_SYNC)
try:
    with mmap.mmap(fd,4096,mmap.MAP_SHARED,mmap.PROT_READ|mmap.PROT_WRITE,offset=0x02023000) as view:
        offsets = (0xc00,0xe00)
        read = lambda:[struct.unpack_from('<I',view,off)[0] for off in offsets]
        def restore():
            if not state.exists():
                return
            saved = json.loads(state.read_text())
            assert saved['boot_id'] == boot and saved['original'] == [1,3]
            assert all(value in (0,old) for value,old in zip(read(),saved['original']))
            for off,value in zip(offsets,saved['original']):
                struct.pack_into('<I',view,off,value)
                assert struct.unpack_from('<I',view,off)[0] == value
            assert read() == saved['original']
            state.unlink()
            print('NSI_AUTOGATING_ORIGINAL_VALUES_RESTORED',json.dumps(saved),flush=True)
        if args.restore:
            restore()
            raise SystemExit(0)
        assert not state.exists()
        assert os.uname().release == '7.3.3-tzx-a523-accel1' and '#5 ' in os.uname().version
        assert json.loads(Path('/home/debian/installed-bundle.json').read_text())['sha256'] == '3fa0fa94b70f7c4f7f08a9c3fb6dec7d4cef6ce4245338d73d4bb1aaf421b84c'
        assert int(Path('/proc/sys/kernel/tainted').read_text()) == 4096
        for name in ('panfrost','tzx_cpufreq_divider','tzx_cpu_stream_probe'):
            assert not Path('/sys/module',name).exists(),name
        binary = Path('/home/debian/library-copy-coherency-v7')
        assert hashlib.sha256(binary.read_bytes()).hexdigest() == '86d65c7f7d431b459cad4cfa3224d32758a98c1849b78d4d3caea45652da9b9c'
        assert read() == [1,3],read()
        saved = {'boot_id':boot,'original':read(),'trial':[0,0],
                 'addresses':['0x02023c00','0x02023e00'],
                 'reference':'U-Boot dram_sun55i_a523.c sunxi_nsi_init close ra0/ta autogating'}
        state.write_text(json.dumps(saved)+'\n')
        try:
            for off in offsets:
                struct.pack_into('<I',view,off,0)
                assert struct.unpack_from('<I',view,off)[0] == 0
            assert read() == [0,0]
            print('NSI_AUTOGATING_TRIAL_READBACK',json.dumps(saved),flush=True)
            os.sync()
            Path('/proc/sys/vm/drop_caches').write_text('1\n')
            result = subprocess.run([str(binary),'300','/home/debian/copy-nsi-gating-v7-high',
                '255','libc'],env=dict(os.environ,TZX_COPY_HIGH_TARGETS='1'),timeout=350)
            print('NSI_AUTOGATING_COPY_RESULT',result.returncode,flush=True)
        finally:
            restore()
finally:
    os.close(fd)
raise SystemExit(result.returncode)
