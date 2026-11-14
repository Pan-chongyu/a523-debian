"""Derive an isolated prefetch comparison from the reviewed BL31 transaction."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
folder = root/'build/bl31-prefetch'
record = json.loads((folder/'BUILD_COMPLETE.json').read_text())
sha = lambda data: hashlib.sha256(data).hexdigest()
bl31 = (folder/'bl31.bin').read_bytes()
assert sha(bl31) == record['files']['bl31.bin']
assert len(bl31) == 41124
compose = (root/'tools/compose_bl31_streaming_bundle.py').read_text()
compose = compose.replace("build/bl31-streaming", "build/bl31-prefetch")
compose = compose.replace("assert build['installed_bl31_exact_reproduction']", "assert build['expected_cpuectlr'] == '0x28081000'")
compose = compose.replace("build['candidate_sha256']", "build['files']['bl31.bin']")
compose = compose.replace('disable A55 write streaming', 'disable A55 L1/L3 data prefetch')
compile(compose, 'compose_bl31_prefetch_bundle.py', 'exec')
path = root/'tools/compose_bl31_prefetch_bundle.py'
assert not path.exists()
path.write_text(compose, encoding='utf8', newline='\n')
exec(compile(compose, str(path), 'exec'), {'__file__': str(path)})
manifest = json.loads((folder/'linux-bundle.json').read_text())
assert manifest['bytes'] == 14880768

installer = (root/'firmware/install_bl31_streaming_candidate.py').read_text()
installer = installer.replace('bl31-streaming', 'bl31-prefetch').replace('BL31_STREAM', 'BL31_PREFETCH')
installer = installer.replace('bl31-stream-', 'bl31-prefetch-')
installer = installer.replace('165f940df7bcd97bddce20ec927d53fe32bcf3581fadbd3c10c5404484671e8a', manifest['sha256'])
installer = installer.replace('573865c541b221a8c55dada09496de61ecc3d93eb7641b6713e0412db5e36579', sha(bl31))
installer = installer.replace('prior = os.pread(fd,15020032,98304*512)', 'prior = os.pread(fd,14811136,98304*512)')
installer = installer.replace('606a18d4eeeee98ccdff67fca33911437380e79b970a504f2356ba99dec37116', 'f4055eda1458b18800f99661ed625e081af477eb521b4ac7db0b79cada356b16')
installer = installer.replace('sha(prior[:len(candidate)]) == NEW_SHA', 'sha(os.pread(fd,len(candidate),98304*512)) == NEW_SHA')
compile(installer, 'install_bl31_prefetch_candidate.py', 'exec')
path = root/'firmware/install_bl31_prefetch_candidate.py'
assert not path.exists()
path.write_text(installer, encoding='utf8', newline='\n')

trial = (root/'firmware/run_guarded_copy_trial.py').read_text()
trial = trial.replace('3fa0fa94b70f7c4f7f08a9c3fb6dec7d4cef6ce4245338d73d4bb1aaf421b84c', manifest['sha256'])
trial = trial.replace('copy-readonly-v8-high', 'copy-bl31-prefetch-v8-high')
trial = trial.replace('GUARDED_COPY', 'PREFETCH_COPY')
compile(trial, 'run_bl31_prefetch_copy_trial.py', 'exec')
path = root/'firmware/run_bl31_prefetch_copy_trial.py'
assert not path.exists()
path.write_text(trial, encoding='utf8', newline='\n')
print('PREFETCH_TRIAL_PREPARED', manifest['sha256'], sha(bl31), flush=True)
