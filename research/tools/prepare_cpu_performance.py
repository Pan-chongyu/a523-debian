"""Keep the qualified 480 MHz cooler intact; build an independent variant."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
out = root/'build/cpu-performance/source'
out.mkdir(parents=True, exist_ok=True)
text = (root/'firmware/tzx_cpu_cooling.c').read_text()
replacements = {
    'caps[] = {480000, 240000, 120000}': 'caps[] = {0, 480000, 240000}',
    'caps[state]);': 'state ? caps[state] : cluster->policy->cpuinfo.max_freq);',
    'policy->cpuinfo.max_freq != 480000': 'policy->cpuinfo.max_freq != (i ? 1008000 : 792000)',
    'FREQ_QOS_MAX, caps[0]);': 'FREQ_QOS_MAX, policy->cpuinfo.max_freq);',
    'caps 480/240/120 MHz': 'caps cluster maximum/480/240 MHz',
    'Standard thermal step-wise cooling for the already qualified divider OPPs.':
        'Standard thermal step-wise cooling for fixed-voltage CPU performance.',
    'No PMIC, PLL or DSU access.': 'This cooling module has no PMIC, PLL or DSU access.',
}
for before, after in replacements.items():
    assert text.count(before) == 1, before
    text = text.replace(before, after)
(out/'tzx_cpu_perf_cooling.c').write_text(text)
(out/'tzx_cpufreq_safepll.c').write_bytes((root/'firmware/tzx_cpufreq_safepll.c').read_bytes())
print('INDEPENDENT_CPU_PERFORMANCE_SOURCES_PREPARED')
