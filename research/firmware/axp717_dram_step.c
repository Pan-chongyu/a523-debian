/* SPDX-License-Identifier: MIT
 * Manual bounded DCDC3 diagnostic. No /dev/mem mappings; preserve DVM bit.
 * Board wiring is inferred, not measured. Invoke writes only under a unit
 * with ExecStopPost, independent timer, and a boot-time restore helper.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/i2c.h>
#include <linux/i2c-dev.h>
#include <signal.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/utsname.h>
#include <time.h>
#include <unistd.h>

#define DIR "/var/lib/tzx/diagnostics/dram-c-step"
#define STATE DIR "/original.txt"
static int bus = -1, trace_fd = -1;
static volatile sig_atomic_t stopping;

static void trace(const char *stage, unsigned value)
{
    struct timespec now;
    clock_gettime(CLOCK_REALTIME, &now);
    char line[180];
    int count = snprintf(line, sizeof(line), "%lld.%09ld %s 0x%02x\n",
                         (long long)now.tv_sec, now.tv_nsec, stage, value);
    if (count <= 0 || count >= (int)sizeof(line) || write(trace_fd, line, count) != count)
        _exit(91);
    fputs(line, stdout);
    fflush(stdout);
}

static void die(const char *message)
{
    fprintf(stderr, "DRAM_C_REJECTED: %s (errno=%d)\n", message, errno);
    exit(2);
}

static void transfer(struct i2c_msg *messages, unsigned count)
{
    struct i2c_rdwr_ioctl_data request = {messages, count};
    if (ioctl(bus, I2C_RDWR, &request) != (int)count)
        die("I2C_RDWR");
}

static unsigned read_reg(unsigned address, unsigned reg)
{
    unsigned char tx = reg, rx = 0;
    struct i2c_msg messages[2] = {{address, 0, 1, &tx},
                                 {address, I2C_M_RD, 1, &rx}};
    transfer(messages, 2);
    return rx;
}

static void check_identity(void)
{
    struct utsname id;
    char cid[80] = {0};
    FILE *file = fopen("/sys/class/block/mmcblk0/device/cid", "r");
    if (!file || !fgets(cid, sizeof(cid), file)) die("CID read");
    fclose(file);
    if (geteuid() || uname(&id) || strcmp(id.release, "7.3.3-tzx-a523-accel1") ||
        !strstr(id.version, "#5 ") || strcmp(cid, "3e01ff55454d20202010209170281b59\n"))
        die("board/kernel identity");
    if (!access("/sys/bus/i2c/devices/0-0034", F_OK) ||
        !access("/sys/bus/i2c/devices/0-0036", F_OK)) die("PMIC driver bound");
    if (read_reg(0x36, 3) != 0x49 || read_reg(0x34, 0x80) != 0x0f ||
        read_reg(0x34, 0x83) != 0xa8 || read_reg(0x34, 0x84) != 0xa8 ||
        read_reg(0x34, 0x86) != 0 || read_reg(0x34, 0x98) != 0x0d)
        die("PMIC register identity");
}

static void ramp(unsigned destination)
{
    unsigned current = read_reg(0x34, 0x85);
    trace("CURRENT_READBACK", current);
    if (current < 0xbc || current > 0xc9) die("unexpected DCDC3");
    int direction = destination > current ? 1 : -1;
    while (current != destination) {
        if (stopping && destination != 0xbc) die("interrupted; unit restores");
        unsigned next = current + direction;
        if (next < 0xbc || next > 0xc9 || !(next & 0x80)) die("range or DVM");
        trace("ABOUT_TO_WRITE", next); /* O_DSYNC completes before ioctl. */
        unsigned char bytes[2] = {0x85, next};
        struct i2c_msg message = {0x34, 0, 2, bytes};
        transfer(&message, 1);
        struct timespec delay = {0, 10000000};
        nanosleep(&delay, NULL);
        current = read_reg(0x34, 0x85);
        trace("STEP_READBACK", current);
        if (current != next) die("step readback");
    }
    trace("FINAL_READBACK", current);
}

static void stop(int signum) { (void)signum; stopping = 1; }

int main(int argc, char **argv)
{
    if (argc != 2 || (strcmp(argv[1], "probe") && strcmp(argv[1], "1200") &&
                     strcmp(argv[1], "1260") && strcmp(argv[1], "restore"))) return 2;
    if (geteuid()) return 2;
    struct stat status;
    if (lstat(DIR, &status) || !S_ISDIR(status.st_mode) || status.st_uid != 0) return 2;
    trace_fd = open(DIR "/trace.txt", O_WRONLY | O_CREAT | O_APPEND | O_DSYNC | O_NOFOLLOW, 0600);
    bus = open("/dev/i2c-0", O_RDWR | O_CLOEXEC);
    if (trace_fd < 0 || bus < 0) die("open");
    signal(SIGTERM, stop);
    signal(SIGINT, stop);
    check_identity();
    trace("PREFLIGHT_READBACK", read_reg(0x34, 0x85));
    if (!strcmp(argv[1], "probe")) return 0;
    if (!strcmp(argv[1], "restore")) {
        FILE *saved = fopen(STATE, "r");
        if (!saved) { trace("NO_STATE_NO_WRITE", 0); return 0; }
        unsigned original, target;
        int parsed = fscanf(saved, "TZXDRAMV1 %u %u", &original, &target);
        fclose(saved);
        if (parsed != 2 || original != 0xbc || (target != 0xc6 && target != 0xc9)) die("saved state");
        ramp(original);
        return 0;
    }
    if (!access("/sys/module/panfrost", F_OK) ||
        !access("/sys/module/tzx_cpufreq_divider", F_OK) ||
        !access("/var/lib/tzx/gpu-qualified", F_OK) || read_reg(0x34, 0x85) != 0xbc)
        die("test baseline");
    unsigned target = !strcmp(argv[1], "1200") ? 0xc6 : 0xc9;
    char saved[80];
    int length = snprintf(saved, sizeof(saved), "TZXDRAMV1 %u %u\n", 0xbc, target);
    int state = open(STATE ".new", O_WRONLY | O_CREAT | O_TRUNC | O_NOFOLLOW, 0600);
    if (state < 0 || write(state, saved, length) != length || fsync(state) || close(state) ||
        rename(STATE ".new", STATE)) die("durable state");
    int directory = open(DIR, O_DIRECTORY | O_RDONLY);
    if (directory < 0 || fsync(directory) || close(directory)) die("state directory sync");
    trace("STATE_SAVED_TARGET", target);
    ramp(target);
    puts("DRAM_C_SETPOINT_APPLIED_BEFORE_WORKLOAD");
    fflush(stdout);
    return 0;
}
