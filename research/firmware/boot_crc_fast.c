/* SPDX-License-Identifier: MIT
 * Drop-in for the frozen loader's 512-byte CRC32 function. The checksum,
 * polynomial, seed and return convention are unchanged. This routine only
 * reads its input and a const SRAM table; it does not access hardware.
 */
#include <stdint.h>
#include "boot_crc_table.h"

uint32_t boot_crc_fast(uint32_t crc, const unsigned char *data)
{
    const unsigned char *end = data + 512;
    while (data != end)
        crc = (crc >> 8) ^ boot_crc_table[(crc ^ *data++) & 255];
    return crc;
}
