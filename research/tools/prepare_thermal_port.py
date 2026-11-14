"""Apply the board-independent fixes selected from the newer A523 THS series."""
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()
before = '''	/*
	 * The GPU sensor (id 2) is unreliable on this silicon; the vendor
	 * driver reads the NPU sensor (id 3) in its place, so do the same.
	 */
	if (id == 2)
		regmap_read(tmdev->regmap,
			    tmdev->chip->temp_data_base + 0x4 * 3, &reg);
'''
assert text.count(before) == 1
text = text.replace(before, '''	/* Read each channel itself, as in Mikhail Kalashnikov's v6 A523
	 * series (2026-09-13). Never convert a different channel's zero
	 * register into a false critical temperature. The caller already
	 * rejects zero samples from this channel. */
''')
# Never publish uncalibrated A523 temperatures as if factory data were valid.
assert text.count('if (!ft_temp)\n\t\treturn 0;') == 2
text = text.replace('if (!ft_temp)\n\t\treturn 0;',
                    'if (!ft_temp)\n\t\treturn -EINVAL;')
text = text.replace('.name = "sun8i-thermal"', '.name = "tzx-a523-thermal"')
path.write_text(text)
print('THERMAL_PORT_PREPARED: BSP calibration retained; GPU channel read directly')
