# Debian for TZX P30 A523

[简体中文](README.zh-CN.md) · [English guide](docs/en/FLASHING.md) · [日本語](docs/ja/FLASHING.md) · [Español](docs/es/FLASHING.md)

Board support, a complete Debian ARM64/XFCE image, and a verified FEL-to-USB installer for **TZX P30A523_20T5G, LPDDR3 4 GiB, UEM 128 GB eMMC**. This image is board specific. An A523 processor alone does not establish compatibility.

**Experimental public release:** the original tablet runs the adapted desktop. The distributable image resets credentials and identities and changes the eMMC guard from one serial number to a product-family prefix. These release-specific changes have automated checks, but a complete flash of the public image has not yet been verified on hardware. Keep a working FEL recovery path.

## Download and flash

**Windows:** download the [standalone EXE](https://github.com/Pan-chongyu/a523-debian/releases/download/flasher-v0.2.0/A523-Debian-Flasher-v0.2.0-Windows-x64.exe), double-click it, verify the board and erasure confirmation, then click **Start flashing**. No Python installation is needed. The graphical app supports Chinese, English, Japanese and Spanish, with download progress and verified writes. [Standalone app details](docs/WINDOWS-APP.md).

**Linux:** download the script ZIP from the [image Release](https://github.com/Pan-chongyu/a523-debian/releases/tag/v0.1.0-20261114), install Python, venv, curl and libusb, then run `sudo ./flash.sh --lang en`. The original Windows Python/`flash.cmd` workflow remains available. Both tools download and verify the same image.

**Flashing replaces all existing tablet eMMC data.** Read the [full instructions](docs/en/FLASHING.md) before confirming. FEL driver installation and entering FEL require user action; a tool cannot automate physical buttons on an unbootable tablet. No arbitrary disk number is accepted.

Initial local account: **debian / debian**. Root is locked; SSH is disabled. Change the password before enabling remote access. The first boot expands the root partition filesystem to the eMMC capacity.

## Adaptation status

| Component | Original-unit qualification / release behavior |
|---|---|
| Display | JD9365, 800×1280 DSI; default right landscape 1280×800; brightness and blank/resume tested |
| Early splash | User-provided star-cat image; released image about 7.8 s; [original-unit optimization measured 5.9 s](docs/BOOT-SPLASH-SPEED.md), not yet in the image assets |
| Boot console | [Real boot logs and continuous display handoff](docs/BOOT-CONSOLE.md), owner-confirmed on the original tablet; research update only |
| Touch | GSL3670; rotation and multitouch tested by the owner |
| CPU | All eight cores; performance policy, 1416 / 1800 MHz cluster limits |
| GPU | Native Panfrost desktop acceleration; requested minimum 600 MHz; [OpenCL/WebGL API add-on](docs/GPU-API.md) available separately; no hardware Vulkan |
| Storage | HS200 at 100 MHz; **HS400 is not qualified or enabled** |
| Memory | 4 GiB LPDDR3; 2 GiB zram |
| Audio / buttons | Owner confirmed speaker sound, volume keys and power menu; microphone measurements exist |
| Connectivity | AIC8800D80 Wi-Fi/Bluetooth driver integration; USB network and serial |
| Power | Reboot and power-off tested on the original unit; thermal and fault guards retained |
| Not complete | Cameras, system suspend, headphone and Bluetooth-audio end-to-end tests, other board variants |

No browser preloading is enabled. Performance mode does not bypass thermal protections or certify higher clocks.

The [startup scheduling update](docs/BOOT-STARTUP.md) reduced the original unit's last desktop process creation time from 25.48 to 21.73/21.64 seconds after Linux start, with two reboot and mixed-load passes. It enables HS200 earlier, overlaps the unchanged RAM check and removes redundant waits. The first image remains about 5.9 seconds on its hardware counter; Bluetooth initializes in the background. This research update does not replace the image or flasher Release assets.

The [compact-kernel boot update](docs/BOOT-COMPACT.md) further reduces payload reads/CRC to 2.22 / 2.22 seconds and desktop process creation to 19.83 / 19.96 seconds after Linux start, with two full reboot/load passes. Source and measurements are published; Release assets remain unchanged.

The [GPU API update](docs/GPU-API.md) adds Rusticl OpenCL 3.0, selected OpenCL C 3.0 features, SPIR-V input tests and persistent health recording. Install it separately after the original image; the original image/flasher assets have not been replaced. See the update Release for measured stability results and the exact supported features.

## Sources and licensing

See [BUILD.md](docs/BUILD.md), [THIRD_PARTY.md](THIRD_PARTY.md), [LICENSE](LICENSE) and [release validation](docs/VALIDATION.md). Release assets contain the corresponding modified kernel, firmware-loader and module sources, the sanitized system template and package source inventory. `research/` preserves development sources; many scripts have historical local paths and are not installation entry points.

This is an independently adapted Debian system, not an official Debian hardware image. Debian packages retain their own licenses and `/usr/share/doc/*/copyright`. The vendor DRAM training library and some wireless firmware are binary components: their source is unavailable here, and they are explicitly identified rather than described as open source.

![Boot artwork preview](assets/boot-preview.png)
