/* SPDX-License-Identifier: MIT
 * Run the real ARM64 decoder and CRC under QEMU against the exact image, plus
 * malformed bounds, short-distance overlap, extended lengths and canaries.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "compact_lz4.h"
static void check(int yes) { if (!yes) { fputs("FAIL\n", stderr); exit(1); } }
static uint8_t *readfile(const char *name, size_t *n)
{
    FILE *f=fopen(name,"rb"); check(f!=NULL); check(!fseek(f,0,SEEK_END));
    long size=ftell(f); check(size>0); *n=(size_t)size; rewind(f);
    uint8_t *p=malloc(*n); check(p!=NULL); check(fread(p,1,*n,f)==*n); fclose(f); return p;
}
static void reject(const uint8_t *src, size_t n, size_t output)
{
    uint8_t *p=malloc(output+32); check(p!=NULL); memset(p,0xa5,output+32);
    check(compact_lz4(src,n,p+16,output)!=0);
    for(unsigned i=0;i<16;i++) check(p[i]==0xa5 && p[output+16+i]==0xa5);
    free(p);
}
int main(int argc,char **argv)
{
    check(argc==3); size_t n,m; uint8_t *p=readfile(argv[1],&n), *raw=readfile(argv[2],&m);
    check(n>32); uint32_t *h=(uint32_t *)p; check(h[3]==m && h[4]==n-32);
    uint8_t *out=malloc(m+32); check(out!=NULL); memset(out,0xa5,m+32);
    check(!compact_lz4(p+32,n-32,out+16,m)); check(!memcmp(out+16,raw,m));
    check(compact_crc32(out+16,m)==h[5]);
    for(unsigned i=0;i<16;i++) check(out[i]==0xa5 && out[m+16+i]==0xa5);
    reject(p+32,n-33,m); reject(p+32,n-32,m-1); reject(p+32,n-32,m+1);
    const uint8_t zero_offset[]={0x10,'x',0,0,0}; reject(zero_offset,sizeof(zero_offset),10);
    const uint8_t far_offset[]={0x10,'x',2,0,0}; reject(far_offset,sizeof(far_offset),10);
    const uint8_t short_offset[]={0x10,'x',1}; reject(short_offset,sizeof(short_offset),10);
    const uint8_t truncated_len[]={0xf0,255}; reject(truncated_len,sizeof(truncated_len),300);
    const uint8_t too_long[]={0xf0,255,255,0}; reject(too_long,sizeof(too_long),20);
    const uint8_t no_match_room[]={0x10,'x',1,0}; reject(no_match_room,sizeof(no_match_room),3);
    const uint8_t overlap[]={0x1f,'x',1,0,30,0x10,'y'}; /* 50 x's and a final y */
    check(!compact_lz4(overlap,sizeof(overlap),out,51));
    for(unsigned i=0;i<50;i++) check(out[i]=='x');
    check(out[50]=='y');
    puts("ARM64_PRODUCTION_KERNEL_LZ4_AND_MALFORMED_INPUTS_PASS");
    free(p);free(raw);free(out); return 0;
}
