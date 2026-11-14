/* SPDX-License-Identifier: MIT
 * Allocation-free raw LZ4 block decoder. Every read, write and back-reference
 * is bounded. The copy must preserve the sequential semantics of matches.
 */
#include "compact_lz4.h"

static uint64_t load8(const uint8_t *p)
{
    if (!((uintptr_t)p & 7)) return *(const uint64_t *)p;
    uint64_t v = 0;
    for (unsigned i = 0; i < 8; ++i) v |= (uint64_t)p[i] << (8*i);
    return v;
}

static void copy(uint8_t *dst, const uint8_t *src, size_t n, size_t distance)
{
    while (n && ((uintptr_t)dst & 7)) { *dst++ = *src++; --n; }
    if (distance >= 8) {
        while (n >= 8) {
            *(uint64_t *)dst = load8(src);
            dst += 8; src += 8; n -= 8;
        }
    }
    while (n--) *dst++ = *src++;
}

static int length(const uint8_t **in, const uint8_t *end, size_t initial,
                  size_t limit, size_t *value)
{
    size_t n = initial;
    if (initial == 15) {
        unsigned byte;
        do {
            if (*in == end) return -1;
            byte = *(*in)++;
            if (n > limit || byte > limit-n) return -2;
            n += byte;
        } while (byte == 255);
    }
    if (n > limit) return -3;
    *value = n;
    return 0;
}

int compact_lz4(const uint8_t *src, size_t packed, uint8_t *dst, size_t raw)
{
    const uint8_t *in = src, *end = src+packed;
    uint8_t *out = dst;
    size_t remaining = raw;
    while (in < end) {
        unsigned token = *in++;
        size_t n;
        if (length(&in, end, token >> 4, remaining, &n)) return -10;
        if (n > (size_t)(end-in)) return -11;
        copy(out, in, n, (size_t)-1);
        in += n; out += n; remaining -= n;
        if (in == end) return remaining ? -12 : 0;
        if (end-in < 2) return -13;
        unsigned offset = in[0] | (unsigned)in[1] << 8;
        in += 2;
        if (!offset || offset > (size_t)(out-dst)) return -14;
        if (remaining < 4 || length(&in, end, token & 15, remaining-4, &n)) return -15;
        n += 4;
        copy(out, out-offset, n, offset);
        out += n; remaining -= n;
    }
    return -16;
}

uint32_t compact_crc32(const void *data, size_t n)
{
    const uint8_t *p = data;
    uint32_t crc = ~0U;
    /* ARMv8 CRC32 is available on both A523 CPU clusters. */
    while (n && ((uintptr_t)p & 7)) {
        __asm__ volatile("crc32b %w0, %w0, %w1" : "+r"(crc) : "r"(*p++)); --n;
    }
    while (n >= 8) {
        __asm__ volatile("crc32x %w0, %w0, %1" : "+r"(crc) : "r"(*(const uint64_t *)p));
        p += 8; n -= 8;
    }
    while (n--) __asm__ volatile("crc32b %w0, %w0, %w1" : "+r"(crc) : "r"(*p++));
    return ~crc;
}
