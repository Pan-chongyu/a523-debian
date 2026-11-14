# Building the release

Use an x86-64 Linux build host (Ubuntu 22.04 was used), at least 25 GB free space, and an AArch64 cross toolchain. Build in an isolated directory; never point the image sanitizer at a live root filesystem.

```sh
sudo apt install build-essential gcc-aarch64-linux-gnu binutils-aarch64-linux-gnu \
  gcc-arm-none-eabi bison flex bc libssl-dev libelf-dev dwarves \
  python3 python3-cryptography qemu-user-static cpio device-tree-compiler \
  e2fsprogs dosfstools mtools rsync
```

Download the corresponding-source archive and sanitized-system-template archive from the same Release, verify SHA256SUMS, and extract them into separate directories. The template contains the root filesystem before first boot, not a raw clone of the owner's disk. The archive `a523-corresponding-sources-*.tar.gz` contains the full modified kernel, external module trees, Arm Trusted Firmware, SyterKit, upstream AIC driver, DRAM parameters and exact boot templates used for this release. Vendor training/firmware blobs remain identified as binary components.

## Kernel and modules

```sh
mkdir kernel-build
cp sources/kernel.config kernel-build/.config
make -C sources/linux-7.3.3 O="$PWD/kernel-build" ARCH=arm64 \
  CROSS_COMPILE=aarch64-linux-gnu- olddefconfig
make -C sources/linux-7.3.3 O="$PWD/kernel-build" ARCH=arm64 \
  CROSS_COMPILE=aarch64-linux-gnu- KBUILD_BUILD_VERSION=5 \
  KBUILD_BUILD_USER=builder KBUILD_BUILD_HOST=a523-debian -j"$(nproc)" Image modules
```

The runtime expects `7.3.3-tzx-a523-accel1` and matching symbol CRCs. Do not install the in-tree Panfrost module over the separately qualified external Panfrost module. External sources are under `sources/modules/`. Some historical Makefiles embed original build paths: replace their kernel source/output paths with these directories before `make -C ... O=... M=... modules`. The public HS lease source is `modules/public-emmc-lease/`. Keep board/module guards intact.

`research/tools/build_*.sh` and `research/firmware/install_*.py` document the development steps, including experimental variants; they are not a generic single-pass build pipeline. Runtime scripts from the public template are also published in `runtime/`. The supplied boot templates make rebuilding the public distribution possible without extracting anything from the owner's tablet.

## Boot and image composition

The loader uses an authenticated TOC0, custom SRAM eMMC reader, BL31, kernel, DTB and BusyBox initramfs. No U-Boot boot menu or standard EFI installer is involved. The layout is fixed in sectors: TOC0=256, selected header=4096, artwork=49152, selected bundle=98304, FAT boot=131072, ext4 root=1179648. The disk image has primary and backup GPT. The flasher moves the backup GPT to the real disk end and expands partition 2; initramfs grows ext4 on first boot.

1. Place `Image`, rebuilt `linux-entry.bin`, original boot templates and BL31 in an assets directory. The entry stub must copy the kernel rounded up to 512 bytes (`TZX_IMAGE_COPY_BYTES`) and use `TZX_ALIGNED_KERNEL`; see `research/firmware/linux_entry.S`.
2. Run `image/build_initramfs.sh ORIGINAL_INITRAMFS image/init.public ASSETS`. It emits normal and forced-installer initramfs variants. Extract the original from the template bundle using its item directory at byte 32 (five 24-byte records, LBAs relative to 98304).
3. Run `python3 image/build_boot.py --input BOOT_TEMPLATES --kernel ASSETS/Image --initramfs ASSETS/initramfs.cpio.gz --installer-initramfs ASSETS/installer-initramfs.cpio.gz --key PRIVATE/release-signing.pem --out ASSETS`. A fresh signing key is generated locally; it is never distributed. This requires the exact template hash. The script updates initrd bounds, item CRCs, TOC checksum and signature.
4. Build `tzx-enable-cpub` from `research/firmware/enable_cpub.c`, using the public product-prefix guard rather than the historical original serial. Build `tzx_emmc_hs_lease.ko` and the MIT FEL helper. The release source archive contains the already-portable public versions. The sanitizer consumes these exact assets.
5. Extract the sanitized system template under a path containing `a523-public-release`, for example `/work/a523-public-release/rootfs`. With root permissions run `python3 image/sanitize_rootfs.py --root ROOTFS --assets ASSETS` if updating runtime assets. Do not apply it to `/`. The sanitizer regenerates runtime hash dependencies after modifications.
6. As root run `python3 image/build_disk.py --root ROOTFS --assets ASSETS`. This creates the 5 GiB raw image, compressed image, GPT filesystems, manifest and hashes. Individual Release assets remain below 2 GiB.

For source-level loader rebuilds, start from the source archive's SyterKit and the `research/` boot hooks. The public TOC0 is derived from an exact known template with four CID-comparison instruction changes. The DRAM library is a linked upstream binary, so a wholly source-only rebuild of that vendor component is unavailable. Signing a rebuilt image assumes a device accepting this development TOC0 format; fused secure-boot variants are outside this profile.

## Debian source packages

`board/packages.tsv` records binary version, source package and source version. `tools/fetch_debian_sources.py` uses Debian's archive metadata to retrieve the exact `.dsc` and referenced source tarballs, checking their SHA256. Debian package source terms are retained separately from project licensing. Image releases include acquired source archives and a machine-readable acquisition report; report any missing source immediately via Issues. Original package copyright files remain in the image.

## Checks

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q flasher image tools
```

Read `docs/VALIDATION.md` for the separation between automated release checks and original-unit observations. A successful build or simulator result does not establish a successful hardware flash.
