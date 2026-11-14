/* SPDX-License-Identifier: MIT
 * Retained data-abort context in the existing three RTC words only.
 * u32/u64 are supplied by the kernel or the standalone host harness.
 */
static int tzx_abort_pack(u64 pc, u64 far, u32 esr, unsigned cpu, u32 words[3])
{
    static const u32 prefixes[] = {0x000000, 0xffff00, 0xffff80, 0xfffffd, 0xffffff};
    unsigned prefix = 15, i;
    if (pc < 0xffff800080000000ULL || pc >= 0xffff800081000000ULL ||
        (pc & 3) || (esr >> 26) != 0x25 || cpu >= 8)
        return 0;
    for (i = 0; i < sizeof(prefixes)/sizeof(prefixes[0]); i++)
        if ((far >> 40) == prefixes[i]) prefix = i;
    words[0] = 0xd6000000U | (cpu << 22) | (u32)((pc - 0xffff800080000000ULL) >> 2);
    words[1] = (u32)far;
    words[2] = (u32)((far >> 32) & 0xff) | (prefix << 8) |
        ((esr & 0x3f) << 12) | (((esr >> 26) & 0x3f) << 18) |
        (((esr >> 6) & 0x7f) << 24) | (((esr >> 25) & 1) << 31);
    return 1;
}
