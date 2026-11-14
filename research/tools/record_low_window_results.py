"""Record completed low-window tests and the subsequent inconclusive rail trial."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
evidence = root/'evidence'
cpu = (evidence/'k5-low-window-copy-final-and-audit-start.txt').read_text(encoding='utf8')
first = (evidence/'k5-low-window-gpu-host-unit.txt').read_text(encoding='utf8')
last = (evidence/'k5-low-window-gpu-host-unit-final.txt').read_text(encoding='utf8')
restore = (evidence/'k5-low-window-complete-and-restore.txt').read_text(encoding='utf8')
assert all(s in cpu for s in ('Result=success', 'ExecMainStatus=0', 'copies=55142', 'seconds_per_phase=300'))
assert first.count('MEMORY_TEST_1792_MIB_8_THREADS_PASS') == 3
assert 'GPU_FULL_X11_WITH_4_SCENES_AND_THREE_1792MIB_CPU_MEMORY_PASSES' in first
assert all(s in last for s in ('GPU_CLOCKFIX_TWO_FULL_SCENE_PASSES', 'LIBRARY_PAGE_WATCH_CLEAN_STOP 1861',
    'GPU_FULL_COMBINED_AND_RESIDENT_LIBRARY_GUARD_PASS', 'MAPPED_FILES_AND_GPU_BINARIES_INTEGRITY_PASS'))
assert all(s in restore for s in ('Result=success', 'ActiveState=inactive', 'LOW_WINDOW_SELECTED_FULL_PAYLOAD_READBACK_PASS 65536'))
files = ('k5-low-window-copy-final-and-audit-start.txt', 'k5-low-window-before-gpu-files-final.txt',
         'k5-low-window-gpu-host-unit.txt', 'k5-low-window-gpu-host-unit-final.txt',
         'k5-low-window-complete-and-restore.txt', 'k5-full-memory-restored-and-pmic-live.txt',
         'dram-rail-baseline-progress.txt', 'dram-rail-all-unit-journal.txt',
         'dram-rail-comparison-host-kernel.txt', 'dram-rail-state-captures-and-audit-start.txt',
         'dram-rail-recovery-files-final.txt')
record = {'low_window_boot_id': '047bab81-e3ae-4750-a016-ab531ed0bc82',
    'diagnostic_RAM_bytes': 3 << 30, 'original_BL31_and_kernel_5': True,
    'cpu_test': {'seconds': 300, 'copies': 55142, 'result': 'PASS'},
    'gpu_test': {'X11_full_suites': 4, 'native_full_suites': 2,
        'concurrent_RAM_MiB': 1792, 'RAM_passes': 3, 'resident_watch_iterations': 1861,
        'result': 'bounded PASS', 'persistent_enabled': False},
    'full_4GiB_restored': True, 'full_RAM_baseline_result': 'transient comparison failure after 568 copies',
    'rail_trial': {'setpoint_before_mV': 1100, 'intended_setpoint_mV': 1200,
        'voltage_write_or_1200mV_readback_confirmed': False,
        'result': 'inconclusive; page-table corruption and reset before first durable trial marker',
        'after_reboot_register_0x85': '0xbc', 'after_reboot_setpoint_mV': 1100,
        'post_reboot_files_checked': 447, 'post_reboot_file_audit': 'PASS'},
    'overall_stability_qualified': False,
    'evidence_sha256': {name: hashlib.sha256((evidence/name).read_bytes()).hexdigest() for name in files}}
(root/'build/k5-low-window-3g/BOUNDED_TEST_RESULTS.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf8')

checkpoint = ('2026-11-12 14:14：原#5/原BL31/8核的临时3GiB地址范围对照通过：'
    '300秒55142份普通复制、四轮X11、两轮直接显示、三轮1792MiB内存负载及1861轮库页监控，'
    '未重启，事后290文件审计通过。13:57已撤回，完整4GiB恢复。'
    '随后完整4GiB基线568份复制再次出现瞬时比较异常；拟进行1.20V对照时启动路径发生坏页表与重启，'
    '没有任何电压写入回读，故调压结果不成立。当前boot `e34f0da3-2946-4b98-9c29-59e265d2937a`，'
    '原电压寄存器0xbc/1.10V，GPU未加载、CPUfreq临时停止，447文件审计通过。'
    'RTC保存读取翻译故障FSC7，PC `set_root+0x40`，FAR只保留低40位，未伪造高位。'
    '正在复核MMC DMA散列表及地址掩码的上游修复，尚未应用；适配和整机稳定性未完成。')
for name, after in (('PROGRESS.md', '## 当前结果\n\n'),
                    ('GPU-MEMORY-DEBUG.md', '\n\n'), ('CPU-POWER-BRINGUP.md', '\n\n')):
    path = root/name
    text = path.read_text(encoding='utf8')
    assert checkpoint not in text
    pos = text.index(after)+len(after)
    path.write_text(text[:pos]+checkpoint+'\n\n'+text[pos:], encoding='utf8', newline='\n')
path = root/'CPU-COPY-ISOLATION.md'
text = path.read_text(encoding='utf8')
text = text.replace('2026-11-12：完整4GiB保留。GPU没有加载；每次比较固定原480MHz，不调整电压。',
    '2026-11-12：当前完整4GiB已恢复、GPU未加载、固定原480MHz。3GiB临时对照及拟调压的中断记录见文末。')
text += ('\n## 3GiB地址范围结果与完整4GiB复现\n\n'+checkpoint+'\n\n'
    '首次1920MiB GPU负载因512MiB余量不足而拒绝，不属于硬件失败；改用独立标签1792MiB完成，旧记录保留。'
    'CPU源和八目标均在物理4GiB以下，5450页零重复；GPU最高记录温度约54.9°C。'
    '本轮没有关闭预取或写流，亦未额外插入DSB。结果证据和哈希见 `build/k5-low-window-3g/BOUNDED_TEST_RESULTS.json`。\n\n'
    '完整4GiB基线14:02:53至14:02:57失败，CPU7第78轮、合计568份；源及八目标全为高地址。'
    '初次memcmp=-1、重复=0、逐字节差异0，五份捕获均与可信libgio一致，是瞬时异常，不能称为持久错误页。'
    '5450个PFN零重复/变化。此时DCDC3仍0xbc。\n\n'
    '14:03:51计划中的电源对照只记录到drop_caches，未留下BEGIN、STEP或1200mV回读；'
    '因而不能声称已执行升压，亦不能以该复位证明电压因果关系。'
    '主机捕获journalctl页表内容已变成库数据形态并经el0_undef退出，RTC首次捕获压缩data-abort，'
    'FSC7=level3 translation fault、read、PC=ffff80008016f5d4；FAR前缀未知，只有low40=ff916fdbb4。'
    '14:12:44恢复后447文件477273374字节审计通过。两个电源诊断单元仅手动，不开机启动，准备撤销执行入口。\n')
path.write_text(text, encoding='utf8', newline='\n')
path = root/'RTC-ABORT-CONTEXT.md'
text = path.read_text(encoding='utf8')
text += ('\n14:04真实样本：boot `e34f0da3-2946-4b98-9c29-59e265d2937a` 读取前一boot异常，'
    'GP1..3=`d645bd75,916fdbb4,80947fff`，CPU1，PC `ffff80008016f5d4`=原#5 `set_root+0x40`，'
    '保存ESR=`96000007`、mask=`fe001fff`，EC37/FSC7、read。FAR不在字典，正确报告'
    '`fault_far=null`、`fault_far_low40=ff916fdbb4`、`fault_far_complete=false`，不生成完整地址。'
    '该次主机同时捕获坏页表，完整4GiB/原BL31；尚不能确定损坏写入者或将其归因电压。'
    '当前已退出3GiB诊断，不需再运行low-window回退。\n')
path.write_text(text, encoding='utf8', newline='\n')
print('LOW_WINDOW_RESULTS_AND_CHECKPOINTS_RECORDED')
