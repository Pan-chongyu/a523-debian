"""Build frozen read-only register sampling and high-target copy diagnostics in WSL."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

root = Path(__file__).resolve().parents[1]
out = root/'build/cpu-copy-v6'
out.mkdir(exist_ok=False)
source = root/'firmware/library_copy_coherency.c'
shutil.copy2(source, out/source.name)
module = out/'readonly-probe'
module.mkdir()
shutil.copy2(root/'firmware/tzx_cpu_stream_probe.c', module/'tzx_cpu_stream_probe.c')
(module/'Makefile').write_text('obj-m += tzx_cpu_stream_probe.o\n')
commands = [
    ['aarch64-linux-gnu-gcc', '-O2', '-static', '-pthread', '-Wall', '-Wextra',
     '-Wconversion', '-Werror', '-fno-builtin-memcpy', '-fno-builtin-memcmp',
     '-o', str(out/'library-copy-coherency-v6'), str(out/source.name)],
    ['make', '-C', '/opt/a523-debian-20261109/linux-7.3.3',
     'O=/opt/a523-debian-20261109/kernel-cpufreq-framework-build',
     'ARCH=arm64', 'CROSS_COMPILE=aarch64-linux-gnu-', 'M='+str(module), '-j8', 'modules'],
]
with (out/'build.log').open('w') as log:
    for command in commands:
        subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT)
disassembly = subprocess.check_output(['aarch64-linux-gnu-objdump', '-d',
    str(module/'tzx_cpu_stream_probe.ko')], text=True)
assert 'msr\ts3_0_c15_c1_4' not in disassembly.lower()
(out/'readonly-probe.disassembly.txt').write_text(disassembly)
record = {'copy_binary': 'library-copy-coherency-v6',
          'copy_option': 'TZX_COPY_HIGH_TARGETS=1',
          'selection_pool_mib': 2560, 'headroom_mib': 512,
          'pool_released_before_copy': True, 'module_contains_cpuectlr_write': False,
          'files': {str(p.relative_to(out)): {'bytes':p.stat().st_size,
                   'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
                   for p in (out/'library-copy-coherency-v6', out/source.name,
                             module/'tzx_cpu_stream_probe.ko', module/'tzx_cpu_stream_probe.c')}}
(out/'BUILD_COMPLETE.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
