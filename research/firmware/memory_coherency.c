/* SPDX-License-Identifier: MIT
 * Verify cross-CPU visibility on both A55 clusters using CPU-only memory.
 */
#define _GNU_SOURCE
#include <pthread.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#define CPUS 8
#define WORDS 256
#define ROUNDS 4096
static uint64_t shared[CPUS][WORDS] __attribute__((aligned(64)));
static pthread_barrier_t barrier;
static unsigned failures[CPUS];
static uint64_t expected(unsigned round, unsigned cpu, unsigned word)
{
    return ((uint64_t)round << 40) ^ ((uint64_t)cpu << 32) ^
           (0x9e3779b97f4a7c15ULL * (word + 1));
}
static void *worker(void *arg)
{
    unsigned cpu = (uintptr_t)arg;
    cpu_set_t set;
    CPU_ZERO(&set);
    CPU_SET(cpu, &set);
    if (pthread_setaffinity_np(pthread_self(), sizeof(set), &set))
        abort();
    for (unsigned r = 0; r < ROUNDS; r++) {
        for (unsigned i = 0; i < WORDS; i++)
            shared[cpu][i] = expected(r, cpu, i);
        pthread_barrier_wait(&barrier);
        for (unsigned other = 0; other < CPUS; other++)
            for (unsigned i = 0; i < WORDS; i++)
                if (shared[other][i] != expected(r, other, i))
                    failures[cpu]++;
        pthread_barrier_wait(&barrier);
    }
    return NULL;
}
int main(void)
{
    pthread_t threads[CPUS];
    unsigned errors = 0;
    if (pthread_barrier_init(&barrier, NULL, CPUS)) return 2;
    for (uintptr_t i = 0; i < CPUS; i++)
        if (pthread_create(&threads[i], NULL, worker, (void *)i)) abort();
    for (unsigned i = 0; i < CPUS; i++) {
        pthread_join(threads[i], NULL);
        printf("CPU%u cross-core visibility errors=%u\n", i, failures[i]);
        errors += failures[i];
    }
    puts(errors ? "CPU_COHERENCY_FAILED" : "CPU_COHERENCY_8_CPUS_PASS");
    return !!errors;
}
