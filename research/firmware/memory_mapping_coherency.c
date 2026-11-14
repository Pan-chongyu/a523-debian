/* SPDX-License-Identifier: MIT
 * CPU-only TLB shootdown check: remap shared pages while eight pinned
 * workers retain virtual addresses. No device mappings or physical writes.
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

#define CPUS 8
#define SPAN (2UL * 1024 * 1024)
#define PAGE 4096UL
#define LANES 8
#define ROUNDS 1024
static int backing;
static unsigned char *alias;
static unsigned char *slots[CPUS];
static pthread_barrier_t begin, finish;

static void check(int ok, const char *what)
{
    if (!ok) { perror(what); fflush(NULL); _exit(2); }
}
static uint64_t value(unsigned round, unsigned cpu, size_t page, unsigned lane)
{
    return 0xa55c000000000000ULL ^ ((uint64_t)round << 32) ^
           ((uint64_t)cpu << 24) ^ ((uint64_t)page << 8) ^ lane;
}
static size_t offset(unsigned bank, unsigned cpu)
{
    return (bank * CPUS + cpu) * SPAN;
}
static void *worker(void *arg)
{
    unsigned cpu = (unsigned)(uintptr_t)arg;
    cpu_set_t mask;
    CPU_ZERO(&mask); CPU_SET(cpu, &mask);
    check(pthread_setaffinity_np(pthread_self(), sizeof(mask), &mask) == 0, "pin worker");
    for (unsigned r = 0; r < ROUNDS; r++) {
        pthread_barrier_wait(&begin);
        for (size_t p = 0; p < SPAN / PAGE; p++) {
            volatile uint64_t *dst = (volatile uint64_t *)(slots[cpu] + p * PAGE);
            for (unsigned lane = 0; lane < LANES; lane++)
                dst[lane] = value(r + 1, cpu, p, lane);
        }
        pthread_barrier_wait(&finish);
    }
    return NULL;
}
static void show_pfns(void)
{
    int fd = open("/proc/self/pagemap", O_RDONLY);
    check(fd >= 0, "pagemap");
    size_t high = 0, visible = 0, total = CPUS * 2 * SPAN / PAGE;
    uint64_t min = UINT64_MAX, max = 0;
    for (size_t p = 0; p < total; p++) {
        uint64_t entry;
        off_t off = (off_t)((((uintptr_t)alias + p * PAGE) / PAGE) * 8);
        check(pread(fd, &entry, 8, off) == 8, "read pagemap");
        uint64_t pa = (entry & ((1ULL << 55) - 1)) * PAGE;
        check((entry & (1ULL << 63)) != 0, "page not resident");
        if (pa) {
            visible++;
            if (pa >= (1ULL << 32)) high++;
            if (pa < min) min = pa;
            if (pa > max) max = pa;
        }
    }
    close(fd);
    printf("MAPPING_BACKING pages=%zu visible=%zu above_4g=%zu min=%#llx max=%#llx\n",
           total, visible, high, (unsigned long long)min, (unsigned long long)max);
    check(visible == total, "root PFN visibility required");
    fflush(stdout);
}
int main(void)
{
    check(sysconf(_SC_PAGESIZE) == PAGE, "4K pages required");
    check(access("/sys/module/panfrost", F_OK) != 0 && errno == ENOENT, "GPU must be unloaded");
    check(geteuid() == 0, "root required for PFNs");
    cpu_set_t mask;
    CPU_ZERO(&mask); CPU_SET(0, &mask);
    check(sched_setaffinity(0, sizeof(mask), &mask) == 0, "pin controller");
    backing = memfd_create("tzx-cpu-tlb-test", MFD_CLOEXEC);
    check(backing >= 0, "memfd");
    check(ftruncate(backing, CPUS * 2 * SPAN) == 0, "ftruncate");
    alias = mmap(NULL, CPUS * 2 * SPAN, PROT_READ | PROT_WRITE, MAP_SHARED, backing, 0);
    check(alias != MAP_FAILED, "backing alias");
    for (unsigned bank = 0; bank < 2; bank++)
        for (unsigned cpu = 0; cpu < CPUS; cpu++)
            for (size_t p = 0; p < SPAN / PAGE; p++) {
                uint64_t *dst = (uint64_t *)(alias + offset(bank, cpu) + p * PAGE);
                for (unsigned l = 0; l < LANES; l++) dst[l] = value(0, cpu, p, l);
            }
    for (unsigned cpu = 0; cpu < CPUS; cpu++) {
        slots[cpu] = mmap(NULL, SPAN, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        check(slots[cpu] != MAP_FAILED, "reserve virtual slot");
    }
    show_pfns();
    check(pthread_barrier_init(&begin, NULL, CPUS + 1) == 0, "begin barrier");
    check(pthread_barrier_init(&finish, NULL, CPUS + 1) == 0, "finish barrier");
    pthread_t threads[CPUS];
    for (uintptr_t i = 0; i < CPUS; i++)
        check(pthread_create(&threads[i], NULL, worker, (void *)i) == 0, "worker create");
    struct timespec start, end;
    clock_gettime(CLOCK_MONOTONIC, &start);
    unsigned last[2] = {0, 0};
    for (unsigned r = 0; r < ROUNDS; r++) {
        unsigned bank = r % 2;
        for (unsigned cpu = 0; cpu < CPUS; cpu++)
            check(mmap(slots[cpu], SPAN, PROT_READ | PROT_WRITE, MAP_SHARED | MAP_FIXED,
                       backing, (off_t)offset(bank, cpu)) == slots[cpu], "switch mapping");
        pthread_barrier_wait(&begin);
        pthread_barrier_wait(&finish);
        last[bank] = r + 1;
        for (unsigned b = 0; b < 2; b++)
            for (unsigned cpu = 0; cpu < CPUS; cpu++)
                for (size_t p = 0; p < SPAN / PAGE; p++) {
                    volatile uint64_t *src = (volatile uint64_t *)(alias + offset(b, cpu) + p * PAGE);
                    for (unsigned l = 0; l < LANES; l++) {
                        uint64_t actual = src[l], expected = value(last[b], cpu, p, l);
                        if (actual != expected) {
                            fprintf(stderr, "MAPPING_MISMATCH r=%u bank=%u cpu=%u page=%zu lane=%u expected=%016llx got=%016llx\n",
                                    r, b, cpu, p, l, (unsigned long long)expected, (unsigned long long)actual);
                            fflush(NULL); _exit(1);
                        }
                    }
                }
        if ((r + 1) % 128 == 0) {
            printf("MAPPING_PROGRESS rounds=%u remaps=%u\n", r + 1, (r + 1) * CPUS);
            fflush(stdout);
        }
    }
    for (unsigned cpu = 0; cpu < CPUS; cpu++) pthread_join(threads[cpu], NULL);
    clock_gettime(CLOCK_MONOTONIC, &end);
    printf("CPU_MAPPING_COHERENCY_PASS cpus=8 rounds=%u remaps=%u backing_mib=32 seconds=%.3f\n",
           ROUNDS, CPUS * ROUNDS, (double)(end.tv_sec-start.tv_sec)+(double)(end.tv_nsec-start.tv_nsec)/1e9);
    return 0;
}
