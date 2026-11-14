/* SPDX-License-Identifier: MIT
 * Read each aligned DRAM word once. Keep the same SRAM lookup table and
 * byte-order CRC convention; unaligned callers retain byte loads.
 */
#include <stdint.h>
#define TABLE ((const uint32_t *)0x4be2c)
static inline __attribute__((always_inline)) uint32_t byte(uint32_t crc,uint32_t value) {
    return (crc>>8)^TABLE[(crc^value)&255];
}
uint32_t boot_crc_word(uint32_t crc,const void *data) {
    if ((uintptr_t)data&3) {
        const unsigned char *p=data;
        for (unsigned i=0;i<512;i++) crc=byte(crc,p[i]);
    } else {
        const volatile uint32_t *p=data;
        for (unsigned i=0;i<128;i++) {
            uint32_t word=p[i];
            crc=byte(crc,word);crc=byte(crc,word>>8);
            crc=byte(crc,word>>16);crc=byte(crc,word>>24);
        }
    }
    return crc;
}
