# Components and source availability

| Component | Origin / license / corresponding source |
|---|---|
| Linux 7.3.3 with TZX changes | GPL-2.0-only plus per-file SPDX terms; full modified tree and configuration in `a523-corresponding-sources-*.tar.gz` |
| External TZX modules and Panfrost changes | Linux-derived GPL modules; full source directories in that archive under `modules/` |
| FEL eMMC helper | [A523-root](https://github.com/chrislennon/A523-root), MIT; exact helper source in `third_party/fel-emmc/` |
| SRAM/DRAM loader foundations | [SyterKit](https://github.com/YuzukiHD/SyterKit), commit `7f539e17762639589897db835e58dd638b2bea80`, GPL-2.0; source and license in the source archive |
| DRAM training | SyterKit `soc/sun55iw3/lib/libdram.a`, supplied upstream as a binary library; training source is unavailable here. Retain upstream distribution notices. This component is not represented as source-complete |
| EL3 firmware / BL31 | Adapted Arm Trusted Firmware source in `trusted-firmware-a/`, BSD-3-Clause and included component licenses; retain `docs/license.rst` and per-file notices |
| AIC8800 driver | [radxa-pkg/aic8800](https://github.com/radxa-pkg/aic8800), commit `b6e136a9fe30a4babf0dde5ba9d02313e1c99c30`; root license GPL-3.0, driver files may specify GPL-2.0. Both original and ported sources are included |
| AIC8800D80 firmware | Binary files distributed by the same upstream repository/package; preserve original notices and source origin. Wireless firmware source is unavailable here |
| GSL touch firmware | Upstream [onitake/gsl-firmware](https://github.com/onitake/gsl-firmware) / supplied Seeed firmware distribution; Apache-2.0 license copy in LICENSES. Firmware is controller data, not host driver source |
| Debian packages | Exact installed binary/source versions in `board/packages.tsv`; package notices in `/usr/share/doc/*/copyright`; source acquisition tool in `tools/fetch_debian_sources.py` |
| Boot artwork | Supplied by the device owner. Separate artwork reuse rights are not asserted; see LICENSE |
| Windows flasher runtime | CPython (PSF), Tcl/Tk (Tcl/Tk terms), PyUSB 1.3.1 (BSD-3-Clause), pySerial 3.5 (BSD), importlib_resources (Apache-2.0), libusb-package 1.0.26.4 (Apache-2.0) and its libusb 1.0.26 DLL (LGPL-2.1-or-later). Notices and matching dependency sources accompany the executable Release; DLL loading remains dynamic. PyInstaller 6.12.0 uses its bootloader distribution exception. Build recipe: `packaging/build_windows.py` |

Release images include executable binaries and firmware. Publishing this project does not make unavailable vendor source available. The repo's MIT license applies only to the release tooling and documentation listed in LICENSE.

`research/` includes historical experiments and recovery helpers. Their presence is not a statement that every attempted driver is installed or validated. The image's module inventory and the validation report identify the actual release content.
