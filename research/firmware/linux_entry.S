/* SPDX-License-Identifier: MIT
 * TF-A enters this at non-secure EL2 with the MMU and data cache disabled.
 * Distinct values at each 256-MiB boundary test for memory address aliasing.
 */
.section .text.entry,"ax"
.global _start
_start:
    msr daifset, #0xf
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
    b.ne failure
    add x9, x9, #1
    b 3b
4:  ldr w11, =0xa5233302
    str w11, [x10]
    str w9, [x10, #4]
#ifdef TZX_ALIGNED_KERNEL
    /* The immutable SRAM loader loads at 0x48080000. Current ARM64 Images
     * have text_offset=0, requiring a 2-MiB-aligned execution address.
     * Move forward into the overlapping lower range while caches are off.
     * image_size includes the BSS; the kernel initializes it after entry.
     */
    ldr x4, =0x48080000
    ldr x5, [x4, #8]
    cbnz x5, failure
    ldr x6, [x4, #16]
    cbz x6, failure
    ldr x7, =0x1f80000
    cmp x6, x7
    b.hi failure
    tst x6, #15
    b.ne failure
    ldr x7, =TZX_IMAGE_COPY_BYTES
    cmp x6, x7
    b.lo failure
    mov x6, x7
    tst x6, #15
    b.ne failure
    ldr x5, =0x48000000
6:  ldp x7, x8, [x4], #16
    stp x7, x8, [x5], #16
    subs x6, x6, #16
    b.ne 6b
    dsb sy
    ic iallu
    dsb sy
    isb
    ldr w11, =0xa5233303
    str w11, [x10]
#endif
    ldr x0, =0x47000000
    mov x1, #0
    mov x2, #0
    mov x3, #0
#ifdef TZX_ALIGNED_KERNEL
    ldr x4, =0x48000000
#else
    ldr x4, =0x48080000
#endif
    dsb sy
    isb
    br x4
failure:
    ldr w11, =0xa52333ee
    str w11, [x10]
    str w9, [x10, #4]
    ldr x10, =0x02050008
    ldr w11, =0x16aa0001
    str w11, [x10]
5:  wfi
    b 5b
.ltorg
