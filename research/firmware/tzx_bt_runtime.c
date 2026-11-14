// SPDX-License-Identifier: GPL-2.0-only
/* Reversible BT UART/power setup, verified by HCI initialization and RF scans.
 * Reset must be released before the shared AIC BSP firmware is uploaded.
 */
#include <linux/delay.h>
#include <linux/dma-mapping.h>
#include <linux/gpio/consumer.h>
#include <linux/gpio/machine.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/of_address.h>
#include <linux/of_irq.h>
#include <linux/of_platform.h>
#include <linux/platform_device.h>

static struct platform_device *owner, *uart;
static struct gpio_desc *pins[4], *reset, *wake, *hostwake;
static void __iomem *pio, *rpio;
static u32 saved_pg[2], saved_pm_cfg, saved_pm_data;
static bool saved, lookup;
static int prepare_firmware(const char *value, const struct kernel_param *parameter)
{
    bool pulse;
    int ret = kstrtobool(value, &pulse);
    if (ret || !pulse) return -EINVAL;
    if (!reset || !wake) return -ENODEV;
    gpiod_set_value_cansleep(wake, 1);
    gpiod_set_value_cansleep(reset, 0); msleep(30);
    gpiod_set_value_cansleep(reset, 1); msleep(300);
    pr_info("tzx-bt: powered reset completed before shared firmware\n");
    return 0;
}
static const struct kernel_param_ops prepare_ops = { .set = prepare_firmware };
module_param_cb(prepare_firmware, &prepare_ops, NULL, 0200);
static struct gpiod_lookup_table gpios = {
    .dev_id = "tzx-bt-runtime",
    .table = {
        GPIO_LOOKUP_IDX("2000000.pinctrl", 198, "uart", 0, GPIO_ACTIVE_HIGH),
        GPIO_LOOKUP_IDX("2000000.pinctrl", 199, "uart", 1, GPIO_ACTIVE_HIGH),
        GPIO_LOOKUP_IDX("2000000.pinctrl", 200, "uart", 2, GPIO_ACTIVE_HIGH),
        GPIO_LOOKUP_IDX("2000000.pinctrl", 201, "uart", 3, GPIO_ACTIVE_HIGH),
        GPIO_LOOKUP("7022000.pinctrl", 34, "reset", GPIO_ACTIVE_HIGH),
        GPIO_LOOKUP("7022000.pinctrl", 35, "wake", GPIO_ACTIVE_HIGH),
        GPIO_LOOKUP("7022000.pinctrl", 36, "hostwake", GPIO_ACTIVE_HIGH), {}
    }
};

static void masked_restore(void __iomem *reg, u32 mask, u32 value)
{
    writel((readl(reg) & ~mask) | (value & mask), reg);
}
static void cleanup(void)
{
    if (uart) { platform_device_unregister(uart); uart = NULL; }
    if (reset) gpiod_set_value_cansleep(reset, 0);
    if (wake) gpiod_set_value_cansleep(wake, 0);
    if (saved) {
        masked_restore(pio + 0x120, 0xff000000, saved_pg[0]);
        masked_restore(pio + 0x124, 0x000000ff, saved_pg[1]);
        masked_restore(rpio + 0x40, BIT(2) | BIT(3), saved_pm_data);
        masked_restore(rpio + 0x30, 0x000fff00, saved_pm_cfg);
    }
    if (hostwake) { gpiod_put(hostwake); hostwake = NULL; }
    if (wake) { gpiod_put(wake); wake = NULL; }
    if (reset) { gpiod_put(reset); reset = NULL; }
    for (int i = 3; i >= 0; i--) if (pins[i]) { gpiod_put(pins[i]); pins[i] = NULL; }
    if (owner) { platform_device_unregister(owner); owner = NULL; }
    if (lookup) gpiod_remove_lookup_table(&gpios);
    if (pio) iounmap(pio);
    if (rpio) iounmap(rpio);
}
static int __init start(void)
{
    struct device_node *node;
    struct platform_device *existing;
    struct resource resources[2] = {};
    int ret;
    if (!of_machine_is_compatible("tzx,p30a523")) return -ENODEV;
    node = of_find_node_by_path("/soc/serial@2500400");
    if (!node) return -ENODEV;
    existing = of_find_device_by_node(node);
    if (existing) { put_device(&existing->dev); ret = -EBUSY; goto put_node; }
    ret = of_address_to_resource(node, 0, &resources[0]);
    if (ret || resources[0].start != 0x02500400) { ret = -EINVAL; goto fail; }
    ret = of_irq_get(node, 0);
    if (ret <= 0) { ret = -ENXIO; goto fail; }
    resources[1] = (struct resource){ .start = ret, .end = ret, .flags = IORESOURCE_IRQ };
    pio = ioremap(0x02000000, 0x800); rpio = ioremap(0x07022000, 0x400);
    if (!pio || !rpio) { ret = -ENOMEM; goto fail; }
    saved_pg[0] = readl(pio + 0x120); saved_pg[1] = readl(pio + 0x124);
    saved_pm_cfg = readl(rpio + 0x30); saved_pm_data = readl(rpio + 0x40); saved = true;
    gpiod_add_lookup_table(&gpios); lookup = true;
    owner = platform_device_register_simple("tzx-bt-runtime", -1, NULL, 0);
    if (IS_ERR(owner)) { ret = PTR_ERR(owner); owner = NULL; goto fail; }
    for (int i = 0; i < 4; i++) {
        pins[i] = gpiod_get_index(&owner->dev, "uart", i, GPIOD_ASIS);
        if (IS_ERR(pins[i])) { ret = PTR_ERR(pins[i]); pins[i] = NULL; goto fail; }
    }
    reset = gpiod_get(&owner->dev, "reset", GPIOD_ASIS);
    if (IS_ERR(reset)) { ret = PTR_ERR(reset); reset = NULL; goto fail; }
    wake = gpiod_get(&owner->dev, "wake", GPIOD_ASIS);
    if (IS_ERR(wake)) { ret = PTR_ERR(wake); wake = NULL; goto fail; }
    hostwake = gpiod_get(&owner->dev, "hostwake", GPIOD_IN);
    if (IS_ERR(hostwake)) { ret = PTR_ERR(hostwake); hostwake = NULL; goto fail; }
    ret = gpiod_direction_output(reset, 0); if (ret) goto fail;
    ret = gpiod_direction_output(wake, 1); if (ret) goto fail;
    msleep(30);
    for (int pin = 6; pin <= 9; pin++) {
        unsigned off = 0x120 + pin / 8 * 4, shift = pin % 8 * 4;
        writel((readl(pio + off) & ~(15U << shift)) | (2U << shift), pio + off);
    }
    gpiod_set_value_cansleep(reset, 1); msleep(300);
    uart = platform_device_alloc("tzx-bt-uart", -1);
    if (!uart) { ret = -ENOMEM; goto fail; }
    ret = platform_device_add_resources(uart, resources, ARRAY_SIZE(resources));
    if (ret) goto put_uart;
    platform_device_set_of_node(uart, node);
    uart->dev.coherent_dma_mask = DMA_BIT_MASK(32);
    uart->dev.dma_mask = &uart->dev.coherent_dma_mask;
    ret = platform_device_add(uart); if (ret) goto put_uart;
    if (!device_is_bound(&uart->dev)) { ret = -ENODEV; goto fail; }
    pr_info("tzx-bt: PG6..9 UART1, PM2 reset high PM3 wake high PM4=%d\n", gpiod_get_value_cansleep(hostwake));
    of_node_put(node); return 0;
put_uart:
    platform_device_put(uart); uart = NULL;
fail:
    cleanup();
put_node:
    of_node_put(node); return ret;
}
module_init(start);
module_exit(cleanup);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("TZX P30 AIC8800D80 Bluetooth UART and reset setup");
