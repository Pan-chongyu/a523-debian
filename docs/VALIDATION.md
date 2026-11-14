# Validation boundaries

The adapted original tablet and a redistributable image are different artifacts. Source and image metadata preserve that distinction.

Original-unit observations include a working landscape desktop, correctly positioned touch, multitouch, brightness changes, display off/on, speaker playback, volume keys, power menu, power-off/on and repeated reboots. Runtime measurements verified CPU performance controls, native Panfrost integration, HS200, zram and temperature monitoring. Some earlier trials caused hangs or unrequested reboots; only the later qualified configuration forms the template. These observations do not establish reliability under every workload.

The public image removes owner data and keys, changes default credentials, disables SSH, generates installation identities, replaces original-serial-only eMMC guards with a product-prefix guard, and uses a rebuilt kernel/initramfs/TOC0. **A complete flash and boot of this public image has not been tested on hardware.** The Release is a prerelease. No running owner installation is erased merely to manufacture a test claim.

Automated checks cover GPT CRCs and boundaries; rejecting malformed manifests and wrong eMMC identity; verifying compressed assets before opening a target; bounded writes and readback; deferring boot-region commit until complete uncompressed verification; filesystem consistency; boot-item CRC and signature checks; staged identity/secret removal; Python/shell syntax and ARM CID-guard behavior. The Release's `validation-report.json` records the checks actually completed and their results. Tests exercise files or emulation, not a physical disk.

Windows and Linux launchers are supplied. FEL driver setup, administrator privileges, entering FEL and occasional physical reboot remain prerequisites. End-to-end Windows WinUSB-to-storage transitions on a fresh installation have not been qualified as part of this release.

Please report device marking, release tag, exact failing stage, host OS and redacted logs. Do not post passwords, private keys, Wi-Fi profiles or full eMMC serial numbers.
