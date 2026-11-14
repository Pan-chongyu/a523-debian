/* SPDX-License-Identifier: MIT */
.syntax unified
.arm
.section .text.entry,"ax"
.global _start
_start:
    /* Preserve the boot ROM context before masking interrupts or replacing
     * its stack. The original loader jumped back to ROM with our own SP. */
    ldr r0, =retry_boot_context
    str sp, [r0]
    str lr, [r0, #4]
    mrs r1, cpsr
    str r1, [r0, #8]
    mrc p15, 0, r1, c1, c0, 0
    str r1, [r0, #12]
    mrc p15, 0, r1, c12, c0, 0
    str r1, [r0, #16]
    mrs r1, sp_irq
    str r1, [r0, #20]
    mrc p15, 0, r1, c12, c12, 5
    str r1, [r0, #32]
    tst r1, #1
    beq 3f
    mrc p15, 0, r1, c4, c6, 0
    str r1, [r0, #24]
    mrc p15, 0, r1, c12, c12, 7
    str r1, [r0, #28]
3:
    cpsid if
    ldr r0, =__bss_start__
    ldr r1, =__bss_end__
    mov r2, #0
1:  cmp r0, r1
    strlo r2, [r0], #4
    blo 1b
    ldr sp, =0x0002d000
    bl dram_probe
    ldr r0, =retry_boot_context
    ldr r1, [r0, #16]
    mcr p15, 0, r1, c12, c0, 0
    ldr r1, [r0, #12]
    dsb sy
    mcr p15, 0, r1, c1, c0, 0
    isb
    ldr r1, [r0, #20]
    msr sp_irq, r1
    ldr r1, [r0, #32]
    tst r1, #1
    beq 4f
    ldr r1, [r0, #24]
    mcr p15, 0, r1, c4, c6, 0
    ldr r1, [r0, #28]
    mcr p15, 0, r1, c12, c12, 7
4:
    ldr sp, [r0]
    ldr lr, [r0, #4]
    ldr r1, [r0, #8]
    dsb sy
    msr cpsr_fc, r1
    isb
    mov r0, #0x20
    bx r0
.ltorg
.section .data
.align 2
.global retry_boot_context
retry_boot_context:
    .space 36
