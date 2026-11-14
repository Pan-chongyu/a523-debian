# GPU APIs and stability update v0.3.0

[简体中文](zh-CN/GPU-API.md) · [日本語](ja/GPU-API.md) · [Español](es/GPU-API.md)

This is an add-on for the adapted **TZX P30A523_20T5G / Mali-G57 / 4 GiB LPDDR3 / UEM 128 GB** tablet. It adds native Rusticl OpenCL, API tests and persistent health recording. It preserves the qualified kernel, bootloader, partition layout, display settings and thermal/fault controls.

The image and Windows flasher at `v0.1.0-20261114` / `flasher-v0.2.0` remain unchanged. **Install this add-on after flashing that image.** Validation on the original running tablet does not establish that the sanitized public image has passed a complete hardware flash.

## Actual API support

| API | Qualified implementation / boundary |
|---|---|
| EGL / OpenGL | EGL 1.5, OpenGL 3.1 / GLSL 1.40 on Mesa 25.0.7-2+deb13u1, Panfrost |
| OpenGL ES | GLES 3.1 / ESSL 3.10; shader, framebuffer readback and compute SSBO/fence tests |
| WebGL 1 / 2 | Firefox ESR native Mali-G57; 120 shader/pixel checks per API, graceful browser exit |
| OpenCL | Rusticl device reports OpenCL 3.0, GPU type; default OpenCL C query is 1.2; explicit `-cl-std=CL3.0` builds and selected optional features pass |
| OpenCL IL | A reproducible SPIR-V 1.0 kernel executes and all 65,536 results match; this is an OpenCL test |
| Vulkan | **No qualified hardware driver for Mali-G57 / Valhall v9 in this stack.** `vulkaninfo` reports no compatible driver; no software Vulkan is installed |

Mesa's [Panfrost hardware table](https://docs.mesa3d.org/drivers/panfrost.html) lists G57 support for GL/GLES/OpenCL and leaves Vulkan unsupported. [Rusticl](https://docs.mesa3d.org/rusticl.html) requires opting the driver in; this update enables only `panfrost`. No version override, llvmpipe, lavapipe or CPU OpenCL device is used to make these tests pass.

OpenCL tests cover non-multiple work sizes, integer/float32 buffers, local-memory barriers and reduction, event profiling, RGBA image transfers, int64 arithmetic, global uint32 atomics, read/write images and dependencies between in-order and out-of-order queues. This is selected functional qualification, **not a full Khronos CTS run or a new conformance certification**. FP16, FP64, SVM and CL/GL object sharing are not advertised as available by this installed OpenCL device. Other optional features remain unqualified.

Firefox may expose a privacy-sanitized string such as “Mali-G51, or similar” to web pages. The WebGL test checks Firefox's internal Mali-G57 renderer separately and leaves browser privacy defaults enabled.

## Install on the tablet

Download `a523-gpu-api-v0.3.0.tar.gz` and `SHA256SUMS` from the [GPU API Release](https://github.com/Pan-chongyu/a523-debian/releases/tag/gpu-api-v0.3.0). The archive contains all eleven new Debian `.deb` dependencies, installation/test source and these guides.

```sh
sha256sum --ignore-missing -c SHA256SUMS
tar -xzf a523-gpu-api-v0.3.0.tar.gz
cd a523-gpu-api-v0.3.0
sudo python3 gpu/install.py --offline debs
tzx-gpu-check opencl
tzx-gpu-check opencl3
tzx-gpu-check spirv
sudo reboot
```

Run these commands on the tablet's Debian system, not on the Windows host. The installer rejects a different board, eMMC capacity, missing qualified Panfrost configuration, mixed Mesa versions, dependency upgrades/removals, corrupt packages and unowned destination files. Its GPU acceptance checks run as the unprivileged desktop account before configuration is activated. There is no eMMC erase or boot-region write.

The offline package set targets the published image's existing package versions. If dependencies have since changed, installation fails instead of upgrading the graphics stack. An online install is available with `sudo python3 gpu/install.py`; it uses the same exact top-level versions and refuses dependency replacements. `--skip-apt` is for an installation that already has the exact packages.

After reboot, login shells, X11 applications and new systemd user sessions receive `RUSTICL_ENABLE=panfrost`. The `tzx-opencl` launcher works immediately, including from a noninteractive SSH command:

```sh
tzx-opencl clinfo -l
tzx-opencl your-opencl-program
DISPLAY=:0 tzx-gpu-check info
sudo tzx-gpu-check webgl --output /var/lib/tzx-gpu-api-tests/webgl.json
```

The WebGL test opens a temporary Firefox window in the running desktop, uses a separate disposable profile, then exits Firefox gracefully. It does not read the owner's browser profile. Do not run it while performing a fullscreen presentation.

## Sustained testing and diagnostics

The Release's `gpu-api-validation.json` and samples record the actual duration, workload counts, checked values, peak temperatures and reboot verification. A finite soak cannot establish lifetime reliability. Earlier development hangs and a previously unresolved browser-startup GPU fault are not erased by a later clean test.

To repeat an hour-long mixed test without changing performance limits:

```sh
sudo systemd-run --unit=tzx-gpu-api-soak \
  --property=MemoryMax=1600M --property=RuntimeMaxSec=3950 \
  /usr/local/bin/tzx-gpu-check soak --duration 3600 \
  --output /var/lib/tzx-gpu-api-tests/new-run
sudo journalctl -fu tzx-gpu-api-soak
```

Use a new output directory and an unused unit name on every run. The test runs native OpenCL, GLES compute, pixel readback, six glmark2 scenes and a 512 MiB anonymous-RAM checksum worker concurrently. It stops on a mismatched result, deadline, new kernel/storage/display error, changed X server, failed unit or temperature at/above 85 °C. It checks five physical thermal channels and the optional board aggregate. No raw storage is written. Results go to `result.json`; raw kernel logs should be redacted before sharing.

The installed `tzx-gpu-api-health.service` samples health every ten seconds, keeps small boot summaries in `/var/lib/tzx-gpu-api-health/`, persists at most every thirty seconds during healthy operation and retains up to 32 boot summaries. Its systemd watchdog restarts a stalled recorder. It records a sticky degraded state and incomplete monitor endings; those do not identify whether a restart came from power loss, a forced button press or a kernel crash. It does not reset the GPU, renew performance proofs, or restart the desktop.

```sh
systemctl status tzx-gpu-api-health
cat /run/tzx-gpu-api-health.json
sudo cat /var/lib/tzx-gpu-api-health/latest.json
```

The existing kernel leases and temperature/fault guards remain responsible for performance limits. The requested GPU minimum is 600 MHz, with thermal reductions to 400/200 MHz. OpenCL's static `Max clock frequency: 800MHz` capability field is **not the current clock and does not enable an 800 MHz OPP**. Read `/sys/class/devfreq/1800000.gpu/cur_freq` for the actual rate. Sustained speed is constrained by the tablet's cooling.

## Revert

Keep the extracted archive and run:

```sh
sudo python3 gpu/install.py --rollback
sudo reboot
```

Rollback stops/removes this recorder and removes only hash-matching files owned by the add-on. It preserves modified local files, diagnostic history and Debian packages; it does not restore an older disk image or remove the original performance guards.

Binary versions and hashes are in `gpu/packages.json` and `board/gpu-api-packages.tsv`. Corresponding sources for the five additional source packages accompany the Release. The unchanged Mesa, LLVM 19 and ocl-icd sources remain in the original image Release; `board/gpu-api-debian-sources.json` maps all eight source packages to exact assets and upstream hashes. See [LICENSE](../LICENSE) for MIT tooling and GPL GLES-test terms.
