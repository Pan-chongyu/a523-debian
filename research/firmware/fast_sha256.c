/* SPDX-License-Identifier: MIT
 * SHA256 over a bounded file region, using the Cortex-A55 SHA2 instructions.
 */
#define _FILE_OFFSET_BITS 64
#include <arm_neon.h>
#include <asm/hwcap.h>
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/auxv.h>
#include <sys/stat.h>
#include <unistd.h>
static const uint32_t constants[64]={
0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
static uint32_t state[8]={0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
static void blocks(const unsigned char *p,size_t count){
    uint32x4_t a=vld1q_u32(state),b=vld1q_u32(state+4);
    while(count--){
        uint32x4_t saved_a=a,saved_b=b,m[4];
        for(int j=0;j<4;j++)m[j]=vreinterpretq_u32_u8(vrev32q_u8(vld1q_u8(p+16*j)));
        for(int i=0;i<16;i++){
            uint32x4_t t=vaddq_u32(m[i%4],vld1q_u32(constants+4*i)),old_a=a;
            a=vsha256hq_u32(a,b,t);b=vsha256h2q_u32(b,old_a,t);
            if(i<12)m[i%4]=vsha256su1q_u32(vsha256su0q_u32(m[i%4],m[(i+1)%4]),m[(i+2)%4],m[(i+3)%4]);
        }
        a=vaddq_u32(a,saved_a);b=vaddq_u32(b,saved_b);p+=64;
    }
    vst1q_u32(state,a);vst1q_u32(state+4,b);
}
int main(int argc,char **argv){
    if(argc!=2&&argc!=4)return 10;
    if(!(getauxval(AT_HWCAP)&HWCAP_SHA2)){fprintf(stderr,"No SHA2 CPU support\n");return 11;}
    int fd=open(argv[1],O_RDONLY);if(fd<0){perror("open");return 12;}
    struct stat st;if(fstat(fd,&st))return 13;
    uint64_t offset=argc==4?strtoull(argv[2],0,0):0;
    uint64_t length=argc==4?strtoull(argv[3],0,0):(uint64_t)st.st_size;
    if(lseek(fd,offset,SEEK_SET)<0)return 14;
    uint64_t remaining=length;unsigned char buf[65536+128];size_t used=0;
    while(remaining){
        size_t want=remaining<65536?remaining:65536;
        ssize_t n=read(fd,buf+used,want);
        if(n<0&&errno==EINTR)continue;
        if(n<=0){fprintf(stderr,"Short read\n");return 15;}
        remaining-=n;used+=n;size_t whole=used/64;
        blocks(buf,whole);used-=whole*64;
        for(size_t i=0;i<used;i++)buf[i]=buf[whole*64+i];
    }
    close(fd);buf[used++]=0x80;
    size_t end=used<=56?64:128;
    while(used<end)buf[used++]=0;
    uint64_t bits=length*8;
    for(int i=0;i<8;i++)buf[end-1-i]=(unsigned char)(bits>>(i*8));
    blocks(buf,end/64);
    for(int i=0;i<8;i++)printf("%08x",state[i]);
    printf("  %s\n",argv[1]);return 0;
}
