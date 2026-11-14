// SPDX-License-Identifier: MIT
/* A dependent integer workload; no clock or voltage register access. */
#define _GNU_SOURCE
#include <inttypes.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

static double seconds(struct timespec a, struct timespec b)
{
    return b.tv_sec - a.tv_sec + (b.tv_nsec - a.tv_nsec) / 1e9;
}

int main(int argc, char **argv)
{
    unsigned long cpu;
    char *end;
    cpu_set_t mask;
    struct timespec wall_start, wall_end, cpu_start, cpu_end;
    uint64_t value = UINT64_C(0x123456789abcdef0);
    const uint64_t multiplier = UINT64_C(6364136223846793005);
    const uint64_t increment = UINT64_C(1442695040888963407);
    if (argc != 2)
        return 2;
    cpu = strtoul(argv[1], &end, 10);
    if (*end || cpu > 7)
        return 2;
    CPU_ZERO(&mask);
    CPU_SET(cpu, &mask);
    if (sched_setaffinity(0, sizeof(mask), &mask))
        return 3;
    clock_gettime(CLOCK_MONOTONIC, &wall_start);
    clock_gettime(CLOCK_THREAD_CPUTIME_ID, &cpu_start);
    for (unsigned i = 0; i < 24000000; i++) {
        asm volatile("mul %0, %0, %1\n\t"
                     "add %0, %0, %2\n\t"
                     "eor %0, %0, %0, lsr #19\n\t"
                     "ror %0, %0, #17\n\t"
                     "mul %0, %0, %1\n\t"
                     "add %0, %0, %2\n\t"
                     "eor %0, %0, %0, lsr #23\n\t"
                     "ror %0, %0, #13"
                     : "+r"(value) : "r"(multiplier), "r"(increment));
    }
    clock_gettime(CLOCK_THREAD_CPUTIME_ID, &cpu_end);
    clock_gettime(CLOCK_MONOTONIC, &wall_end);
    printf("{\"cpu\":%lu,\"checksum\":\"%016" PRIx64 "\","
           "\"thread_seconds\":%.6f,\"wall_seconds\":%.6f}\n",
           cpu, value, seconds(cpu_start, cpu_end), seconds(wall_start, wall_end));
    return 0;
}
