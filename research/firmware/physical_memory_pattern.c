/* SPDX-License-Identifier: MIT
 * Check owned, pinned pages with physical-address-derived values on all cores.
 * Does not map /dev/mem or access pages owned by the kernel/other processes.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#define CPUS 8u
#define PAGE 4096u
#define POOL ((size_t)2944*1024*1024)
static volatile uint64_t *pool;
static uint64_t *pages;
static size_t page_count;
static pthread_barrier_t barrier;
static unsigned errors[CPUS];
static const uint64_t seeds[] = {UINT64_C(0x0123456789abcdef), UINT64_C(0xaaaaaaaa55555555)};
static void check(int ok, const char *what)
{
    if (!ok) { perror(what); fflush(NULL); _exit(2); }
}
static uint64_t pattern(uint64_t value)
{
    value ^= value >> 30; value *= UINT64_C(0xbf58476d1ce4e5b9);
    value ^= value >> 27; value *= UINT64_C(0x94d049bb133111eb);
    return value ^ (value >> 31);
}
static int order(const void *a, const void *b)
{
    uint64_t x=*(const uint64_t *)a, y=*(const uint64_t *)b;
    return (x>y)-(x<y);
}
static void *worker(void *argument)
{
    unsigned cpu=(unsigned)(uintptr_t)argument;
    cpu_set_t mask;
    CPU_ZERO(&mask); CPU_SET(cpu,&mask);
    check(!pthread_setaffinity_np(pthread_self(),sizeof(mask),&mask),"worker affinity");
    for (unsigned round=0;round<2;round++) {
        size_t begin=cpu*(page_count/CPUS), end=begin+page_count/CPUS;
        for (size_t p=begin;p<end;p++) for (size_t lane=0;lane<PAGE/8;lane++)
            pool[p*(PAGE/8)+lane]=pattern((pages[p]+lane*8)^seeds[round]);
        pthread_barrier_wait(&barrier);
        /* Read a different core's range after every core finishes writing. */
        begin=((cpu+1)%CPUS)*(page_count/CPUS); end=begin+page_count/CPUS;
        for (size_t p=begin;p<end;p++) for (size_t lane=0;lane<PAGE/8;lane++) {
            uint64_t actual=pool[p*(PAGE/8)+lane];
            uint64_t expected=pattern((pages[p]+lane*8)^seeds[round]);
            if (actual!=expected) {
                if (errors[cpu]<4) printf("PHYSICAL_PATTERN_MISMATCH cpu=%u round=%u page=%zu offset=%zx physical=%llx expected=%016llx actual=%016llx\n",
                    cpu,round,p,p*PAGE+lane*8,(unsigned long long)(pages[p]+lane*8),
                    (unsigned long long)expected,(unsigned long long)actual);
                if (errors[cpu]!=UINT32_MAX) errors[cpu]++;
            }
        }
        pthread_barrier_wait(&barrier);
        if (!cpu) { printf("PHYSICAL_PATTERN_ROUND_COMPLETED round=%u\n",round);fflush(NULL); }
        pthread_barrier_wait(&barrier);
    }
    return NULL;
}
int main(void)
{
    check(geteuid()==0 && sysconf(_SC_PAGESIZE)==PAGE,"root and 4K pages");
    check(access("/sys/module/panfrost",F_OK)!=0 && errno==ENOENT,"GPU unloaded");
    FILE *info=fopen("/proc/meminfo","r");check(info!=NULL,"memory info");
    char line[256];unsigned long available=0;
    while (fgets(line,sizeof(line),info)) if (sscanf(line,"MemAvailable: %lu kB",&available)==1) break;
    fclose(info);
    if ((uint64_t)available*1024<POOL+(size_t)512*1024*1024) {
        printf("PHYSICAL_PATTERN_INCONCLUSIVE available_kb=%lu\n",available);return 4;
    }
    page_count=POOL/PAGE;
    pages=malloc(page_count*sizeof(*pages));check(pages!=NULL,"PFN table");
    pool=mmap(NULL,POOL,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    check(pool!=MAP_FAILED,"owned pool");
    check(!mlock((const void *)pool,POOL),"pin owned pool");
    int fd=open("/proc/self/pagemap",O_RDONLY);check(fd>=0,"pagemap");
    uint64_t entries[512];size_t high=0;
    for (size_t p=0;p<page_count;p+=512) {
        check(pread(fd,entries,sizeof(entries),(off_t)(((uintptr_t)pool/PAGE+p)*8))==(ssize_t)sizeof(entries),"PFN read");
        for (size_t i=0;i<512;i++) {
            check((entries[i]&(UINT64_C(1)<<63))!=0,"page present");
            pages[p+i]=(entries[i]&((UINT64_C(1)<<55)-1))*PAGE;
            if (pages[p+i]>=(UINT64_C(1)<<32)) high++;
        }
    }
    close(fd);
    uint64_t *sorted=malloc(page_count*sizeof(*sorted));check(sorted!=NULL,"sorted PFNs");
    memcpy(sorted,pages,page_count*sizeof(*sorted));qsort(sorted,page_count,sizeof(*sorted),order);
    for (size_t p=1;p<page_count;p++) check(sorted[p]!=sorted[p-1],"no duplicate owned PFNs");
    printf("PHYSICAL_PATTERN_BEGIN bytes=%zu pages=%zu above4g_pages=%zu min=%llx max=%llx cpus=8 cross_cpu_read=1\n",
        POOL,page_count,high,(unsigned long long)sorted[0],(unsigned long long)sorted[page_count-1]);
    free(sorted);fflush(NULL);
    check(!pthread_barrier_init(&barrier,NULL,CPUS),"barrier");
    pthread_t threads[CPUS];
    for (uintptr_t cpu=0;cpu<CPUS;cpu++) check(!pthread_create(&threads[cpu],NULL,worker,(void *)cpu),"thread");
    uint64_t total=0;
    for (unsigned cpu=0;cpu<CPUS;cpu++) {check(!pthread_join(threads[cpu],NULL),"join");total+=errors[cpu];}
    printf("PHYSICAL_PATTERN_RESULT errors=%llu status=%s\n",(unsigned long long)total,total?"FAIL":"PASS");
    return total?3:0;
}
