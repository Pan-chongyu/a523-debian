/* SPDX-License-Identifier: MIT
 * CPU-only instruction-cache/mprotect comparison. No device access or GPU.
 */
#define _GNU_SOURCE
#include <fcntl.h>
#include <pthread.h>
#include <sched.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <ucontext.h>
#include <unistd.h>

#define CPUS 8
#define PAGES 1024U
#define PAGE 4096UL
#define ROUNDS 64U
static uint8_t *code;
static pthread_barrier_t ready, done;
static unsigned current_round;

static void check(int value, const char *message)
{
    if (!value) { perror(message); fflush(NULL); _exit(2); }
}
static uint32_t expected(unsigned round, unsigned page)
{
    return 0xa55c0000U ^ (round * 0x10001U) ^ (page * 0x123457U);
}
static void append_hex(char **cursor, uintptr_t value)
{
    static const char digits[] = "0123456789abcdef";
    *(*cursor)++ = '0'; *(*cursor)++ = 'x';
    for (int shift = 60; shift >= 0; shift -= 4)
        *(*cursor)++ = digits[(value >> shift) & 15];
}
static void fault(int signo, siginfo_t *info, void *context)
{
    ucontext_t *uc = context;
    char buffer[160], *cursor = buffer;
    const char prefix[] = "CPU_EXECUTION_SIGNAL pc=";
    memcpy(cursor, prefix, sizeof(prefix) - 1); cursor += sizeof(prefix) - 1;
    append_hex(&cursor, uc->uc_mcontext.pc);
    memcpy(cursor, " address=", 9); cursor += 9;
    append_hex(&cursor, (uintptr_t)info->si_addr);
    memcpy(cursor, " signal=", 8); cursor += 8;
    append_hex(&cursor, (uintptr_t)signo);
    *cursor++ = '\n';
    (void)write(STDOUT_FILENO, buffer, (size_t)(cursor - buffer));
    _exit(128 + signo);
}
static void *worker(void *argument)
{
    unsigned cpu = (unsigned)(uintptr_t)argument;
    cpu_set_t mask;
    CPU_ZERO(&mask); CPU_SET(cpu, &mask);
    check(!pthread_setaffinity_np(pthread_self(), sizeof(mask), &mask), "affinity");
    for (unsigned round = 0; round < ROUNDS; round++) {
        pthread_barrier_wait(&ready);
        check(current_round == round, "round publication");
        for (unsigned repeat = 0; repeat < 4; repeat++) {
            for (unsigned i = 0; i < PAGES; i++) {
                unsigned page = (i * 257U + cpu * 37U + repeat) & (PAGES - 1U);
                uint32_t (*function)(void) = (void *)(code + page * PAGE);
                uint32_t actual = function();
                if (actual != expected(round, page)) {
                    printf("CPU_EXECUTION_MISMATCH cpu=%u round=%u page=%u expected=%08x actual=%08x\n",
                           cpu, round, page, expected(round, page), actual);
                    fflush(NULL); _exit(3);
                }
            }
        }
        pthread_barrier_wait(&done);
    }
    return NULL;
}
int main(void)
{
    struct timespec started, ended;
    struct sigaction action = { .sa_sigaction = fault, .sa_flags = SA_SIGINFO };
    pthread_t threads[CPUS];
    size_t length = PAGES * PAGE;
    uint64_t minimum = UINT64_MAX, maximum = 0;
    unsigned above_4g = 0;
    check(geteuid() == 0, "root for pagemap");
    sigemptyset(&action.sa_mask);
    check(!sigaction(SIGILL, &action, NULL) && !sigaction(SIGSEGV, &action, NULL), "signals");
    clock_gettime(CLOCK_MONOTONIC, &started);
    code = mmap(NULL, length, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    check(code != MAP_FAILED, "mapping");
    memset(code, 0, length);
    int pagemap = open("/proc/self/pagemap", O_RDONLY);
    check(pagemap >= 0, "pagemap");
    for (unsigned page = 0; page < PAGES; page++) {
        uint64_t entry;
        off_t offset = (off_t)(((uintptr_t)code / PAGE + page) * 8);
        check(pread(pagemap, &entry, sizeof(entry), offset) == sizeof(entry), "page read");
        check((entry & (1ULL << 63)) != 0, "resident");
        uint64_t physical = (entry & ((1ULL << 55) - 1)) * PAGE;
        check(physical != 0, "visible PFN");
        above_4g += physical >= (1ULL << 32);
        if (physical < minimum) minimum = physical;
        if (physical > maximum) maximum = physical;
    }
    close(pagemap);
    printf("CPU_EXECUTION_PAGES pages=%u above_4g=%u physical_min=%llx physical_max=%llx virtual=%p\n",
           PAGES, above_4g, (unsigned long long)minimum, (unsigned long long)maximum, code);
    fflush(stdout);
    check(above_4g > 0, "No high physical pages: comparison inconclusive");
    check(!pthread_barrier_init(&ready, NULL, CPUS + 1) &&
          !pthread_barrier_init(&done, NULL, CPUS + 1), "barriers");
    for (unsigned cpu = 0; cpu < CPUS; cpu++)
        check(!pthread_create(&threads[cpu], NULL, worker, (void *)(uintptr_t)cpu), "thread");
    for (unsigned round = 0; round < ROUNDS; round++) {
        check(!mprotect(code, length, PROT_READ | PROT_WRITE), "write protect");
        for (unsigned page = 0; page < PAGES; page++) {
            uint32_t value = expected(round, page);
            uint32_t *words = (void *)(code + page * PAGE);
            words[0] = 0xd503245f; /* BTI c is a NOP on cores without BTI. */
            words[1] = 0x52800000 | ((value & 0xffffU) << 5); /* movz w0 */
            words[2] = 0x72a00000 | ((value >> 16) << 5);   /* movk w0, lsl 16 */
            words[3] = 0xd65f03c0; /* ret */
        }
        __builtin___clear_cache((char *)code, (char *)code + length);
        check(!mprotect(code, length, PROT_READ | PROT_EXEC), "execute protect");
        current_round = round;
        pthread_barrier_wait(&ready);
        pthread_barrier_wait(&done);
    }
    for (unsigned cpu = 0; cpu < CPUS; cpu++)
        check(!pthread_join(threads[cpu], NULL), "join");
    clock_gettime(CLOCK_MONOTONIC, &ended);
    printf("CPU_EXECUTION_COHERENCY_PASS cpus=%u rounds=%u calls=%u seconds=%.3f\n", CPUS,
           ROUNDS, CPUS * ROUNDS * PAGES * 4U,
           (double)(ended.tv_sec - started.tv_sec) + (double)(ended.tv_nsec - started.tv_nsec) / 1e9);
    return 0;
}
