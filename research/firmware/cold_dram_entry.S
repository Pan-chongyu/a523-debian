/* SPDX-License-Identifier: MIT */
.syntax unified
.arm
.section .text.entry,"ax"
.global _start
_start:
    cpsid if
#ifdef CHAIN_BOOT
    ldr r0, =cold_vectors
    mcr p15, 0, r0, c12, c0, 0
    isb
#endif
    ldr r0, =__bss_start__
    ldr r1, =__bss_end__
    mov r2, #0
1:  cmp r0, r1
    strlo r2, [r0], #4
    blo 1b
#ifdef CHAIN_BOOT
    ldr sp, =0x0002d000
#else
    ldr sp, =0x0005f000
#endif
    bl dram_probe
    dsb sy
    isb
    mov r0, #0x20
    bx r0
.ltorg

#ifdef CHAIN_BOOT
/* SRAM exception records distinguish a CPU abort from a stalled PIO loop. */
.align 5
cold_vectors:
    b cold_exception
    b cold_undef
    b cold_svc
    b cold_prefetch_abort
    b cold_data_abort
    b cold_exception
    b cold_irq
    b cold_fiq
cold_undef:
    mov r4, #1
    b cold_fault
cold_svc:
    mov r4, #2
    b cold_fault
cold_prefetch_abort:
    mov r4, #3
    b cold_fault
cold_data_abort:
    mov r4, #4
    b cold_fault
cold_irq:
    mov r4, #6
    b cold_fault
cold_fiq:
    mov r4, #7
    b cold_fault
cold_exception:
    mov r4, #0
cold_fault:
    ldr r0, =0x07090100
    mrc p15, 0, r1, c5, c0, 0
    str r1, [r0]
    mrc p15, 0, r1, c6, c0, 0
    str r1, [r0, #4]
    mrc p15, 0, r1, c5, c0, 1
    str r1, [r0, #8]
    mrc p15, 0, r1, c6, c0, 2
    str r1, [r0, #12]
    ldr r1, =0xa52346e0
    orr r1, r1, r4
    str r1, [r0, #16]
    str lr, [r0, #20]
    ldr r1, =0xa52322ee
    str r1, [r0, #24]
    mrs r1, spsr
    str r1, [r0, #28]
    dsb sy
    ldr r0, =0x02050008
    ldr r1, =0x16aa0001
    str r1, [r0]
    dsb sy
2:  wfi
    b 2b
.ltorg
#endif
