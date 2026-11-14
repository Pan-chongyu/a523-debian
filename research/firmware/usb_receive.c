/* SPDX-License-Identifier: MIT
 * Receive a bounded RAM file over the USB console, with per-record CRC/ACK.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <termios.h>
#include <unistd.h>

static int full_read(int fd, void *p, size_t n) {
    while (n) { ssize_t r=read(fd,p,n); if(r<0&&errno==EINTR)continue;
        if(r<=0)return -1; p=(char*)p+r;n-=r; } return 0;
}
static int full_write(int fd, const void *p, size_t n) {
    while(n) {ssize_t r=write(fd,p,n);if(r<0&&errno==EINTR)continue;
        if(r<=0)return -1;p=(const char*)p+r;n-=r;}return 0;
}
static uint32_t crc32(const unsigned char *p, size_t n) {
    uint32_t c=~0U;while(n--){c^=*p++;for(int i=0;i<8;i++)c=(c>>1)^(0xedb88320U&-(c&1));}return ~c;
}
int main(int argc,char **argv) {
    if(argc!=3||strncmp(argv[1],"/tmp/",5)||strstr(argv[1],".."))return 10;
    uint64_t total=strtoull(argv[2],0,10);
    if(!total||total>512*1024*1024ULL)return 11;
    struct termios old,raw;
    if(tcgetattr(0,&old))return 12;
    raw=old;cfmakeraw(&raw);raw.c_cflag|=CLOCAL;raw.c_cflag&=~HUPCL;
    if(tcsetattr(0,TCSANOW,&raw))return 13;
    int out=open(argv[1],O_CREAT|O_TRUNC|O_WRONLY,0600);
    if(out<0)return 14;
    full_write(1,"TZX_RECORD_READY\n",17);
    uint32_t pos=0,header[4],reply[2];unsigned char buf[2048];int status=0;
    while(pos<total) {
        if(full_read(0,header,sizeof(header))){status=15;break;}
        if(header[0]!=0x43585a54||header[2]==0||header[2]>sizeof(buf)||
            (uint64_t)header[1]+header[2]>total){status=16;break;}
        if(full_read(0,buf,header[2])){status=17;break;}
        reply[0]=0x214b4341;reply[1]=pos;
        if(header[1]==pos&&crc32(buf,header[2])==header[3]){
            if(full_write(out,buf,header[2])){status=18;break;}
            pos+=header[2];reply[1]=pos;
        }
        if(full_write(1,reply,sizeof(reply))){status=19;break;}
    }
    if(fsync(out))status=20;
    close(out);tcsetattr(0,TCSANOW,&old);
    printf("\nTZX_RECORD_RESULT:%d:%u\n",status,pos);fflush(stdout);
    return status;
}
