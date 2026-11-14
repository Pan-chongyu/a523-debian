/* SPDX-License-Identifier: MIT
 * ARM RMR transition used by the upstream sunxi boot0/rmr_switch code.
 */
.syntax unified
.arm
.text
.global enter_arm64
enter_arm64:
    ldr r1, =0x08000040
    str r0, [r1]
    mov r0, #0
    str r0, [r1, #4]
    ldr r0, =24000000
    mcr p15, 0, r0, c14, c0, 0
    dsb sy
    isb
    mrc p15, 0, r0, c12, c0, 2
    orr r0, r0, #3
    mcr p15, 0, r0, c12, c0, 2
    isb
1:  wfi
    b 1b
.ltorg
