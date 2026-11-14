# Live boot logs and continuous display

[简体中文](zh-CN/BOOT-CONSOLE.md) · [日本語](ja/BOOT-CONSOLE.md) · [Español](es/BOOT-CONSOLE.md)

The original tablet now keeps its screen active through the handoff from the SRAM boot display to Linux DRM. The star-cat image is followed by **actual kernel messages, then the right-landscape XFCE desktop**. The owner confirmed visible live logs, no color bars, no intermediate black screen, and normal desktop/touch operation.

Previously, Linux shut down PWM, DSI and the panel rail before starting its native display driver. Registering the native power-domain provider could also discard the running display state. The new path validates the retained receipts, live timing, scanout address and supply state, then retains the three already-on A523 display domains. The native driver claims clocks and GPIOs without panel reset, supply cycling or backlight blanking, copies the visible log buffer to its DMA32 buffers, and commits normal DE scanout. Cold initialization masks its diagnostic source until the first verified frame; diagnostic color bars and quadrant buffers are removed from that path.

An ARM64 text renderer reads authentic `/dev/kmsg` records and writes a right-rotated reserved boot buffer. When the native display module takes ownership, physical-buffer writes stop and messages continue on VT1 until the desktop starts. This is real kernel output, not simulated progress. The unchanged first SRAM image still appears before userspace can read the log; this update does not claim immediate power-key-to-log output or earlier first light.

Two normal boots completed with 422 / 424 kernel records and native display adoption. The second boot's first log frame was acknowledged by the service at **5.48 seconds after Linux start**; all five desktop processes existed by **20.69 seconds**. These are Linux-relative timestamps, not power-button stopwatch or visual-readiness measurements. Both boots passed 42.51 / 44.06 seconds of concurrent CPU, 2.5 GiB RAM, GPU graphics/compute, 600 hardware-decoded frames and direct-file storage tests. Five real panel sleep/wake cycles passed, including DSI stop/start, DCS sleep-bit transitions and backlight off/on. Display, MMC and IOMMU error counts remained zero, with no failed services. See the [machine-readable report](../reports/boot-console-20261114.json).

CPU performance limits remain 1416/1800 MHz, the GPU requests at least 600 MHz subject to thermal/fault caps, HS200 runs at 100 MHz, and zram remains 2 GiB. Browser preloading remains disabled. The signed loader, artwork asset, compact payload, both GPTs and fallback slot were read back unchanged. Historical parent verification is retained for raw bytes and installed files; the child has its own verifier because the live buffer now contains logs and DE intentionally stays running.

Build the published source against the exact prepared target kernel tree and configuration:

```sh
sh research/tools/build_boot_console.sh KERNEL_SOURCE KERNEL_BUILD OUTPUT_DIRECTORY
```

This entry point was tested: both modules, the text renderer and extracted kernel font matched the installed SHA-256 values. Sources are in [`research/firmware/screen-boot-console`](../research/firmware/screen-boot-console), with the retained-domain provider, handoff script, log reader and renderer beside it. The font comes from the kernel's GPL-licensed `lib/fonts/font_8x16.c`. Building does not install anything. Original-unit validation scripts depend on its exact parent installation and guarded installer; they are research records, not a generic update procedure. No private identity snapshots, credentials or signing keys are published.

The three display domains stay powered; full system suspend is not qualified. This child has not had a new physical power-key or completely unpowered cold-start test. Finite reboot/load tests do not establish long-term reliability. **Image `v0.1.0-20261114` and flasher `v0.2.0` Release assets are unchanged**; this commit publishes source and original-unit results. See [BUILD.md](BUILD.md) and the preceding [compact boot layer](BOOT-COMPACT.md).
