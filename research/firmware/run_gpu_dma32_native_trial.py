"""Isolate native KMS presentation on a fresh manually loaded GPU instance."""
import subprocess

subprocess.run(['python3', '/home/debian/start_gpu_dma32_trial.py', '--mmu-init',
                '--trial-id', 'native-isolated', '--restart-desktop-on-exit'],
               check=True, timeout=180)
subprocess.run(['systemctl', 'stop', 'lightdm'], check=True, timeout=40)
subprocess.run(['python3', '/home/debian/verify_gpu_clockfix.py', '--backend', 'drm',
                '--present', '--cycles', '2', '--log-prefix', 'gpu-dma32-mmu-native-isolated'],
               check=True, timeout=440)
print('GPU_DMA32_MMU_ISOLATED_NATIVE_PRESENT_PASS', flush=True)
