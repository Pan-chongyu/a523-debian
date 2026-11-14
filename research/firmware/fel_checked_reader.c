/* SPDX-License-Identifier: MIT
 * Read-only SRAM harness for the exact cold-loader FIFO implementation.
 * Identity must already have been read with the independently built helper.
 * Init on the first request; retain controller state across subsequent reads.
 */
#ifdef RETRY_READER_TEST
#include "emmc_retry_reader.c"
#else
#include "emmc_reader.c"
#endif

void checked_work(void);
void __attribute__((naked, section(".text.entry"))) checked_entry(void) {
    __asm__ volatile(
        "mov r4, sp\n"
        "ldr sp, =0x58000\n"
        "push {r4, lr}\n"
        "bl checked_work\n"
        "pop {r4, lr}\n"
        "mov sp, r4\n"
        "bx lr\n");
}
void checked_work(void) {
    unsigned sector = readl(CMD_ADDR + 4), count = readl(CMD_ADDR + 8);
    unsigned retain = readl(CMD_ADDR + 12), op = readl(CMD_ADDR);
    if (op != CMD_READ || !count || count > 128 || sector >= 244318208 ||
        count > 244318208 - sector) {
        set_state(0xee); return;
    }
    if (!retain && cold_emmc_init()) { set_state(0xee); return; }
    set_state(0x10);
    for (unsigned i = 0; i < count; i++) {
        int rc = cold_emmc_read(sector + i, (void *)(DATA_BUF + i * 512));
        if (rc) {
            set_diag0(sector + i); set_diag1(-rc); set_state(0xee); return;
        }
    }
    set_progress(count); set_state(0xaa);
}
