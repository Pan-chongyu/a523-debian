/* SPDX-License-Identifier: MIT */
.syntax unified
.arm
.section .text.entry,"ax"
.global _start
_start:
    push {r4-r11, lr}
    mov r4, sp
    ldr sp, =0x0005f000
    bl dram_probe
    mov sp, r4
    pop {r4-r11, lr}
    bx lr
.ltorg
