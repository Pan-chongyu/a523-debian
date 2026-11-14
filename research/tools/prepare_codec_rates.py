"""Generate a rate-only codec candidate from the frozen 48 kHz source."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
base = (root/'firmware/tzx_codec.c').read_bytes()
assert hashlib.sha256(base).hexdigest() == 'a64dd070235dbd229a3fb42f889a362855571a7e18c1bc0c806b0f5bb8461442'
source = base.decode()
patches = [
    (' * exposes only 48 kHz S16, stereo playback and ADC1 mono capture.',
     ' * rate candidate: fixed 24.576 MHz, S16, 8/12/16/24/32/48 kHz; DAC also 96 kHz.'),
    ('    int ret;\n    if (params_rate(params) != 48000 || params_format(params) != SNDRV_PCM_FORMAT_S16_LE)\n        return -EINVAL;',
     '''    int ret;
    unsigned int rate_bits;
    if (params_format(params) != SNDRV_PCM_FORMAT_S16_LE)
        return -EINVAL;
    /* A523 BSP sample_rate_conv encodings, only the 48 kHz clock family.
     * DAC/ADC clocks stay at the qualified 24.576 MHz in every case. */
    switch (params_rate(params)) {
    case 8000: rate_bits = 5; break;
    case 12000: rate_bits = 4; break;
    case 16000: rate_bits = 3; break;
    case 24000: rate_bits = 2; break;
    case 32000: rate_bits = 1; break;
    case 48000: rate_bits = 0; break;
    case 96000:
        if (!tx) return -EINVAL;
        rate_bits = 7;
        break;
    default: return -EINVAL;
    }'''),
    ('                          3 << 24 | (params_channels(params) == 1 ? BIT(6) : 0));',
     '                          rate_bits << 29 | 3 << 24 | (params_channels(params) == 1 ? BIT(6) : 0));'),
    ('        regmap_update_bits(c->map, 0x30, GENMASK(31, 29) | BIT(24) | BIT(16), BIT(24));',
     '        regmap_update_bits(c->map, 0x30, GENMASK(31, 29) | BIT(24) | BIT(16), rate_bits << 29 | BIT(24));'),
    ('#define TZX_PLAYBACK {', '''#define TZX_RATE_BASE (SNDRV_PCM_RATE_8000 | SNDRV_PCM_RATE_12000 | SNDRV_PCM_RATE_16000 | \\
                       SNDRV_PCM_RATE_24000 | SNDRV_PCM_RATE_32000 | SNDRV_PCM_RATE_48000)
#define TZX_PLAYBACK {'''),
    ('    .rates = SNDRV_PCM_RATE_48000, .formats = SNDRV_PCM_FMTBIT_S16_LE }\n#define TZX_CAPTURE',
     '    .rates = TZX_RATE_BASE | SNDRV_PCM_RATE_96000, .formats = SNDRV_PCM_FMTBIT_S16_LE }\n#define TZX_CAPTURE'),
    ('    .rates = SNDRV_PCM_RATE_48000, .formats = SNDRV_PCM_FMTBIT_S16_LE }\nstatic struct snd_soc_dai_driver cpu_dai',
     '    .rates = TZX_RATE_BASE, .formats = SNDRV_PCM_FMTBIT_S16_LE }\nstatic struct snd_soc_dai_driver cpu_dai'),
    ('48k S16 PCM registered, ADC1 and stereo DAC, DAPM speaker amplifier PH6',
     '8-48k S16 ADC1, 8-96k stereo DAC, fixed-clock rate candidate, speaker PH6'),
]
for old, new in patches:
    assert source.count(old) == 1, old
    source = source.replace(old, new)
out = root/'build/audio-rates'
out.mkdir(exist_ok=True)
(out/'tzx_codec.c').write_text(source, encoding='utf8', newline='\n')
(out/'SOURCE_CHANGE.json').write_text(json.dumps({
    'base_sha256': hashlib.sha256(base).hexdigest(),
    'candidate_sha256': hashlib.sha256((out/'tzx_codec.c').read_bytes()).hexdigest(),
    'changes': 'Rate selection and exposed masks only; same clocks, format, DMA, channels, analog, amp, and lifetime',
    'playback_rates_Hz': [8000, 12000, 16000, 24000, 32000, 48000, 96000],
    'capture_rates_Hz': [8000, 12000, 16000, 24000, 32000, 48000],
    'source_url': 'https://raw.githubusercontent.com/AvaotaSBC/linux/a464bc4feaff7b102dac6362b44ac3303ec7cae1/bsp/drivers/sound/platform/snd_sun55iw3_codec.c',
    'hardware_qualified': False}, indent=2)+'\n')
print('FIXED_CLOCK_CODEC_RATE_CANDIDATE_SOURCE_PREPARED')
