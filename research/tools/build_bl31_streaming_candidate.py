"""Reproduce the installed BL31, then build a separate early-EL3 comparison."""
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

root = Path(__file__).resolve().parents[1]
base = Path('/opt/a523-debian-20261109')
source = base/'jernej-atf'
candidate = base/'atf-streaming-source'
artifacts = root/'build/bl31-streaming'
artifacts.mkdir(parents=True, exist_ok=True)
assert not (artifacts/'BUILD_COMPLETE.json').exists()
old = source/'build/sun55i_a523/debug/bl31.bin'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(old) == '4f86a989584fe1e1312264ce549ecbb81bdc5656a2307cdef525371b81ad371a'
args = ['PLAT=sun55i_a523', 'DEBUG=1', 'LOG_LEVEL=20', 'CROSS_COMPILE=aarch64-linux-gnu-',
        'BUILD_STRING=', 'BUILD_MESSAGE_TIMESTAMP="21:25:54, Nov  9 2026"', '-j12', 'bl31']

def build(path, name):
    out = base/name
    with (artifacts/(name+'.log')).open('w') as log:
        subprocess.run(['make', '-C', str(path), 'BUILD_BASE='+str(out), *args],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    return out/'sun55i_a523/debug'

reference = build(source, 'atf-stream-reference-notice-build')
assert (reference/'bl31.bin').read_bytes() == old.read_bytes(), 'Reference must reproduce installed BL31 exactly'
print('INSTALLED_BL31_EXACT_REPRODUCTION_PASS', sha(old), flush=True)
assert not candidate.exists()
shutil.copytree(source, candidate, ignore=shutil.ignore_patterns('build', '.git', '__pycache__'))
relative = Path('lib/cpus/aarch64/cortex_a55.S')
before = (candidate/relative).read_text()
needle = 'cpu_reset_func_start cortex_a55\ncpu_reset_func_end cortex_a55'
replacement = '''cpu_reset_func_start cortex_a55
    /* TZX diagnostic only: documented CPUECTLR_EL1 streaming thresholds.
     * Apply at EL3 before MMU enable on every core; preserve all other bits.
     * Arm Cortex-A55 r2p0 TRM 100442_0200_02_en pp269,271.
     */
    dsb sy
    mrs x0, CORTEX_A55_CPUECTLR_EL1
    orr x0, x0, #0x7e000000
    msr CORTEX_A55_CPUECTLR_EL1, x0
    isb
    dsb sy
cpu_reset_func_end cortex_a55'''
assert before.count(needle) == 1
after = before.replace(needle, replacement)
(candidate/relative).write_text(after)
(artifacts/'cortex_a55-before.S').write_text(before)
(artifacts/'cortex_a55-streaming.S').write_text(after)
(artifacts/'streaming.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),
    after.splitlines(True), fromfile='a/'+str(relative), tofile='b/'+str(relative))))
out = build(candidate, 'atf-stream-candidate-build')
for name in ('bl31.bin', 'bl31/bl31.elf', 'bl31/bl31.map'):
    shutil.copy2(out/name, artifacts/Path(name).name)
symbols = subprocess.check_output(['aarch64-linux-gnu-nm', '-n', str(artifacts/'bl31.elf')], text=True)
(artifacts/'symbols.txt').write_text(symbols)
values = {row.split()[2]: int(row.split()[0], 16) for row in symbols.splitlines() if len(row.split()) == 3}
assert values['__BL31_END__'] <= 0x60000
assert 0x21000 <= values['__BSS_START__'] <= values['__BSS_END__'] <= 0x2d000
record = {'state': 'built_not_hardware_tested', 'installed_bl31_exact_reproduction': True,
    'old_sha256': sha(old), 'candidate_sha256': sha(artifacts/'bl31.bin'),
    'candidate_bytes': (artifacts/'bl31.bin').stat().st_size,
    'only_source_change': str(relative), 'register': 'CPUECTLR_EL1', 'set_mask': '0x7e000000',
    'timing': 'EL3 CPU reset function before MMU enable, all cores',
    'kernel_changed': False, 'dram_voltage_clock_changed': False,
    'reference': 'https://documentation-service.arm.com/static/649ac6d4df6cd61d528c2bf1',
    'symbols': {k:hex(values[k]) for k in ('__BL31_END__','__BSS_START__','__BSS_END__')},
    'files': {p.name: sha(p) for p in artifacts.iterdir() if p.is_file() and p.suffix not in ('.log',)}}
(artifacts/'BUILD_COMPLETE.json').write_text(json.dumps(record, indent=2)+'\n')
print('BL31_STREAMING_CANDIDATE_BUILT', json.dumps(record), flush=True)
