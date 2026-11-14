# Debian for TZX P30 A523

[简体中文](README.zh-CN.md) · [English guide](docs/en/FLASHING.md) · [日本語](docs/ja/FLASHING.md) · [Español](docs/es/FLASHING.md)

Board support, a complete Debian ARM64/XFCE image, and a verified FEL-to-USB installer for **TZX P30A523_20T5G, LPDDR3 4 GiB, UEM 128 GB eMMC**. This image is board specific. An A523 processor alone does not establish compatibility.

**Experimental public release:** the original tablet runs the adapted desktop. The distributable image resets credentials and identities and changes the eMMC guard from one serial number to a product-family prefix. These release-specific changes have automated checks, but a complete flash of the public image has not yet been verified on hardware. Keep a working FEL recovery path.

## Download and flash

Download `a523-debian-flasher-v0.1.0-20261114.zip` from [Releases](https://github.com/Pan-chongyu/a523-debian/releases). Extract it; on Windows, install Python 3.10+ and double-click **flash.cmd**. On Linux, install Python, venv, curl and libusb, then run `sudo ./flash.sh --lang en`. The tool downloads the matching complete image and verifies hashes.

**Flashing replaces all existing tablet eMMC data.** Read the [full instructions](docs/en/FLASHING.md) before entering `FLASH`. FEL driver installation and entering FEL require user action; a tool cannot automate physical buttons on an unbootable tablet. No arbitrary disk number is accepted.

Initial local account: **debian / debian**. Root is locked; SSH is disabled. Change the password before enabling remote access. The first boot expands the root partition filesystem to the eMMC capacity.

## Adaptation status

| Component | Original-unit qualification / release behavior |
|---|---|
| Display | JD9365, 800×1280 DSI; default right landscape 1280×800; brightness and blank/resume tested |
| Early splash | User-provided star-cat image, then desktop; current logo loader counter about 7.8 s; timing varies |
| Touch | GSL3670; rotation and multitouch tested by the owner |
| CPU | All eight cores; performance policy, 1416 / 1800 MHz cluster limits |
| GPU | Native Panfrost desktop acceleration; requested minimum 600 MHz; no Vulkan/OpenCL qualification |
| Storage | HS200 at 100 MHz; **HS400 is not qualified or enabled** |
| Memory | 4 GiB LPDDR3; 2 GiB zram |
| Audio / buttons | Owner confirmed speaker sound, volume keys and power menu; microphone measurements exist |
| Connectivity | AIC8800D80 Wi-Fi/Bluetooth driver integration; USB network and serial |
| Power | Reboot and power-off tested on the original unit; thermal and fault guards retained |
| Not complete | Cameras, system suspend, headphone and Bluetooth-audio end-to-end tests, other board variants |

No browser preloading is enabled. Performance mode does not bypass thermal protections or certify higher clocks.

## Sources and licensing

See [BUILD.md](docs/BUILD.md), [THIRD_PARTY.md](THIRD_PARTY.md), [LICENSE](LICENSE) and [release validation](docs/VALIDATION.md). Release assets contain the corresponding modified kernel, firmware-loader and module sources, the sanitized system template and package source inventory. `research/` preserves development sources; many scripts have historical local paths and are not installation entry points.

This is an independently adapted Debian system, not an official Debian hardware image. Debian packages retain their own licenses and `/usr/share/doc/*/copyright`. The vendor DRAM training library and some wireless firmware are binary components: their source is unavailable here, and they are explicitly identified rather than described as open source.

![Boot artwork preview](assets/boot-preview.png)
