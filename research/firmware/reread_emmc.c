/* SPDX-License-Identifier: MIT */
#include <fcntl.h>
#include <linux/fs.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>
int main(void) {
    char cid[64];
    FILE *f=fopen("/sys/class/block/mmcblk0/device/cid","r");
    if(!f||!fgets(cid,sizeof(cid),f))return 10;
    fclose(f);
    if(strcmp(cid,"3e01ff55454d20202010209170281b59\n"))return 11;
    int fd=open("/dev/mmcblk0",O_RDWR);
    if(fd<0)return 12;
    sync();
    int rc=ioctl(fd,BLKRRPART,0);
    if(rc)perror("BLKRRPART");
    close(fd);
    return rc?13:0;
}
