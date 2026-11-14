// SPDX-License-Identifier: GPL-2.0-or-later
/* A523 codec bring-up. Register definitions/sequences: Allwinner sun55iw3
 * BSP pinned in upstream/a523-audio-bsp/SOURCES.json. This initial PCM path
 * exposes only 48 kHz S16, stereo playback and ADC1 mono capture.
 * Speaker PH6 was confirmed by the user in a bounded enable test.
 * No PMIC voltage changes.
 */
#include <linux/clk.h>
#include <linux/delay.h>
#include <linux/dma-mapping.h>
#include <linux/gpio/consumer.h>
#include <linux/gpio/machine.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/regmap.h>
#include <linux/reset.h>
#include <sound/dmaengine_pcm.h>
#include <sound/pcm_params.h>
#include <sound/soc.h>
#include <sound/tlv.h>

struct tzx_codec {
    struct regmap *map;
    struct clk *bus, *dac, *adc, *parent;
    struct reset_control *reset;
    struct gpio_desc *amp;
    void __iomem *pio;
    u32 saved_amp_mux, saved_amp_data;
    bool amp_claimed;
    struct snd_dmaengine_dai_dma_data tx, rx;
    struct snd_soc_card card;
    struct snd_soc_dai_link link;
    struct snd_soc_dai_link_component cpus, codecs, platforms;
    u32 saved_analog[5];
};
static int overlay_id;
static struct gpiod_lookup_table amp_lookup = {
    .dev_id = "7110000.audio-codec",
    .table = { GPIO_LOOKUP("2000000.pinctrl", 230, "speaker-enable", GPIO_ACTIVE_HIGH), {} }
};
extern const u8 tzx_codec_overlay[], tzx_codec_overlay_end[];

/* ASoC stores the card in card->dev drvdata during registration. This board
 * shares one device between the machine and codec, as sun4i-codec does. */
static struct tzx_codec *codec_data(struct device *dev)
{
    return snd_soc_card_get_drvdata(dev_get_drvdata(dev));
}

static int codec_startup(struct snd_pcm_substream *s, struct snd_soc_dai *dai)
{
    struct tzx_codec *c = codec_data(dai->dev);
    return clk_prepare_enable(s->stream == SNDRV_PCM_STREAM_PLAYBACK ? c->dac : c->adc);
}
static void codec_shutdown(struct snd_pcm_substream *s, struct snd_soc_dai *dai)
{
    struct tzx_codec *c = codec_data(dai->dev);
    clk_disable_unprepare(s->stream == SNDRV_PCM_STREAM_PLAYBACK ? c->dac : c->adc);
}
static int codec_params(struct snd_pcm_substream *s, struct snd_pcm_hw_params *params,
                        struct snd_soc_dai *dai)
{
    struct tzx_codec *c = codec_data(dai->dev);
    bool tx = s->stream == SNDRV_PCM_STREAM_PLAYBACK;
    struct clk *clock = tx ? c->dac : c->adc;
    int ret;
    if (params_rate(params) != 48000 || params_format(params) != SNDRV_PCM_FORMAT_S16_LE)
        return -EINVAL;
    ret = clk_set_rate(clock, 24576000);
    if (ret) return ret;
    if (clk_get_rate(clock) != 24576000) return -ERANGE;
    if (tx)
        regmap_update_bits(c->map, 0x10, GENMASK(31, 29) | GENMASK(25, 24) | BIT(6) | BIT(5),
                          3 << 24 | (params_channels(params) == 1 ? BIT(6) : 0));
    else
        regmap_update_bits(c->map, 0x30, GENMASK(31, 29) | BIT(24) | BIT(16), BIT(24));
    return 0;
}
static int codec_prepare(struct snd_pcm_substream *s, struct snd_soc_dai *dai)
{
    struct tzx_codec *c = codec_data(dai->dev);
    bool tx = s->stream == SNDRV_PCM_STREAM_PLAYBACK;
    regmap_update_bits(c->map, tx ? 0x10 : 0x30, BIT(0), BIT(0));
    regmap_write(c->map, tx ? 0x14 : 0x38, tx ? 0x0e : 0x0a);
    regmap_write(c->map, tx ? 0x24 : 0x44, 0);
    return 0;
}
static int codec_trigger(struct snd_pcm_substream *s, int command, struct snd_soc_dai *dai)
{
    struct tzx_codec *c = codec_data(dai->dev);
    bool tx = s->stream == SNDRV_PCM_STREAM_PLAYBACK, on;
    switch (command) {
    case SNDRV_PCM_TRIGGER_START: case SNDRV_PCM_TRIGGER_RESUME:
    case SNDRV_PCM_TRIGGER_PAUSE_RELEASE: on = true; break;
    case SNDRV_PCM_TRIGGER_STOP: case SNDRV_PCM_TRIGGER_SUSPEND:
    case SNDRV_PCM_TRIGGER_PAUSE_PUSH: on = false; break;
    default: return -EINVAL;
    }
    regmap_update_bits(c->map, tx ? 0x10 : 0x30, BIT(tx ? 4 : 3), on ? BIT(tx ? 4 : 3) : 0);
    return 0;
}
static int cpu_probe(struct snd_soc_dai *dai)
{
    struct tzx_codec *c = codec_data(dai->dev);
    snd_soc_dai_init_dma_data(dai, &c->tx, &c->rx);
    return 0;
}
static const struct snd_soc_dai_ops cpu_ops = {
    .probe = cpu_probe, .startup = codec_startup, .shutdown = codec_shutdown,
    .hw_params = codec_params, .prepare = codec_prepare, .trigger = codec_trigger,
};
#define TZX_PLAYBACK { .stream_name = "Playback", .channels_min = 1, .channels_max = 2, \
    .rates = SNDRV_PCM_RATE_48000, .formats = SNDRV_PCM_FMTBIT_S16_LE }
#define TZX_CAPTURE { .stream_name = "Capture", .channels_min = 1, .channels_max = 1, \
    .rates = SNDRV_PCM_RATE_48000, .formats = SNDRV_PCM_FMTBIT_S16_LE }
static struct snd_soc_dai_driver cpu_dai = {
    .name = "tzx-a523-cpu", .playback = TZX_PLAYBACK, .capture = TZX_CAPTURE, .ops = &cpu_ops,
};
static struct snd_soc_dai_driver analog_dai = {
    .name = "tzx-a523-codec", .playback = TZX_PLAYBACK, .capture = TZX_CAPTURE,
};
static const DECLARE_TLV_DB_SCALE(dac_volume, -11925, 75, 1);
static const DECLARE_TLV_DB_SCALE(mic_gain, 0, 100, 0);
static const unsigned int lineout_volume[] = {
    TLV_DB_RANGE_HEAD(2),
    0, 1, TLV_DB_SCALE_ITEM(0, 0, 1),
    2, 31, TLV_DB_SCALE_ITEM(-4350, 150, 1),
};
static const char *const loop_text[] = { "Off", "DACLR-to-ADC12", "DACL-to-ADC3" };
static SOC_ENUM_SINGLE_DECL(loop_mode, 0x28, 0, loop_text);
static const struct snd_kcontrol_new controls[] = {
    /* Cap initial DAC gain at 0 dB. Start muted and at -24 dB. */
    SOC_DOUBLE_TLV("Master Playback Volume", 0x04, 8, 0, 159, 0, dac_volume),
    SOC_DOUBLE("Master Playback Switch", 0x310, 12, 10, 1, 0),
    SOC_SINGLE_TLV("Lineout Playback Volume", 0x310, 0, 31, 0, lineout_volume),
    SOC_SINGLE_TLV("ADC1 Capture Volume", 0x34, 0, 159, 0, dac_volume),
    SOC_SINGLE_TLV("Mic1 Capture Gain", 0x300, 8, 31, 0, mic_gain),
    SOC_ENUM("ADDA Loop Mode", loop_mode),
};
static int mic_event(struct snd_soc_dapm_widget *widget, struct snd_kcontrol *control, int event)
{
    struct snd_soc_component *component = snd_soc_dapm_to_component(widget->dapm);
    struct tzx_codec *c = codec_data(component->dev);
    bool on = SND_SOC_DAPM_EVENT_ON(event);
    regmap_update_bits(c->map, 0x300, BIT(31) | BIT(30), on ? BIT(31) | BIT(30) : 0);
    regmap_update_bits(c->map, 0x318, BIT(7), on ? BIT(7) : 0);
    if (on) msleep(240);
    regmap_update_bits(c->map, 0x30, BIT(28), on ? BIT(28) : 0);
    return 0;
}
static int speaker_event(struct snd_soc_dapm_widget *widget, struct snd_kcontrol *control, int event)
{
    struct snd_soc_component *component = snd_soc_dapm_to_component(widget->dapm);
    struct tzx_codec *c = codec_data(component->dev);
    bool on = SND_SOC_DAPM_EVENT_ON(event);
    gpiod_set_value_cansleep(c->amp, on);
    if (on) msleep(10);
    return 0;
}
static const struct snd_soc_dapm_widget widgets[] = {
    SND_SOC_DAPM_AIF_IN("DACL", "Playback", 0, 0x310, 15, 0),
    SND_SOC_DAPM_AIF_IN("DACR", "Playback", 1, 0x310, 14, 0),
    SND_SOC_DAPM_SUPPLY("DAC Digital", 0x00, 31, 0, NULL, 0),
    SND_SOC_DAPM_PGA("Line Left", 0x310, 13, 0, NULL, 0),
    SND_SOC_DAPM_PGA("Line Right", 0x310, 11, 0, NULL, 0),
    SND_SOC_DAPM_OUTPUT("LINEOUTL"), SND_SOC_DAPM_OUTPUT("LINEOUTR"),
    SND_SOC_DAPM_SPK("Speaker", speaker_event),
    SND_SOC_DAPM_INPUT("MIC1"),
    SND_SOC_DAPM_PGA_E("Mic Bias", SND_SOC_NOPM, 0, 0, NULL, 0,
                       mic_event, SND_SOC_DAPM_PRE_PMU | SND_SOC_DAPM_POST_PMD),
    SND_SOC_DAPM_AIF_OUT("ADC1", "Capture", 0, 0x50, 0, 0),
};
static const struct snd_soc_dapm_route routes[] = {
    {"DACL", NULL, "DAC Digital"}, {"DACR", NULL, "DAC Digital"},
    {"Line Left", NULL, "DACL"}, {"Line Right", NULL, "DACR"},
    {"LINEOUTL", NULL, "Line Left"}, {"LINEOUTR", NULL, "Line Right"},
    {"Speaker", NULL, "LINEOUTL"}, {"Speaker", NULL, "LINEOUTR"},
    {"Mic Bias", NULL, "MIC1"}, {"ADC1", NULL, "Mic Bias"},
};
static int component_probe(struct snd_soc_component *component)
{
    struct tzx_codec *c = codec_data(component->dev);
    snd_soc_component_init_regmap(component, c->map);
    return 0;
}
static const struct snd_soc_component_driver analog = {
    .name = "tzx-a523-analog", .probe = component_probe, .debugfs_prefix = "analog",
    .controls = controls, .num_controls = ARRAY_SIZE(controls),
    .dapm_widgets = widgets, .num_dapm_widgets = ARRAY_SIZE(widgets),
    .dapm_routes = routes, .num_dapm_routes = ARRAY_SIZE(routes),
};
static const struct snd_soc_component_driver digital = {
    .name = "tzx-a523-digital", .debugfs_prefix = "digital",
};
static const struct regmap_config regconfig = {
    .reg_bits = 32, .val_bits = 32, .reg_stride = 4, .max_register = 0x348,
};
static void disable_bus(void *data) { clk_disable_unprepare(data); }
static void assert_reset(void *data) { reset_control_assert(data); }
static void unregister_pcm(void *data) { snd_dmaengine_pcm_unregister(data); }
static void restore_amp_pin(void *data)
{
    struct tzx_codec *c = data;
    /* devm_gpiod_get was registered after this action, so it is freed first. */
    if (!c->amp_claimed) return;
    writel((readl(c->pio + 0x160) & ~BIT(6)) | c->saved_amp_data, c->pio + 0x160);
    writel((readl(c->pio + 0x150) & ~GENMASK(27, 24)) | c->saved_amp_mux, c->pio + 0x150);
}
static void restore_analog(void *data)
{
    struct tzx_codec *c = data;
    regmap_update_bits(c->map, 0x310, BIT(7) | GENMASK(25, 24) | GENMASK(15, 10) | GENMASK(4, 0),
                      c->saved_analog[0]);
    regmap_update_bits(c->map, 0x31c, BIT(1), c->saved_analog[1]);
    regmap_update_bits(c->map, 0x348, BIT(24) | BIT(15), c->saved_analog[2]);
    regmap_update_bits(c->map, 0x300, GENMASK(12, 8), c->saved_analog[3]);
    regmap_update_bits(c->map, 0x28, GENMASK(2, 0), c->saved_analog[4]);
}
static ssize_t pcm_counters_show(struct device *dev, struct device_attribute *attribute, char *buffer)
{
    struct tzx_codec *c = codec_data(dev);
    unsigned int tx, rx, tx_status, rx_status;
    int ret;
    ret = regmap_read(c->map, 0x24, &tx); if (ret) return ret;
    ret = regmap_read(c->map, 0x44, &rx); if (ret) return ret;
    ret = regmap_read(c->map, 0x14, &tx_status); if (ret) return ret;
    ret = regmap_read(c->map, 0x38, &rx_status); if (ret) return ret;
    return sysfs_emit(buffer, "dac_samples=%u adc_samples=%u dac_fifo=%08x adc_fifo=%08x\n",
                      tx, rx, tx_status, rx_status);
}
static DEVICE_ATTR_RO(pcm_counters);
static ssize_t speaker_shutdown_store(struct device *dev, struct device_attribute *attribute,
                                     const char *buffer, size_t count)
{
    struct tzx_codec *c = codec_data(dev);
    bool off;
    if (kstrtobool(buffer, &off) || !off) return -EINVAL;
    gpiod_set_value_cansleep(c->amp, 0);
    return count;
}
static DEVICE_ATTR_WO(speaker_shutdown);
static struct attribute *attributes[] = {
    &dev_attr_pcm_counters.attr, &dev_attr_speaker_shutdown.attr, NULL
};
static const struct attribute_group attribute_group = { .attrs = attributes };
static int codec_probe(struct platform_device *pdev)
{
    struct device *dev = &pdev->dev;
    struct tzx_codec *c;
    void __iomem *base;
    int ret;
    c = devm_kzalloc(dev, sizeof(*c), GFP_KERNEL);
    if (!c) return -ENOMEM;
    platform_set_drvdata(pdev, c);
    c->pio = devm_ioremap(dev, 0x02000000, 0x800);
    if (!c->pio) return -ENOMEM;
    c->saved_amp_mux = readl(c->pio + 0x150) & GENMASK(27, 24);
    c->saved_amp_data = readl(c->pio + 0x160) & BIT(6);
    if (c->saved_amp_mux != 0 && c->saved_amp_mux != (7 << 24) && c->saved_amp_mux != (15 << 24))
        return dev_err_probe(dev, -EBUSY, "PH6 is in use by another function\n");
    ret = devm_add_action_or_reset(dev, restore_amp_pin, c); if (ret) return ret;
    c->amp = devm_gpiod_get(dev, "speaker-enable", GPIOD_OUT_LOW);
    if (IS_ERR(c->amp)) return PTR_ERR(c->amp);
    c->amp_claimed = true;
    base = devm_platform_ioremap_resource(pdev, 0);
    if (IS_ERR(base)) return PTR_ERR(base);
    c->map = devm_regmap_init_mmio(dev, base, &regconfig);
    if (IS_ERR(c->map)) return PTR_ERR(c->map);
    c->bus = devm_clk_get(dev, "bus"); c->dac = devm_clk_get(dev, "dac");
    c->adc = devm_clk_get(dev, "adc"); c->parent = devm_clk_get(dev, "parent");
    c->reset = devm_reset_control_get_exclusive(dev, NULL);
    if (IS_ERR(c->bus) || IS_ERR(c->dac) || IS_ERR(c->adc) || IS_ERR(c->parent) || IS_ERR(c->reset))
        return -EPROBE_DEFER;
    ret = clk_prepare_enable(c->bus); if (ret) return ret;
    ret = devm_add_action_or_reset(dev, disable_bus, c->bus); if (ret) return ret;
    ret = reset_control_deassert(c->reset); if (ret) return ret;
    ret = devm_add_action_or_reset(dev, assert_reset, c->reset); if (ret) return ret;
    ret = clk_set_parent(c->dac, c->parent); if (ret) return ret;
    ret = clk_set_parent(c->adc, c->parent); if (ret) return ret;
    /* The shared PLL has CLK_SET_RATE_GATE: establish both 48 kHz clocks
     * before startup enables it. Later hw_params uses this same fixed rate. */
    ret = clk_set_rate(c->dac, 24576000); if (ret) return ret;
    ret = clk_set_rate(c->adc, 24576000); if (ret) return ret;
    if (clk_get_rate(c->dac) != 24576000 || clk_get_rate(c->adc) != 24576000)
        return dev_err_probe(dev, -ERANGE, "codec clocks must be exactly 24.576 MHz\n");
    ret = regmap_read(c->map, 0x310, &c->saved_analog[0]); if (ret) return ret;
    ret = regmap_read(c->map, 0x31c, &c->saved_analog[1]); if (ret) return ret;
    ret = regmap_read(c->map, 0x348, &c->saved_analog[2]); if (ret) return ret;
    ret = regmap_read(c->map, 0x300, &c->saved_analog[3]); if (ret) return ret;
    ret = regmap_read(c->map, 0x28, &c->saved_analog[4]); if (ret) return ret;
    ret = devm_add_action_or_reset(dev, restore_analog, c); if (ret) return ret;
    /* Only codec-local analog supplies, following the BSP initialization. */
    regmap_update_bits(c->map, 0x31c, BIT(1), BIT(1));
    regmap_update_bits(c->map, 0x310, BIT(7) | GENMASK(25, 24), BIT(7) | GENMASK(25, 24));
    regmap_update_bits(c->map, 0x348, BIT(24), BIT(24));
    regmap_update_bits(c->map, 0x348, BIT(15), BIT(15)); msleep(50);
    regmap_update_bits(c->map, 0x348, BIT(15), 0);
    regmap_write(c->map, 0x04, BIT(16) | 127 << 8 | 127);
    regmap_update_bits(c->map, 0x310, BIT(12) | BIT(10) | GENMASK(4, 0), 0);
    regmap_update_bits(c->map, 0x30, BIT(25) | GENMASK(27, 26), BIT(25) | 2 << 26);
    regmap_update_bits(c->map, 0x50, BIT(16), BIT(16));
    regmap_write(c->map, 0x34, 127);
    regmap_update_bits(c->map, 0x300, GENMASK(12, 8), 0);
    regmap_update_bits(c->map, 0x28, GENMASK(2, 0), 0);
    c->tx = (struct snd_dmaengine_dai_dma_data){ .addr = 0x07110020,
        .addr_width = DMA_SLAVE_BUSWIDTH_2_BYTES, .maxburst = 4, .fifo_size = 128 };
    c->rx = (struct snd_dmaengine_dai_dma_data){ .addr = 0x07110040,
        .addr_width = DMA_SLAVE_BUSWIDTH_2_BYTES, .maxburst = 4, .fifo_size = 128 };
    ret = devm_snd_soc_register_component(dev, &analog, &analog_dai, 1); if (ret) return ret;
    ret = devm_snd_soc_register_component(dev, &digital, &cpu_dai, 1); if (ret) return ret;
    ret = snd_dmaengine_pcm_register(dev, NULL, 0); if (ret) return ret;
    ret = devm_add_action_or_reset(dev, unregister_pcm, dev); if (ret) return ret;
    c->cpus = (struct snd_soc_dai_link_component){ .name = dev_name(dev), .dai_name = "tzx-a523-cpu" };
    c->codecs = (struct snd_soc_dai_link_component){ .name = dev_name(dev), .dai_name = "tzx-a523-codec" };
    c->platforms = (struct snd_soc_dai_link_component){ .name = dev_name(dev) };
    c->link = (struct snd_soc_dai_link){ .name = "A523 Codec", .stream_name = "A523 Codec PCM",
        .cpus = &c->cpus, .num_cpus = 1, .codecs = &c->codecs, .num_codecs = 1,
        .platforms = &c->platforms, .num_platforms = 1 };
    c->card = (struct snd_soc_card){ .name = "TZX A523", .driver_name = "tzx-a523-codec",
        .owner = THIS_MODULE, .dev = dev, .dai_link = &c->link, .num_links = 1 };
    snd_soc_card_set_drvdata(&c->card, c);
    ret = devm_snd_soc_register_card(dev, &c->card); if (ret) return ret;
    ret = devm_device_add_group(dev, &attribute_group); if (ret) return ret;
    dev_info(dev, "48k S16 PCM registered, ADC1 and stereo DAC, DAPM speaker amplifier PH6\n");
    return 0;
}
static const struct of_device_id matches[] = { { .compatible = "tzx,a523-audio-codec" }, {} };
MODULE_DEVICE_TABLE(of, matches);
static void codec_device_shutdown(struct platform_device *pdev)
{
    struct tzx_codec *c = codec_data(&pdev->dev);
    regmap_update_bits(c->map, 0x310, BIT(12) | BIT(10), 0);
    gpiod_set_value_cansleep(c->amp, 0);
}
static struct platform_driver codec_driver = { .probe = codec_probe, .shutdown = codec_device_shutdown,
    .driver = { .name = "tzx-a523-codec", .of_match_table = matches } };
static bool provider_matches(u32 phandle, const char *path)
{
    struct device_node *node = of_find_node_by_phandle(phandle);
    struct device_node *expected = of_find_node_by_path(path);
    bool match = node && node == expected;
    of_node_put(node); of_node_put(expected); return match;
}
static int __init start(void)
{
    int ret;
    if (!of_machine_is_compatible("tzx,p30a523") ||
        !provider_matches(0x16, "/soc/clock-controller@7102000") ||
        !provider_matches(0x15, "/soc/dma-controller@7121000")) return -ENODEV;
    gpiod_add_lookup_table(&amp_lookup);
    ret = platform_driver_register(&codec_driver);
    if (ret) { gpiod_remove_lookup_table(&amp_lookup); return ret; }
    ret = of_overlay_fdt_apply(tzx_codec_overlay, tzx_codec_overlay_end - tzx_codec_overlay,
                               &overlay_id, NULL);
    if (ret) {
        platform_driver_unregister(&codec_driver);
        gpiod_remove_lookup_table(&amp_lookup);
    }
    return ret;
}
static void __exit stop(void)
{
    of_overlay_remove(&overlay_id);
    platform_driver_unregister(&codec_driver);
    gpiod_remove_lookup_table(&amp_lookup);
}
module_init(start);
module_exit(stop);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("TZX P30 A523 integrated codec PCM bring-up");
