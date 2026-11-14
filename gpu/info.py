#!/usr/bin/env python3
"""Report actual APIs and clocks without changing versions or performance limits. MIT."""
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent


def main():
    check = subprocess.run([sys.executable, str(HERE / 'opencl_check.py')], capture_output=True, text=True, timeout=90)
    value = {'opencl': json.loads(check.stdout) if check.returncode == 0 else
                      {'status': 'FAIL', 'detail': check.stderr[-2500:]},
             'vulkan_hardware': {'status': 'UNSUPPORTED', 'gpu_architecture': 'Valhall v9 / Mali-G57',
                'reference': 'https://docs.mesa3d.org/drivers/panfrost.html',
                'note': 'No qualified PanVK support for this GPU; software Vulkan is not hardware acceleration.'}}
    for name, path in (('gpu_hz', '/sys/class/devfreq/1800000.gpu/cur_freq'),
                        ('kernel_taint', '/proc/sys/kernel/tainted')):
        value[name] = int(Path(path).read_text())
    try:
        value['performance_guard'] = json.loads(Path('/run/tzx-gpu-performance.json').read_text())
    except PermissionError:
        value['performance_guard'] = {'detail': 'Full guard state is root-readable; existing permissions preserved.'}
        health = Path('/run/tzx-gpu-api-health.json')
        if health.exists():
            summary = json.loads(health.read_text())
            value['performance_guard'].update(state=summary['gpu_guard'], health=summary['status'],
                                              had_issue=summary['had_issue_this_session'])
    value['cpu_policies'] = {p.name: {n: (p / n).read_text().strip()
                           for n in ('scaling_cur_freq', 'scaling_governor')}
                           for p in Path('/sys/devices/system/cpu/cpufreq').glob('policy*')}
    display = subprocess.run(['glxinfo', '-B'], capture_output=True, text=True, timeout=20)
    # With no X session, report that fact instead of inventing a renderer/version.
    value['glxinfo'] = {'exit_code': display.returncode,
                       'detail': display.stdout if display.returncode == 0 else display.stderr.strip()}
    print(json.dumps(value, indent=2, ensure_ascii=False))
    return 0 if check.returncode == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
