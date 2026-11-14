# Flashing guide

[简体中文](../zh-CN/FLASHING.md) · [日本語](../ja/FLASHING.md) · [Español](../es/FLASHING.md)

## Hardware and release status

Use only **TZX P30A523_20T5G**, marking `TZX P30A523-56T5G-240321`, A523/sun55iw3p1, **4 GiB LPDDR3**, **128 GB UEM eMMC** (244318208 × 512-byte sectors), and JL_M1010WX92_M4027 800×1280 DSI display. The installer also checks FEL SoC ID `0x00189000` and CID product prefix `3e01ff55454d2020`. These checks do not identify every board component; physically verify the PCB.

This is an **experimental prerelease**. The original tablet was qualified, but a complete reflash of the sanitized public image has not been hardware verified. **All existing tablet data is replaced, without automatic backup.** This is system replacement, not secure erasure of every eMMC sector. Use reliable power and a data-capable USB cable.

## Windows

1. Download `a523-debian-flasher-v0.1.0-20261114.zip` from [Releases](https://github.com/Pan-chongyu/a523-debian/releases), then extract the entire archive.
2. Install Python 3.10+ including Python Launcher (`py`). Internet access is required for dependencies and the roughly gigabyte-scale image; reserve at least 8 GB on the host.
3. Enter **FEL** using the button procedure already verified for your tablet. Connect exactly one tablet. Confirm USB **1f3a:efe8** in Device Manager. This project does not assume a universal button combination.
4. If necessary, use [Zadig](https://zadig.akeo.ie/) to install **WinUSB for that FEL device only**. Do not replace the drivers of the later USB-storage, serial or network interfaces.
5. Double-click **flash.cmd**, accept administrator elevation, verify the displayed hardware profile, and type **FLASH**. Downloads, SHA256 checks, temporary installer bootstrap, disk selection, writing, block readback and GPT expansion are automatic.
6. Wait for completion. The first boot expands the root filesystem. If automatic reboot is unavailable, safely disconnect USB and restart using Power. Keep power stable throughout.

Language selection and a download-only check:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\flash.ps1 -Language en
powershell -NoProfile -ExecutionPolicy Bypass -File .\flash.ps1 -Language en -DryRun
```

Elevation permits access to the physical USB disk. The tool accepts no arbitrary disk number: capacity and a fresh random session nonce must match. Windows boot/system disks are excluded. Dry run opens neither USB devices nor disks.

## Linux

```sh
sudo apt install python3 python3-venv curl libusb-1.0-0
chmod +x flash.sh
sudo ./flash.sh --lang en
```

Enter FEL first and connect one target. Unmount any tablet partitions automatically mounted by the desktop. `sudo ./flash.sh --lang en --dry-run` checks release files without writing. macOS raw-disk installation is not implemented.

## First login

Local credentials: **debian / debian**. The desktop automatically logs in and defaults to right landscape. Run `passwd` immediately. Root is locked and SSH is disabled. After changing the password, enable remote management if needed:

```sh
sudo systemctl enable --now ssh
```

For USB networking, configure the host USB interface to `192.168.77.1`, mask `255.255.255.252`, no gateway; the tablet is `192.168.77.2`. Connect with `ssh debian@192.168.77.2`. Machine identity and SSH host keys are generated for each installation. Wi-Fi credentials, browser profiles and the owner's keys are not distributed.

Performance mode, native Panfrost, HS200 and 2 GiB zram are configured; browser preloading is disabled. Thermal protections remain active. Read the homepage for unqualified features.

## Recovery

Rerun interrupted downloads: `.part` files resume and SHA256 is checked. For a checksum failure, remove that cached asset and download again; do not disable verification. Default cache: `~/.cache/a523-debian/v0.1.0-20261114` (the account running the elevated process on Windows).

If FEL is absent, check the data cable, `1f3a:efe8`, WinUSB, and other connected FEL devices. If the USB installer does not appear within 180 seconds or writing fails, force power off, re-enter FEL with your verified procedure, and rerun. Image writing restarts from the beginning. The temporary installer modifies user-area boot locations; after a failed attempt the previous OS may no longer boot.

Do not bypass CID/capacity checks. eMMC boot0, boot1, RPMB and fuses are not written. Recovery still requires a working FEL path and correct DRAM initialization. For issues, provide the PCB marking, release and failing stage, with passwords, keys and eMMC serial numbers removed from logs.
