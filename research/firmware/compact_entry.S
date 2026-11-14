/* SPDX-License-Identifier: MIT
 * TF-A enters at EL2 with MMU/data cache disabled. Keep that contract, use a
 * private stack and instruction cache, and retain the existing alias test.
 */
#include "compact_config.h"
.section .text.entry,"ax"
.global _start
_start:
    msr daifset, #0xf
    ldr x0, =0x4bfff000
    mov sp, x0
    mrs x20, sctlr_el2
    mrs x21, tcr_el2
    mrs x22, mair_el2
    mrs x23, ttbr0_el2
    adr x0, compact_vectors
    msr vbar_el2, x0
    isb
    mrs x0, sctlr_el2
    tst x0, #1
    b.ne compact_failure
    tst x0, #4
    b.ne compact_failure
    ic iallu
    dsb sy
    orr x0, x0, #0x1000
    msr sctlr_el2, x0
    isb
    ldr x10, =0x07090110
    ldr w11, =0xa5233301
    str w11, [x10]
    mov x9, #0
    ldr x12, =0x41000000
    ldr x13, =0x140000000
1:  add x14, x12, x9, lsl #28
    cmp x14, x13
    b.hs 2f
    ldr x15, =0xa5233344aabb0000
    eor x15, x15, x14
    str x15, [x14]
    add x9, x9, #1
    b 1b
2:  dsb sy
    mov x9, #0
3:  add x14, x12, x9, lsl #28
    cmp x14, x13
    b.hs 4f
    ldr x15, =0xa5233344aabb0000
    eor x15, x15, x14
    ldr x16, [x14]
    cmp x15, x16
    b.ne compact_failure
    add x9, x9, #1
    b 3b
4:  ldr w11, =0xa5233302
    str w11, [x10]
    str w9, [x10, #4]
    bl compact_boot
    cbnz w0, compact_failure
    bl compact_cache_finish
    msr tcr_el2, x21
    msr mair_el2, x22
    msr ttbr0_el2, x23
    msr sctlr_el2, x20
    dsb sy
    ic iallu
    dsb sy
    isb
    ldr x10, =0x07090110
    ldr w11, =0xa5233303
    str w11, [x10]
    ldr x0, =0x47000000
    mov x1, #0
    mov x2, #0
    mov x3, #0
    ldr x4, =0x48000000
    br x4
.global compact_failure
compact_failure:
    mrs x12, esr_el2
    mrs x13, elr_el2
    ldr x10, =0x2d800
    str w12, [x10, #24]
    str x13, [x10, #72]
    ldr x10, =0x07090110
    ldr w11, =0xa52333ee
    str w11, [x10]
    ldr x10, =0x07090118
    ldr w11, =0xa52322ee
    str w11, [x10]
    dsb sy
    ldr x10, =0x02050008
    ldr w11, =0x16aa0001
    str w11, [x10]
5:  wfi
    b 5b
.ltorg
.balign 2048
compact_vectors:
.rept 16
    b compact_failure
    .space 124
.endr

/* Operate only on scratch/output ranges. CTR_EL0 supplies the cache line.
 * The panel framebuffer, DT, initrd and TF-A remain untouched.
 */
.macro cache_range op, start, end
    ldr x0, =\start
    ldr x1, =\end
    mrs x2, ctr_el0
    ubfx x2, x2, #16, #4
    mov x3, #4
    lsl x2, x3, x2
1:  dc \op, x0
    add x0, x0, x2
    cmp x0, x1
    b.lo 1b
    dsb sy
.endm
.global compact_cache_enable
compact_cache_enable:
    cache_range ivac, 0x48000000, (0x48000000+COMPACT_RAW)
    cache_range ivac, 0x4a000000, 0x4a010000
    cache_range ivac, 0x4bf00000, 0x4c000000
    cache_range ivac, 0x50000000, (0x50000000+COMPACT_PACKED)
    ldr x0, =0xff00
    msr mair_el2, x0
    ldr x0, =0x80803519
    msr tcr_el2, x0
    ldr x0, =0x4bf00000
    msr ttbr0_el2, x0
    dsb sy
    isb
    tlbi alle2
    dsb sy
    isb
    mrs x0, sctlr_el2
    orr x0, x0, #1
    orr x0, x0, #4
    msr sctlr_el2, x0
    isb
    ret
.global compact_cache_finish
compact_cache_finish:
    cache_range civac, 0x48000000, (0x48000000+COMPACT_RAW)
    cache_range civac, 0x50000000, (0x50000000+COMPACT_PACKED)
    cache_range civac, 0x4bf00000, 0x4c000000
    mrs x0, sctlr_el2
    bic x0, x0, #1
    bic x0, x0, #4
    msr sctlr_el2, x0
    isb
    tlbi alle2
    dsb sy
    isb
    ldr x0, =0x2d800
    mov w1, #3
    str w1, [x0, #68]
    mrs x1, cntpct_el0
    str x1, [x0, #56]
    ret
