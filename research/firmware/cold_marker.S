/* SPDX-License-Identifier: MIT
 * First cold-boot test: record entry, then enter the ROM FEL entry at 0x20.
 * No DRAM, PMIC, storage, OTP or fuse access.
 */
.syntax unified
.arm
.section .text.entry,"ax"
.global _start
_start:
    ldr r0, =0x07090110
    ldr r1, =0xa5231101
    str r1, [r0]
    mrs r1, cpsr
    str r1, [r0, #4]
    dsb sy
    isb
    mov r0, #0x20
    bx r0
.ltorg
