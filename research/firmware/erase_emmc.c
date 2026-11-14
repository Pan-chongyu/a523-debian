/* SPDX-License-Identifier: MIT
 * Destructive user-area erase explicitly requested by the device owner.
 * Refuse every target except this board's unmounted eMMC user area.
 */
#define _GNU_SOURCE
#include <fcntl.h>
#include <linux/fs.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <unistd.h>

int main(int argc, char **argv) {
    if (argc != 2 || strcmp(argv[1], "ERASE-TZX-3e01ff55454d20202010209170281b59")) return 10;
    char cid[64] = {0}, line[1024];
    FILE *f = fopen("/sys/class/block/mmcblk0/device/cid", "r");
    if (!f || !fgets(cid, sizeof(cid), f)) return 11;
    fclose(f);
    if (strcmp(cid, "3e01ff55454d20202010209170281b59\n")) return 12;
    f = fopen("/proc/mounts", "r");
    if (!f) return 13;
    while (fgets(line, sizeof(line), f)) if (strstr(line, "/dev/mmcblk")) return 14;
    fclose(f);
    int fd = open("/dev/mmcblk0", O_RDWR | O_CLOEXEC);
    if (fd < 0) { perror("open"); return 15; }
    struct stat st;
    uint64_t bytes;
    if (fstat(fd, &st) || !S_ISBLK(st.st_mode) || ioctl(fd, BLKGETSIZE64, &bytes) || bytes != 125090922496ULL) return 16;
    uint64_t range[2] = {0, bytes};
    printf("Erasing user area: %s%llu bytes\n", cid, (unsigned long long)bytes);
    fflush(stdout);
    fsync(fd);
    if (ioctl(fd, BLKDISCARD, range)) { perror("BLKDISCARD"); return 17; }
    fsync(fd);
    printf("USER_AREA_DISCARD_COMPLETE\n");
    close(fd);
    return 0;
}
