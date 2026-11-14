/* SPDX-License-Identifier: MIT
 * Fixed, locked source and destination mappings: isolate copying from reuse.
 * Reads a system library; writes only one private diagnostic capture on error.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#define CPUS 8
static const char library[] = "/usr/lib/aarch64-linux-gnu/libgio-2.0.so.0.8400.4";
static const unsigned char *source, *expected;
static unsigned char *targets[CPUS];
static size_t length, rounded;
static double until;
static atomic_int stopped;
static atomic_ulong iterations[CPUS];
static pthread_barrier_t ready;
static const char *prefix;
static unsigned cpu_mask = 255;
static const char *copy_mode = "libc";
static uint64_t initial_pfns[CPUS+2][1024];
extern void *__memcpy_generic(void *, const void *, size_t);
extern void *__memcpy_simd(void *, const void *, size_t);

static void scalar_copy(unsigned char *to, const unsigned char *from, size_t bytes)
{
    /* Volatile explicitly prevents loop recognition/vectorization into memcpy. */
    volatile uint64_t *d = (volatile uint64_t *)to;
    const volatile uint64_t *s = (const volatile uint64_t *)from;
    size_t words = bytes/8;
    for (size_t i = 0; i < words; i++) d[i] = s[i];
    for (size_t i = words*8; i < bytes; i++)
        ((volatile unsigned char *)to)[i] = ((const volatile unsigned char *)from)[i];
}

static double now(void)
{
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts)) _exit(2);
    return (double)ts.tv_sec + (double)ts.tv_nsec/1e9;
}
static void require(int value, const char *what)
{
    if (!value) { perror(what); fflush(NULL); _exit(2); }
}
static void full_write(int fd, const void *data, size_t bytes)
{
    const unsigned char *p = data;
    while (bytes) {
        ssize_t n = write(fd, p, bytes);
        require(n > 0, "capture write");
        p += (size_t)n; bytes -= (size_t)n;
    }
}
static uint64_t physical(const void *address)
{
    int fd = open("/proc/self/pagemap", O_RDONLY);
    uint64_t entry = 0;
    require(fd >= 0, "pagemap");
    require(pread(fd, &entry, 8, (off_t)((uintptr_t)address/4096*8)) == 8, "pagemap read");
    close(fd);
    require((entry & (1ULL<<63)) != 0, "pagemap present");
    return (entry & ((1ULL<<55)-1))*4096;
}

/* Optional placement comparison. Allocate only private anonymous RAM, select
 * eight wholly high-address ranges, lock them, and release every unused page
 * before the copying phase. The workload itself keeps fixed mappings.
 */
static int high_targets(void)
{
    const size_t pool_bytes = (size_t)2816*1024*1024;
    FILE *info = fopen("/proc/meminfo", "r");
    require(info != NULL, "memory information");
    char line[256];
    unsigned long available_kb = 0;
    while (fgets(line, sizeof(line), info))
        if (sscanf(line, "MemAvailable: %lu kB", &available_kb) == 1) break;
    fclose(info);
    if ((uint64_t)available_kb*1024 < pool_bytes+(size_t)512*1024*1024) {
        printf("LIBRARY_FIXED_COPY_INCONCLUSIVE insufficient_headroom available_kb=%lu\n", available_kb);
        return 0;
    }
    printf("LIBRARY_FIXED_COPY_HIGH_POOL_BEGIN bytes=%zu available_kb=%lu\n", pool_bytes, available_kb);
    fflush(NULL);
    unsigned char *pool = mmap(NULL, pool_bytes, PROT_READ|PROT_WRITE,
                              MAP_PRIVATE|MAP_ANONYMOUS, -1, 0);
    require(pool != MAP_FAILED, "high-address selection pool");
    for (size_t off = 0; off < pool_bytes; off += 4096)
        ((volatile unsigned char *)pool)[off] = 0;
    int fd = open("/proc/self/pagemap", O_RDONLY);
    require(fd >= 0, "selection pagemap");
    uint64_t entries[512];
    size_t run = 0, high = 0;
    unsigned selected = 0;
    for (size_t page = 0; page < pool_bytes/4096; page += 512) {
        require(pread(fd, entries, sizeof(entries),
                      (off_t)(((uintptr_t)pool/4096+page)*8)) == (ssize_t)sizeof(entries),
                "selection page entries");
        for (size_t i = 0; i < 512; i++) {
            int above = (entries[i] & (1ULL<<63)) &&
                        (entries[i] & ((1ULL<<55)-1)) >= (1ULL<<20);
            if (above) high++;
            if (selected == CPUS) continue;
            run = above ? run+1 : 0;
            if (run == rounded/4096) {
                targets[selected++] = pool+(page+i+1-run)*4096;
                run = 0;
            }
        }
    }
    close(fd);
    if (selected != CPUS) {
        printf("LIBRARY_FIXED_COPY_INCONCLUSIVE high_pool_pages=%zu selected=%u\n", high, selected);
        require(!munmap(pool, pool_bytes), "release unsuccessful pool");
        return 0;
    }
    unsigned char *cursor = pool;
    for (unsigned cpu = 0; cpu < CPUS; cpu++) {
        require(!mlock(targets[cpu], rounded), "lock selected target");
        if (targets[cpu] > cursor)
            require(!munmap(cursor, (size_t)(targets[cpu]-cursor)), "release pool gap");
        cursor = targets[cpu]+rounded;
    }
    if (cursor < pool+pool_bytes)
        require(!munmap(cursor, (size_t)(pool+pool_bytes-cursor)), "release remaining pool");
    for (unsigned cpu = 0; cpu < CPUS; cpu++) {
        for (size_t off = 0; off < rounded; off += 4096)
            if (physical(targets[cpu]+off) < (1ULL<<32)) {
                printf("LIBRARY_FIXED_COPY_INCONCLUSIVE selected_page_moved_low cpu=%u\n", cpu);
                return 0;
            }
        memset(targets[cpu], 0, rounded);
    }
    printf("LIBRARY_FIXED_COPY_HIGH_POOL_RELEASED high_pool_pages=%zu selected_bytes=%zu\n",
           high, rounded*CPUS);
    fflush(NULL);
    return 1;
}
static void save(const char *suffix, const void *data, size_t bytes)
{
    char name[240];
    require(snprintf(name, sizeof(name), "%s-%s", prefix, suffix) < (int)sizeof(name), "capture name");
    int fd = open(name, O_WRONLY | O_CREAT | O_EXCL, 0600);
    require(fd >= 0, "capture open");
    full_write(fd, data, bytes); require(!fsync(fd), "capture fsync"); close(fd);
}
static int physical_order(const void *a, const void *b)
{
    uint64_t x = *(const uint64_t *)a, y = *(const uint64_t *)b;
    return (x > y) - (x < y);
}
static int mapping_snapshot(const char *suffix, int baseline)
{
    char name[240];
    require(snprintf(name, sizeof(name), "%s-%s", prefix, suffix) < (int)sizeof(name), "map name");
    FILE *stream = fopen(name, "wx");
    require(stream != NULL, "map snapshot open");
    uint64_t all[(CPUS+2)*1024];
    size_t count = 0, changed = 0;
    require(rounded/4096 <= 1024, "bounded page count");
    for (unsigned role = 0; role < CPUS+2; role++) {
        const unsigned char *base = role == 0 ? source : role == 1 ? expected : targets[role-2];
        if (!base) continue;
        for (size_t page = 0; page < rounded/4096; page++) {
            uint64_t pa = physical(base+page*4096);
            if (baseline) initial_pfns[role][page] = pa;
            else if (initial_pfns[role][page] && initial_pfns[role][page] != pa) changed++;
            all[count++] = pa;
            fprintf(stream, "%u %zu %llx %llx\n", role, page,
                    (unsigned long long)(uintptr_t)(base+page*4096), (unsigned long long)pa);
        }
    }
    require(!fflush(stream) && !fsync(fileno(stream)), "map snapshot sync");
    require(!fclose(stream), "map snapshot close");
    qsort(all, count, sizeof(all[0]), physical_order);
    size_t duplicates = 0;
    for (size_t i = 1; i < count; i++) if (all[i] == all[i-1]) duplicates++;
    printf("LIBRARY_FIXED_COPY_MAPPING snapshot=%s pages=%zu duplicate_pfns=%zu changed_pfns=%zu reference_readonly=1\n",
           suffix, count, duplicates, changed);
    fflush(NULL);
    return !duplicates;
}
static void *worker(void *argument)
{
    unsigned cpu = (unsigned)(uintptr_t)argument;
    cpu_set_t mask;
    CPU_ZERO(&mask); CPU_SET(cpu, &mask);
    require(!pthread_setaffinity_np(pthread_self(), sizeof(mask), &mask), "CPU affinity");
    pthread_barrier_wait(&ready);
    while (!atomic_load(&stopped) && now() < until) {
        memset(targets[cpu], 0xa5, length);
        if (!strcmp(copy_mode, "libc-dsb")) __asm__ volatile("dsb sy" ::: "memory");
        if (!strcmp(copy_mode, "generic")) __memcpy_generic(targets[cpu], source, length);
        else if (!strcmp(copy_mode, "scalar")) scalar_copy(targets[cpu], source, length);
        else memcpy(targets[cpu], source, length);
        if (!strcmp(copy_mode, "libc-dsb")) __asm__ volatile("dsb sy" ::: "memory");
        int compared = memcmp(targets[cpu], expected, length);
        if (compared) {
            if (atomic_exchange(&stopped, 1)) return NULL;
            size_t first = 0, last = 0, count = 0;
            for (size_t i = 0; i < length; i++) if (targets[cpu][i] != expected[i]) {
                if (!count) first = i;
                last = i; count++;
            }
            /* Snapshot before further allocation or buffered stdio. */
            save("copied.bin", targets[cpu], length);
            mapping_snapshot("mapping-error.txt", 0);
            unsigned char *repeat = mmap(NULL, rounded, PROT_READ|PROT_WRITE,
                                         MAP_PRIVATE|MAP_ANONYMOUS, -1, 0);
            require(repeat != MAP_FAILED, "repeat buffer");
            const volatile unsigned char *p = source;
            for (size_t i = 0; i < length; i++) repeat[i] = p[i];
            save("volatile-repeat.bin", repeat, length);
            save("expected.bin", expected, length);
            int mem = open("/proc/self/mem", O_RDONLY);
            require(mem >= 0, "independent process memory");
            require(pread(mem, repeat, length, (off_t)(uintptr_t)source) == (ssize_t)length,
                    "independent source read");
            save("proc-source.bin", repeat, length);
            require(pread(mem, repeat, length, (off_t)(uintptr_t)targets[cpu]) == (ssize_t)length,
                    "independent target read");
            save("proc-target.bin", repeat, length);
            close(mem);
            const volatile unsigned char *original = source;
            for (size_t i = 0; i < length; i++) repeat[i] = original[i];
            int repeated = memcmp(targets[cpu], expected, length);
            printf("LIBRARY_FIXED_COPY_MISMATCH cpu=%u iterations=%lu initial_memcmp=%d repeated_memcmp=%d bytes=%zu first=%zx last=%zx source_phys=%llx target_phys=%llx reference_phys=%llx repeat_correct=%d\n",
                   cpu, atomic_load(&iterations[cpu]), compared, repeated, count, first, last,
                   (unsigned long long)physical(source+first),
                   (unsigned long long)physical(targets[cpu]+first),
                   (unsigned long long)physical(expected+first),
                   !memcmp(repeat, expected, length));
            fflush(NULL);
            return NULL;
        }
        atomic_fetch_add(&iterations[cpu], 1);
        /* Bound memory bandwidth so this monitor does not replace GPU load. */
        usleep(25000);
    }
    return NULL;
}
int main(int argc, char **argv)
{
    require((argc == 3 || argc == 5) && geteuid() == 0,
            "usage: seconds /home/debian/capture-prefix [cpu-mask libc|generic|scalar|libc-dsb|matrix]");
    char *end;
    long seconds = strtol(argv[1], &end, 10);
    require(!*end && seconds >= 10 && seconds <= 780, "bounded duration");
    prefix = argv[2];
    if (argc == 5) {
        unsigned long mask = strtoul(argv[3], &end, 0);
        require(!*end && mask && mask <= 255, "CPU mask");
        cpu_mask = (unsigned)mask;
        copy_mode = argv[4];
        require(!strcmp(copy_mode, "libc") || !strcmp(copy_mode, "generic") ||
                !strcmp(copy_mode, "scalar") || !strcmp(copy_mode, "libc-dsb") ||
                !strcmp(copy_mode, "matrix"), "copy mode");
    }
    require(!strncmp(prefix, "/home/debian/", 13) && !strstr(prefix, "..") && strlen(prefix)<180, "capture prefix");
    int fd = open(library, O_RDONLY);
    struct stat st;
    require(fd >= 0 && !fstat(fd, &st) && st.st_size > 0 && st.st_size < 4*1024*1024, "library open");
    length = (size_t)st.st_size; rounded = (length+4095)&~(size_t)4095;
    source = mmap(NULL, length, PROT_READ, MAP_PRIVATE, fd, 0);
    require(source != MAP_FAILED, "readonly source");
    close(fd);
    unsigned char *reference = mmap(NULL, rounded, PROT_READ|PROT_WRITE,
                                   MAP_PRIVATE|MAP_ANONYMOUS, -1, 0);
    require(reference != MAP_FAILED, "dedicated direct reference");
    fd = open(library, O_RDONLY|O_DIRECT);
    require(fd >= 0, "direct reference open");
    size_t done = 0;
    while (done < length) {
        ssize_t n = pread(fd, reference+done, rounded-done, (off_t)done);
        require(n > 0, "direct reference read"); done += (size_t)n;
    }
    close(fd); expected = reference;
    require(!memcmp(source, expected, length), "reference compare");
    require(!mlock(source, length) && !mlock(expected, rounded), "lock source/reference");
    require(!mprotect(reference, rounded, PROT_READ), "protect immutable reference");
    require(mapping_snapshot("mapping-reference-before-pool.txt", 1), "distinct initial reference PFNs");
    const char *select_high = getenv("TZX_COPY_HIGH_TARGETS");
    if (select_high) {
        require(!strcmp(select_high, "1"), "high-target selection option");
        if (!high_targets()) return 4;
    } else for (unsigned cpu = 0; cpu < CPUS; cpu++) {
        targets[cpu] = mmap(NULL, rounded, PROT_READ|PROT_WRITE, MAP_PRIVATE|MAP_ANONYMOUS, -1, 0);
        require(targets[cpu] != MAP_FAILED, "fixed target");
        memset(targets[cpu], 0, rounded);
        require(!mlock(targets[cpu], rounded), "lock fixed target");
    }
    unsigned high = 0;
    for (size_t offset = 0; offset < length; offset += 4096) if (physical(source+offset) >= (1ULL<<32)) high++;
    printf("LIBRARY_FIXED_COPY_READY cpus=%u bytes=%zu source_pages_above_4g=%u locked_bytes=%zu\n",
           CPUS, length, high, rounded*(CPUS+2));
    printf("LIBRARY_FIXED_COPY_METHOD mask=0x%x mode=%s resolved_memcpy=%p generic=%p simd=%p source=%p reference=%p\n",
           cpu_mask, copy_mode, (void *)memcpy, (void *)__memcpy_generic,
           (void *)__memcpy_simd, (const void *)source, (const void *)expected);
    for (unsigned cpu = 0; cpu < CPUS; cpu++) {
        unsigned target_high = 0;
        for (size_t off = 0; off < length; off += 4096)
            if (physical(targets[cpu]+off) >= (1ULL<<32)) target_high++;
        printf("LIBRARY_FIXED_COPY_TARGET cpu=%u address=%p physical_first=%llx high_pages=%u total_pages=%zu\n", cpu,
               (void *)targets[cpu], (unsigned long long)physical(targets[cpu]),
               target_high, rounded/4096);
    }
    fflush(NULL);
    require(mapping_snapshot("mapping-before.txt", 1), "distinct source/reference/target PFNs");
    require(!memcmp(source, expected, length), "reference after target allocation");
    unsigned workers = 0;
    for (unsigned cpu = 0; cpu < CPUS; cpu++) if (cpu_mask & (1u<<cpu)) workers++;
    int matrix = !strcmp(copy_mode, "matrix");
    require(!matrix || seconds <= 120, "bounded matrix duration");
    const char *phases[] = {"libc", "libc-dsb", "libc", "scalar"};
    unsigned failures = 0;
    const char *base_prefix = prefix;
    for (unsigned phase = 0; phase < (matrix ? 4u : 1u); phase++) {
        char phase_prefix[240];
        if (matrix) {
            copy_mode = phases[phase];
            require(snprintf(phase_prefix, sizeof(phase_prefix), "%s-phase%u-%s",
                             base_prefix, phase, copy_mode) < (int)sizeof(phase_prefix),
                    "phase prefix");
            prefix = phase_prefix;
        }
        for (unsigned cpu = 0; cpu < CPUS; cpu++) atomic_store(&iterations[cpu], 0);
        atomic_store(&stopped, 0);
        until = now()+(double)seconds;
        printf("LIBRARY_FIXED_COPY_PHASE_BEGIN phase=%u mode=%s same_fixed_buffers=1\n", phase, copy_mode);
        fflush(NULL);
        require(!pthread_barrier_init(&ready, NULL, workers), "worker barrier");
        pthread_t threads[CPUS];
        for (unsigned cpu = 0; cpu < CPUS; cpu++) if (cpu_mask & (1u<<cpu))
            require(!pthread_create(&threads[cpu], NULL, worker, (void *)(uintptr_t)cpu), "worker create");
        unsigned long total = 0;
        for (unsigned cpu = 0; cpu < CPUS; cpu++) {
            if (!(cpu_mask & (1u<<cpu))) continue;
            require(!pthread_join(threads[cpu], NULL), "worker join");
            total += atomic_load(&iterations[cpu]);
        }
        require(!pthread_barrier_destroy(&ready), "destroy worker barrier");
        if (atomic_load(&stopped)) failures++;
        printf("LIBRARY_FIXED_COPY_PHASE_END phase=%u mode=%s result=%s copies=%lu\n", phase,
               copy_mode, atomic_load(&stopped) ? "FAIL" : "PASS", total);
        fflush(NULL);
    }
    if (failures) return 3;
    printf("LIBRARY_FIXED_COPY_PASS cpus=%u seconds_per_phase=%ld bytes=%zu high_source_pages=%u\n", workers, seconds, length, high);
    return 0;
}
