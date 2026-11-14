#define _GNU_SOURCE
#include <errno.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

static uint64_t value(size_t word) {
    size_t page=word/512, offset=word%512;
    uint64_t x=page*0x9e3779b97f4a7c15ULL+0x523beef;
    if ((page&15)==0) { x^=offset*0xd6e8feb86659fd93ULL; x^=x>>29; x*=0xbf58476d1ce4e5b9ULL; }
    return x;
}
int main(void) {
    size_t bytes=256UL<<20,words=bytes/8;
    uint64_t *p=mmap(NULL,bytes,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    if(p==MAP_FAILED) {perror("mmap");return 1;}
    for(size_t i=0;i<words;i++)p[i]=value(i);
    if(madvise(p,bytes,MADV_PAGEOUT)){perror("MADV_PAGEOUT");return 2;}
    puts("ZRAM_PAGEOUT_COMPLETE_256_MIB");fflush(stdout);
    sleep(2);
    FILE *f=fopen("/sys/block/zram0/mm_stat","r");char line[512]={0};
    if(!f||!fgets(line,sizeof(line),f))return 3;
    fclose(f);printf("ZRAM_MM_STAT_AFTER_PAGEOUT %s",line);fflush(stdout);
    unsigned long long original,compressed,used;
    if(sscanf(line,"%llu %llu %llu",&original,&compressed,&used)!=3||original<64UL*1024*1024||!compressed||compressed>=original)return 4;
    uint64_t checksum=0;
    for(size_t i=0;i<words;i++){uint64_t observed=p[i];if(observed!=value(i)){fprintf(stderr,"MISMATCH %zu\n",i);return 5;}checksum+=observed;}
    munmap(p,bytes);
    printf("ZRAM_SWAPOUT_SWAPIN_256_MIB_EVERY_WORD_VERIFIED %016" PRIx64 "\n",checksum);
    return 0;
}
