"""Freeze a separate reversible four-bit SDIO host candidate."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
out = root / 'build/wifi-bus-trial'
out.mkdir(exist_ok=False)
source = (root / 'firmware/tzx_wifi_runtime.c').read_text()
parent_sha = hashlib.sha256(source.encode()).hexdigest()
needle = 'static struct platform_device *owner, *host, *supply;'
assert source.count(needle) == 1
source = source.replace(needle, '''/* These properties apply only to the isolated Wi-Fi host, before probe.
 * They are reverted after unregistering that host. eMMC is never changed. */
static unsigned int bus_width = 1;
module_param(bus_width, uint, 0444);
static struct of_changeset bus_changes;
static bool changes_initialized, changes_applied;

''' + needle)
needle = '    if (supply) {'
assert source.count(needle) == 1
source = source.replace(needle, '''    if (changes_applied) {
        int ret = of_changeset_revert(&bus_changes);
        if (ret) pr_err("TZX Wi-Fi property rollback failed: %d\\n", ret);
        changes_applied = false;
    }
    if (changes_initialized) {
        of_changeset_destroy(&bus_changes);
        changes_initialized = false;
    }
''' + needle)
needle = '    ret = of_address_to_resource(node, 0, &resources[0]);'
assert source.count(needle) == 1
source = source.replace(needle, '''    if (bus_width != 1 && bus_width != 4) {
        ret = -EINVAL;
        goto put_node;
    }
    /* The tested base node omits bus-width, so the old default is one bit.
     * Reject an unexpected property rather than replacing an unknown value. */
    if (of_find_property(node, "bus-width", NULL)) {
        ret = -EEXIST;
        goto put_node;
    }
''' + needle)
needle = '    gpiod_add_lookup_table(&enable_gpios);'
assert source.count(needle) == 1
source = source.replace(needle, '''    if (bus_width == 4) {
        u32 width = 4;
        of_changeset_init(&bus_changes);
        changes_initialized = true;
        ret = of_changeset_add_prop_u32_array(&bus_changes, node,
                                             "bus-width", &width, 1);
        if (ret) goto fail;
        ret = of_changeset_apply(&bus_changes);
        if (ret) goto fail;
        changes_applied = true;
    }
''' + needle)
source = source.replace('signalling, one-bit, max 12MHz\\n");',
                        'signalling, requested width=%u, max 12MHz\\n", bus_width);')
assert 'requested width=%u' in source
(out / 'tzx_wifi_runtime.c').write_text(source, newline='\n')
(out / 'SOURCE.json').write_text(json.dumps({
    'base_source': 'firmware/tzx_wifi_runtime.c', 'base_sha256': parent_sha,
    'candidate_sha256': hashlib.sha256(source.encode()).hexdigest(),
    'purpose': 'four_bit_wifi_only_before_probe_12MHz_unchanged_power_and_eMMC',
    'applied_or_tested': False}, indent=2) + '\n', newline='\n')
print('WIFI_FOUR_BIT_SOURCE_PREPARED')
