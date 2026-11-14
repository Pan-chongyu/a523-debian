/* SPDX-License-Identifier: MIT */
#ifndef TZX_COMPACT_LZ4_H
#define TZX_COMPACT_LZ4_H
#include <stdint.h>
#include <stddef.h>
int compact_lz4(const uint8_t *src, size_t packed, uint8_t *dst, size_t raw);
uint32_t compact_crc32(const void *data, size_t n);
#endif
