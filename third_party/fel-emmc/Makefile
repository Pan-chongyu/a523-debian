# Makefile -- Build bare-metal FEL tools for Allwinner A523/T527
#
# Copyright (c) 2026 Contributors
# SPDX-License-Identifier: MIT
#
# These tools run from SRAM via FEL mode (no OS, no DRAM).
# Cross-compiled for ARMv7-A (AArch32, Cortex-A55 compat).
#
# Usage:
#   make                     Build all tools (requires arm-none-eabi-gcc)
#   make docker              Build all tools via Docker (no local toolchain needed)
#   make fel-emmc.bin         Build just the eMMC driver
#   make clean               Remove build artifacts

CROSS_COMPILE ?= arm-none-eabi-
CC      = $(CROSS_COMPILE)gcc
OBJCOPY = $(CROSS_COMPILE)objcopy

CFLAGS  = -nostdlib -nostartfiles -ffreestanding -O2 -march=armv7-a -Wall
LDFLAGS = -Wl,-Ttext=0x20000

# Default speed mode for eMMC driver (1-bit safe mode)
EMMC_DEFS = -DSPEED_1BIT_FAST

# All bare-metal C tools
TOOLS = fel-emmc fel-pmic-poweroff fel-i2c-scan fel-regdump
BINS  = $(addsuffix .bin, $(TOOLS))
ELFS  = $(addsuffix .elf, $(TOOLS))

.PHONY: all clean docker

all: $(BINS)

# Generic rule: .c -> .elf -> .bin
%.elf: %.c
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $< $(if $(findstring fel-emmc,$*),$(EMMC_DEFS))

%.bin: %.elf
	$(OBJCOPY) -O binary $< $@
	@echo "  Built $@ ($(shell stat -f%z $@ 2>/dev/null || stat -c%s $@ 2>/dev/null) bytes)"

# Docker build -- no local ARM toolchain required
docker:
	docker run --rm -v "$(CURDIR):/work" -w /work debian:bookworm bash -c '\
		apt-get update -qq >/dev/null 2>&1 && \
		apt-get install -y -qq gcc-arm-none-eabi >/dev/null 2>&1 && \
		make all'

clean:
	rm -f $(BINS) $(ELFS)

# Print help
help:
	@echo "Targets:"
	@echo "  all       Build all .bin files (default)"
	@echo "  docker    Build via Docker (no local toolchain needed)"
	@echo "  clean     Remove build artifacts"
	@echo ""
	@echo "Individual tools:"
	@echo "  fel-emmc.bin          eMMC read/write driver"
	@echo "  fel-pmic-poweroff.bin AXP717 PMIC cold shutdown"
	@echo "  fel-i2c-scan.bin      R_TWI I2C bus scanner"
	@echo "  fel-regdump.bin       DRAM register dump"
	@echo ""
	@echo "Speed modes for fel-emmc (set via EMMC_DEFS):"
	@echo "  make EMMC_DEFS='-DSPEED_1BIT_FAST'  12MHz/1-bit (default, safest)"
	@echo "  make EMMC_DEFS='-DSPEED_4BIT_FAST'  12MHz/4-bit (faster)"
	@echo "  make EMMC_DEFS='-DSPEED_8BIT_FAST'  12MHz/8-bit (fastest)"
