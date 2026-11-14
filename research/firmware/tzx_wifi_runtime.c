// SPDX-License-Identifier: GPL-2.0-only
/* Reversible SDIO bring-up on the base DT, without reboot or boot-area writes.
 * PL7/PM5/PM1 remain candidates until the exact AIC8800 function responds.
 * Rail enable/voltage checks are done by the accompanying guarded script.
 */
#include <linux/delay.h>
#include <linux/dma-mapping.h>
#include <linux/gpio/consumer.h>
#include <linux/gpio/machine.h>
#include <linux/module.h>
#include <linux/mmc/host.h>
#include "core.h" /* matching kernel's MMC host claim/release helpers */
#include <linux/of_address.h>
#include <linux/of_irq.h>
#include <linux/of_platform.h>
#include <linux/platform_device.h>
#include <linux/regulator/fixed.h>
#include <linux/regulator/machine.h>

static struct platform_device *owner, *host, *supply;
static struct gpio_desc *enables[3];
static struct gpiod_lookup_table enable_gpios = {
    .dev_id = "tzx-wifi-enables",
    .table = {
        GPIO_LOOKUP("7022000.pinctrl", 7, "power", GPIO_ACTIVE_HIGH),
        GPIO_LOOKUP("7022000.pinctrl", 37, "chip", GPIO_ACTIVE_HIGH),
        GPIO_LOOKUP("7022000.pinctrl", 33, "regon", GPIO_ACTIVE_HIGH), {}
    }
};
static struct regulator_consumer_supply consumers[] = {
    REGULATOR_SUPPLY("vmmc", "tzx-mmc1-runtime"),
    REGULATOR_SUPPLY("vqmmc", "tzx-mmc1-runtime"),
    REGULATOR_SUPPLY("vcc-pg", "2000000.pinctrl")
};
static struct regulator_init_data supply_init = {
    .constraints = {
        .name = "tzx-wifi-prepowered-3v3", .min_uV = 3300000,
        .max_uV = 3300000, .always_on = 1
    },
    .num_consumer_supplies = ARRAY_SIZE(consumers),
    .consumer_supplies = consumers
};
static struct fixed_voltage_config supply_config = {
    .supply_name = "tzx-wifi-prepowered-3v3", .microvolts = 3300000,
    .enabled_at_boot = 1, .init_data = &supply_init
};

static void release_devices(void)
{
    if (host) {
        platform_device_unregister(host);
        host = NULL;
    }
    if (supply) {
        platform_device_unregister(supply);
        supply = NULL;
    }
    for (int i = ARRAY_SIZE(enables) - 1; i >= 0; i--) {
        if (enables[i]) {
            gpiod_set_value_cansleep(enables[i], 0);
            gpiod_put(enables[i]);
            enables[i] = NULL;
        }
    }
    if (owner) {
        platform_device_unregister(owner);
        owner = NULL;
    }
    gpiod_remove_lookup_table(&enable_gpios);
}

static int __init tzx_wifi_init(void)
{
    struct device_node *node;
    struct platform_device *existing;
    struct mmc_host *mmc;
    struct resource resources[2] = {};
    const char *names[] = {"power", "chip", "regon"};
    int ret;
    if (!of_machine_is_compatible("tzx,p30a523"))
        return -ENODEV;
    node = of_find_node_by_path("/soc/mmc@4021000");
    if (!node)
        return -ENODEV;
    existing = of_find_device_by_node(node);
    if (existing) {
        put_device(&existing->dev);
        ret = -EBUSY;
        goto put_node;
    }
    ret = of_address_to_resource(node, 0, &resources[0]);
    if (ret || resources[0].start != 0x04021000 ||
        resource_size(&resources[0]) != 0x1000) {
        ret = -EINVAL;
        goto put_node;
    }
    ret = of_irq_get(node, 0);
    if (ret <= 0) {
        if (!ret) ret = -ENXIO;
        goto put_node;
    }
    resources[1].start = resources[1].end = ret;
    resources[1].flags = IORESOURCE_IRQ;
    resources[1].name = "mmc1";
    gpiod_add_lookup_table(&enable_gpios);
    owner = platform_device_register_simple("tzx-wifi-enables", -1, NULL, 0);
    if (IS_ERR(owner)) { ret = PTR_ERR(owner); owner = NULL; goto fail; }
    for (unsigned int i = 0; i < ARRAY_SIZE(enables); i++) {
        enables[i] = gpiod_get(&owner->dev, names[i], GPIOD_OUT_LOW);
        if (IS_ERR(enables[i])) {
            ret = PTR_ERR(enables[i]); enables[i] = NULL; goto fail;
        }
    }
    msleep(50);
    for (unsigned int i = 0; i < ARRAY_SIZE(enables); i++) {
        gpiod_set_value_cansleep(enables[i], 1);
        msleep(20);
    }
    msleep(250);
    supply = platform_device_register_data(NULL, "reg-fixed-voltage", -1,
                                          &supply_config, sizeof(supply_config));
    if (IS_ERR(supply)) { ret = PTR_ERR(supply); supply = NULL; goto fail; }
    host = platform_device_alloc("tzx-mmc1-runtime", -1);
    if (!host) { ret = -ENOMEM; goto fail; }
    ret = platform_device_add_resources(host, resources, ARRAY_SIZE(resources));
    if (ret) goto put_host;
    /* Keep OF identity for clocks, reset, pinctrl, DMA and driver matching.
     * The unmodified base node selects a conservative one-bit data bus.
     */
    platform_device_set_of_node(host, node);
    host->dev.coherent_dma_mask = DMA_BIT_MASK(32);
    host->dev.dma_mask = &host->dev.coherent_dma_mask;
    ret = platform_device_add(host);
    if (ret) goto put_host;
    /* sunxi-mmc prefers asynchronous probing. Wait for the completed bind,
     * rather than inspecting drvdata while its probe is still running. */
    for (unsigned int i = 0; i < 200 && !device_is_bound(&host->dev); i++)
        msleep(10);
    mmc = platform_get_drvdata(host);
    if (!device_is_bound(&host->dev) || !mmc) { ret = -ENODEV; goto fail; }
    /* Generic property reads prefer the OF node on this kernel, so a
     * software primary cannot override its 150MHz cap. Limit this isolated
     * host while holding its core lock, before any WLAN driver is loaded.
     */
    mmc_claim_host(mmc);
    mmc->f_max = 12000000;
    if (mmc->ios.clock > mmc->f_max) {
        mmc->ios.clock = mmc->f_max;
        mmc->ops->set_ios(mmc, &mmc->ios);
    }
    mmc_release_host(mmc);
    pr_info("TZX runtime SDIO: PL7/PM5/PM1 high, PG0-5, 3.3V signalling, one-bit, max 12MHz\n");
    of_node_put(node);
    return 0;
put_host:
    platform_device_put(host);
    host = NULL;
fail:
    release_devices();
put_node:
    of_node_put(node);
    return ret;
}
module_init(tzx_wifi_init);
module_exit(release_devices);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Reversible TZX P30 SDIO power and host test");
