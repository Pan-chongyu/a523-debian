// SPDX-License-Identifier: GPL-2.0-only
/* Standard thermal step-wise cooling for the already qualified divider OPPs.
 * No PMIC, PLL or DSU access. Both clusters are capped through frequency QoS.
 */
#include <linux/cpufreq.h>
#include <linux/device.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/pm_qos.h>
#include <linux/thermal.h>

struct tzx_cluster {
	struct cpufreq_policy *policy;
	struct freq_qos_request maximum;
	struct thermal_cooling_device *cdev;
	unsigned long state;
};

static struct tzx_cluster clusters[2];
static struct thermal_zone_device *sensors[5], *zone;
static const char * const sensor_names[] = {
	"cpu-big-thermal", "cpu-little-thermal", "gpu-thermal",
	"npu-thermal", "ddr-thermal",
};
static const unsigned int caps[] = {480000, 240000, 120000};
static int first_trip = 70000, second_trip = 80000;
/* Immutable after load. Lower values allow a real-temperature functional
 * test without heating hardware or inventing temperature readings. Runtime
 * installation always uses the defaults, verified by its pinned wrapper. */
module_param(first_trip, int, 0444);
module_param(second_trip, int, 0444);

static int max_state(struct thermal_cooling_device *cdev, unsigned long *state)
{
	*state = ARRAY_SIZE(caps)-1;
	return 0;
}

static int get_state(struct thermal_cooling_device *cdev, unsigned long *state)
{
	struct tzx_cluster *cluster = cdev->devdata;

	*state = READ_ONCE(cluster->state);
	return 0;
}

static int set_state(struct thermal_cooling_device *cdev, unsigned long state)
{
	struct tzx_cluster *cluster = cdev->devdata;
	int ret;

	if (state >= ARRAY_SIZE(caps))
		return -EINVAL;
	ret = freq_qos_update_request(&cluster->maximum, caps[state]);
	if (ret < 0)
		return ret;
	WRITE_ONCE(cluster->state, state);
	return 0;
}

static const struct thermal_cooling_device_ops cooling_ops = {
	.get_max_state = max_state,
	.get_cur_state = get_state,
	.set_cur_state = set_state,
};

static int get_temp(struct thermal_zone_device *tz, int *temperature)
{
	int i, ret, value, maximum = THERMAL_TEMP_INVALID;

	for (i = 0; i < ARRAY_SIZE(sensors); i++) {
		ret = thermal_zone_get_temp(sensors[i], &value);
		if (ret)
			return ret;
		if (value <= 0 || value > 125000)
			return -ENODATA;
		maximum = max(maximum, value);
	}
	*temperature = maximum;
	return 0;
}

static bool should_bind(struct thermal_zone_device *tz,
			const struct thermal_trip *trip,
			struct thermal_cooling_device *cdev,
			struct cooling_spec *spec)
{
	unsigned long state = THERMAL_TRIP_PRIV_TO_INT(trip->priv);

	if (trip->type != THERMAL_TRIP_PASSIVE || state < 1 || state > 2)
		return false;
	if (cdev != clusters[0].cdev && cdev != clusters[1].cdev)
		return false;
	spec->lower = state;
	spec->upper = state;
	spec->weight = THERMAL_WEIGHT_DEFAULT;
	return true;
}

static const struct thermal_zone_device_ops zone_ops = {
	.get_temp = get_temp,
	.should_bind = should_bind,
};

static const struct thermal_zone_params zone_params = {
	.governor_name = "step_wise",
	.no_hwmon = true,
};

static void cleanup(void)
{
	int i;

	if (zone) {
		thermal_zone_device_unregister(zone);
		zone = NULL;
	}
	for (i = ARRAY_SIZE(clusters)-1; i >= 0; i--) {
		if (clusters[i].cdev)
			thermal_cooling_device_unregister(clusters[i].cdev);
		if (freq_qos_request_active(&clusters[i].maximum))
			freq_qos_remove_request(&clusters[i].maximum);
		if (clusters[i].policy)
			cpufreq_cpu_put(clusters[i].policy);
	}
	for (i = 0; i < ARRAY_SIZE(sensors); i++)
		if (sensors[i])
			put_device(thermal_zone_device(sensors[i]));
}

static int __init start(void)
{
	struct thermal_trip trips[] = {
		{ .temperature = first_trip, .hysteresis = 5000,
		  .type = THERMAL_TRIP_PASSIVE, .priv = THERMAL_INT_TO_TRIP_PRIV(1) },
		{ .temperature = second_trip, .hysteresis = 5000,
		  .type = THERMAL_TRIP_PASSIVE, .priv = THERMAL_INT_TO_TRIP_PRIV(2) },
		{ .temperature = 95000, .hysteresis = 2000, .type = THERMAL_TRIP_CRITICAL },
	};
	int i, ret, temp;

	if (!of_machine_is_compatible("tzx,p30a523"))
		return -ENODEV;
	if (first_trip < 30000 || first_trip > 70000 ||
	    second_trip <= first_trip || second_trip > 80000)
		return -EINVAL;
	for (i = 0; i < ARRAY_SIZE(sensors); i++) {
		struct thermal_zone_device *sensor = thermal_zone_get_zone_by_name(sensor_names[i]);

		if (IS_ERR(sensor)) {
			ret = PTR_ERR(sensor);
			goto fail;
		}
		get_device(thermal_zone_device(sensor));
		sensors[i] = sensor;
		ret = thermal_zone_get_temp(sensor, &temp);
		/* Cooling must also attach to a hot board. The trip policy, rather
		 * than a qualification-only 75C guard, handles valid hot readings. */
		if (ret || temp <= 0 || temp > 125000) {
			ret = ret ? ret : -ERANGE;
			goto fail;
		}
	}
	for (i = 0; i < ARRAY_SIZE(clusters); i++) {
		struct cpufreq_policy *policy = cpufreq_cpu_get(i*4);

		clusters[i].policy = policy;
		if (!policy || !policy->freq_table || cpumask_weight(policy->related_cpus) != 4 ||
		    policy->cpuinfo.max_freq != 480000 || policy->cpuinfo.min_freq != 120000) {
			ret = -ENODEV;
			goto fail;
		}
		ret = freq_qos_add_request(&policy->constraints, &clusters[i].maximum,
					  FREQ_QOS_MAX, caps[0]);
		if (ret < 0)
			goto fail;
		clusters[i].cdev = thermal_cooling_device_register(
			i ? "tzx-cpu-cluster1" : "tzx-cpu-cluster0", &clusters[i], &cooling_ops);
		if (IS_ERR(clusters[i].cdev)) {
			ret = PTR_ERR(clusters[i].cdev);
			clusters[i].cdev = NULL;
			goto fail;
		}
	}
	zone = thermal_zone_device_register_with_trips("tzx-board-thermal", trips,
		ARRAY_SIZE(trips), NULL, &zone_ops, &zone_params, 1000, 1000);
	if (IS_ERR(zone)) {
		ret = PTR_ERR(zone);
		zone = NULL;
		goto fail;
	}
	ret = thermal_zone_device_enable(zone);
	if (ret)
		goto fail;
	pr_info("tzx-cooling: max of five real sensors, trips %d/%d/95000, caps 480/240/120 MHz\n",
		first_trip, second_trip);
	return 0;
fail:
	cleanup();
	return ret;
}

static void __exit stop(void)
{
	cleanup();
	pr_info("tzx-cooling: cooling zone removed, both frequency QoS caps released\n");
}
module_init(start);
module_exit(stop);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("TZX P30 board-max thermal zone and two CPU frequency-QoS cooling devices");
