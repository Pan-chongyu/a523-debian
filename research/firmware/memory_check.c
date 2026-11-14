/* SPDX-License-Identifier: MIT
 * RAM-only validation for the new LPDDR3 initialization on this exact board.
 */
#define _GNU_SOURCE
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#define THREADS 8
#define MIB (1024UL*1024UL)
static size_t task_total=2560UL*MIB;
static pthread_barrier_t barrier;
struct worker {uint64_t *p;size_t count,base;unsigned errors;};
static uint64_t pattern(uint64_t x){
    x^=x>>30;x*=0xbf58476d1ce4e5b9ULL;x^=x>>27;
    x*=0x94d049bb133111ebULL;return x^(x>>31);
}
static void *run(void *arg){
    struct worker *w=arg;
    for(unsigned round=0;round<2;round++){
        uint64_t seed=round?0xaaaaaaaa55555555ULL:0x0123456789abcdefULL;
        for(size_t i=0;i<w->count;i++)w->p[i]=pattern((i+w->base)^seed);
        pthread_barrier_wait(&barrier);
        for(size_t i=0;i<w->count;i++){
            uint64_t expected=pattern((i+w->base)^seed),actual=w->p[i];
            if(actual!=expected){
                if(!w->errors)fprintf(stderr,"Mismatch word %zu: expected %016llx got %016llx\n",i+w->base,(unsigned long long)expected,(unsigned long long)actual);
                w->errors++;
            }
        }
        pthread_barrier_wait(&barrier);
    }
    return NULL;
}
int main(int argc,char **argv){
    if(argc>2)return 14;
    if(argc==2){
        char *end;unsigned long amount=strtoul(argv[1],&end,10);
        if(!*argv[1]||*end||amount<128||amount>2560||amount%8)return 14;
        task_total=amount*MIB;
    }
    FILE *f=fopen("/proc/meminfo","r");if(!f)return 10;
    char line[256];unsigned long available=0;
    while(fgets(line,sizeof(line),f))if(sscanf(line,"MemAvailable: %lu kB",&available)==1)break;
    fclose(f);if(available*1024UL<task_total+512*MIB){fprintf(stderr,"Insufficient available RAM: %lu KiB for %zu MiB test plus 512 MiB reserve\n",available,task_total/MIB);return 11;}
    uint64_t *p=malloc(task_total);if(!p)return 12;
    struct timespec start,end;clock_gettime(CLOCK_MONOTONIC,&start);
    pthread_t threads[THREADS];struct worker workers[THREADS];
    pthread_barrier_init(&barrier,NULL,THREADS);
    for(int i=0;i<THREADS;i++){
        workers[i]=(struct worker){p+i*(task_total/THREADS/8),task_total/THREADS/8,i*(task_total/THREADS/8),0};
        if(pthread_create(&threads[i],NULL,run,&workers[i]))_exit(13);
    }
    unsigned errors=0;
    for(int i=0;i<THREADS;i++){pthread_join(threads[i],NULL);errors+=workers[i].errors;}
    clock_gettime(CLOCK_MONOTONIC,&end);free(p);
    printf("RAM: %zu MiB, 8 threads, two full write/read patterns, errors=%u, %.2f seconds\n",task_total/MIB,errors,(end.tv_sec-start.tv_sec)+(end.tv_nsec-start.tv_nsec)/1e9);
    if(!errors)printf("MEMORY_TEST_%zu_MIB_8_THREADS_PASS\n",task_total/MIB);
    return errors?1:0;
}
