"""Prepare gated follow-ups; neither service is enabled for automatic startup."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = (root/'firmware/run_bl31_prefetch_copy_trial.py').read_text()
source = source.replace('copy-bl31-prefetch-v8-high', 'copy-bl31-prefetch-v8-natural')
source = source.replace("'high_targets': True", "'high_targets': False")
source = source.replace("env=dict(os.environ, TZX_COPY_HIGH_TARGETS='1')", "env={k:v for k,v in os.environ.items() if k != 'TZX_COPY_HIGH_TARGETS'}")
needle = "print('PREFETCH_COPY_TRIAL_BEGIN'"
guard = """state = subprocess.check_output(['systemctl','show','tzx-bl31-prefetch-copy.service',
    '-p','ActiveState','-p','Result','-p','ExecMainStatus'], text=True)
assert 'ActiveState=inactive' in state and 'Result=success' in state and 'ExecMainStatus=0' in state, state
log = subprocess.check_output(['journalctl','-b','-u','tzx-bl31-prefetch-copy.service','-o','cat','--no-pager'], text=True)
assert 'LIBRARY_FIXED_COPY_PASS' in log and 'MISMATCH' not in log
"""
assert source.count(needle) == 1
source = source.replace(needle, guard+needle)
path = root/'firmware/run_bl31_prefetch_natural_copy.py'
assert not path.exists()
compile(source, str(path), 'exec')
path.write_text(source, encoding='utf8', newline='\n')

source = (root/'firmware/run_bl31_streaming_gpu_trial.py').read_text()
source = source.replace('165f940df7bcd97bddce20ec927d53fe32bcf3581fadbd3c10c5404484671e8a', '4a6681c64fc6b173eedf6d3e28062be9596d6ea0c6c1a54b391cdb18a3fce9a9')
source = source.replace("('tzx-bl31-stream-copy-300', 'tzx-bl31-stream-high-v7-aftercache')", "('tzx-bl31-prefetch-copy.service', 'tzx-bl31-prefetch-natural-copy.service')")
start = source.index("probe = Path(")
end = source.index("print('BL31_STREAM_GPU_TRIAL_BEGIN'", start)
source = source[:start]+"subprocess.run(['python3','/home/debian/check_bl31_prefetch_registers.py'],check=True,timeout=30)\n"+source[end:]
source = source.replace('BL31_STREAM', 'BL31_PREFETCH').replace('bl31-stream-first', 'bl31-prefetch-first')
path = root/'firmware/run_bl31_prefetch_gpu_trial.py'
assert not path.exists()
compile(source, str(path), 'exec')
path.write_text(source, encoding='utf8', newline='\n')
source = (root/'firmware/finish_bl31_streaming_gpu_trial.py').read_text().replace('BL31_STREAM', 'BL31_PREFETCH')
path = root/'firmware/finish_bl31_prefetch_gpu_trial.py'
assert not path.exists()
compile(source, str(path), 'exec')
path.write_text(source, encoding='utf8', newline='\n')
source = (root/'firmware/tzx-gpu-bl31-stream-diagnostic.service').read_text()
source = source.replace('cache-mode', 'data-prefetch').replace('bl31_streaming', 'bl31_prefetch')
path = root/'firmware/tzx-gpu-bl31-prefetch-diagnostic.service'
assert not path.exists()
path.write_text(source, encoding='utf8', newline='\n')
print('PREFETCH_FOLLOWUPS_PREPARED_NOT_EXECUTED')
