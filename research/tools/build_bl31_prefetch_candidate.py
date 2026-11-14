"""Build an EL3-only comparison of documented A55 data-prefetch controls."""
import difflib,hashlib,json,shutil,subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[1]
base=Path('/opt/a523-debian-20261109')
source=base/'jernej-atf'
candidate=base/'atf-prefetch-source'
out=base/'atf-prefetch-build'
folder=root/'build/bl31-prefetch'
folder.mkdir(exist_ok=True)
assert not (folder/'BUILD_COMPLETE.json').exists() and not candidate.exists()
sha=lambda data:hashlib.sha256(data).hexdigest()
assert sha((source/'build/sun55i_a523/debug/bl31.bin').read_bytes())=='4f86a989584fe1e1312264ce549ecbb81bdc5656a2307cdef525371b81ad371a'
shutil.copytree(source,candidate,ignore=shutil.ignore_patterns('build','.git','__pycache__'))
relative=Path('lib/cpus/aarch64/cortex_a55.S')
before=(candidate/relative).read_text()
needle='cpu_reset_func_start cortex_a55\ncpu_reset_func_end cortex_a55'
replacement='''cpu_reset_func_start cortex_a55
    /* Diagnostic: L1PCTL[15:13]=000, L3PCTL[12:10]=100.
     * Arm Cortex-A55 r2p0 TRM 100442_0200_02_en p270.
     * Apply at EL3 before MMU enable; preserve streaming and other fields.
     */
    dsb sy
    mrs x0, CORTEX_A55_CPUECTLR_EL1
    bic x0, x0, #0xfc00
    orr x0, x0, #0x1000
    msr CORTEX_A55_CPUECTLR_EL1, x0
    isb
    dsb sy
cpu_reset_func_end cortex_a55'''
assert before.count(needle)==1
after=before.replace(needle,replacement)
(candidate/relative).write_text(after)
(folder/'cortex_a55-before.S').write_text(before)
(folder/'cortex_a55-prefetch.S').write_text(after)
(folder/'prefetch.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='a/'+str(relative),tofile='b/'+str(relative))))
with (folder/'build.log').open('w') as log:
    subprocess.run(['make','-C',str(candidate),'BUILD_BASE='+str(out),'PLAT=sun55i_a523',
        'DEBUG=1','LOG_LEVEL=20','CROSS_COMPILE=aarch64-linux-gnu-','BUILD_STRING=',
        'BUILD_MESSAGE_TIMESTAMP="21:25:54, Nov  9 2026"','-j12','bl31'],
        stdout=log,stderr=subprocess.STDOUT,check=True)
built=out/'sun55i_a523/debug'
for name in ('bl31.bin','bl31/bl31.elf','bl31/bl31.map'):
    shutil.copy2(built/name,folder/Path(name).name)
symbols=subprocess.check_output(['aarch64-linux-gnu-nm','-n',str(folder/'bl31.elf')],text=True)
(folder/'symbols.txt').write_text(symbols)
values={row.split()[2]:int(row.split()[0],16) for row in symbols.splitlines() if len(row.split())==3}
assert values['__BL31_END__']<=0x60000
assert 0x21000<=values['__BSS_START__']<=values['__BSS_END__']<=0x2d000
record={'state':'built_not_hardware_tested','only_source_change':str(relative),
 'clear_mask':'0xfc00','set_mask':'0x1000','expected_cpuectlr':'0x28081000',
 'write_timing':'EL3 CPU reset before MMU enable',
 'dram_voltage_clock_changed':False,'kernel_changed':False,
 'reference':'https://documentation-service.arm.com/static/649ac6d4df6cd61d528c2bf1',
 'files':{p.name:sha(p.read_bytes()) for p in folder.iterdir() if p.is_file() and p.suffix!='.log'},
 'symbols':{k:hex(values[k]) for k in ('__BL31_END__','__BSS_START__','__BSS_END__')}}
(folder/'BUILD_COMPLETE.json').write_text(json.dumps(record,indent=2)+'\n')
print('BL31_PREFETCH_CANDIDATE_BUILT',json.dumps(record),flush=True)
