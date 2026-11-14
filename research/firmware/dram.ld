ENTRY(_start)
SECTIONS {
  . = 0x44000;
  .text : { *(.text.entry) *(.text*) }
  .rodata : { *(.rodata*) }
  .data : { *(.data*) }
  .bss : { __bss_start__ = .; *(.bss*) *(COMMON) __bss_end__ = .; }
  /DISCARD/ : { *(.comment*) *(.note*) *(.ARM.exidx*) *(.ARM.extab*) }
  ASSERT(. < 0x5d000, "DRAM payload exceeds SRAM code window")
}
