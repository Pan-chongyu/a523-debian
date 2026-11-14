# GPU API 与稳定性更新 v0.3.0

[English](../GPU-API.md) · [日本語](../ja/GPU-API.md) · [Español](../es/GPU-API.md)

本补充包面向已安装适配系统的 **TZX P30A523_20T5G / Mali-G57 / LPDDR3 4 GiB / UEM 128 GB**。增加 GPU OpenCL、API 校验和持久健康记录，保留原有内核、引导、分区、屏幕配置及温控与故障保护。

**原镜像 `v0.1.0-20261114` 和刷机工具 `flasher-v0.2.0` 的内容未变，新刷机后需要再安装本补充包。** 本次在原机运行系统上验证，不能据此宣称脱敏后的公开镜像已经通过整包实机重刷。

## 已验证的 API

| API | 实际状态 |
|---|---|
| EGL / OpenGL | EGL 1.5；OpenGL 3.1 / GLSL 1.40；原生 Panfrost；64 帧全量回读，校验 528,320 个像素 |
| OpenGL ES | GLES 3.1 / ESSL 3.10；着色器、像素回读、计算着色器及同步校验 |
| WebGL 1 / 2 | Firefox ESR 使用 Mali-G57；每种 API 校验 120 帧，浏览器正常退出 |
| OpenCL | Rusticl 识别真实 GPU，设备版本 3.0；默认 OpenCL C 查询为 1.2；显式 CL3.0 编译与选定可选功能通过 |
| OpenCL SPIR-V | SPIR-V 1.0 程序执行，65,536 个结果全部正确；属于 OpenCL 输入能力 |
| Vulkan | 当前开源驱动栈不提供这块 G57 / Valhall v9 的合格硬件实现；未安装软件 Vulkan 冒充加速 |

边界依据 [Mesa 硬件支持表](https://docs.mesa3d.org/drivers/panfrost.html) 和 [Rusticl 说明](https://docs.mesa3d.org/rusticl.html)。只启用 `panfrost`，不伪造 API 版本，也不使用 CPU OpenCL 或 llvmpipe/lavapipe 通过测试。

OpenCL 已实测整数、浮点、非整工作组长度、局部内存同步与归约、事件计时、二维图像、64 位整数、32 位原子操作、读写图像及跨队列事件依赖。**这些是选定功能测试，不等同于完整 Khronos CTS 或新的认证。** 当前设备不公布 FP16、FP64、SVM 和 CL/GL 对象共享能力，其他可选功能未据此承诺。

Firefox 向网页返回的 GPU 型号可能被隐私机制简化为“Mali-G51, or similar”；测试同时核对 Firefox 内部的真实 Mali-G57 渲染器，保留浏览器隐私默认值。

解压后还可运行 `python3 gpu/desktop_gl_check.py`，独立验证桌面 OpenGL；或运行 `python3 gpu/repeat_extended.py --cycles 100 --output new-result.json`，反复验证 OpenCL C 3.0 与 SPIR-V。后者不替代带故障与温度检查的混合持续测试。

## 安装

从 [GPU API Release](https://github.com/Pan-chongyu/a523-debian/releases/tag/gpu-api-v0.3.0) 下载 `a523-gpu-api-v0.3.0.tar.gz` 和 `SHA256SUMS`。在**平板的 Debian 系统内**运行：

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

压缩包包含全部 11 个新增 Debian 依赖，可离线安装。安装器检查板型、eMMC 容量、原生 Panfrost 配置、Mesa 版本和包校验和；拒绝依赖升级、移除以及覆盖不属于本补充包的文件。激活前以普通桌面账号执行 GPU 验收，不清空 eMMC、不写引导区。

离线依赖集匹配公开镜像中的原始版本。如果系统后来已自行升级而不兼容，安装会停止。联网方式为 `sudo python3 gpu/install.py`，同样锁定目标版本并拒绝替换依赖。仅当确切依赖已装齐时使用 `--skip-apt`。

重启后，登录 shell、X11 应用和新的 systemd 用户会话会获得 OpenCL 配置。以下启动器无需等待重启即可使用，也适用于非交互 SSH：

```sh
tzx-opencl clinfo -l
tzx-opencl 你的OpenCL程序
DISPLAY=:0 tzx-gpu-check info
sudo tzx-gpu-check webgl --output /var/lib/tzx-gpu-api-tests/webgl.json
```

WebGL 检查会打开临时 Firefox 窗口，以独立临时配置测试，再正常退出；不读取原浏览器个人配置。需要正在运行的 XFCE 桌面。

## 持续测试与故障记录

Release 的 `gpu-api-validation.json` 和采样记录提供本次实际持续时间、循环数、校验量、峰值温度及重启验证。有限时长通过不能保证永久稳定，也不能消除历史开发过程中出现过的故障及尚未查明原因的浏览器启动 GPU 错误。

复测一小时：

```sh
sudo systemd-run --unit=tzx-gpu-api-soak \
  --property=MemoryMax=1600M --property=RuntimeMaxSec=3950 \
  /usr/local/bin/tzx-gpu-check soak --duration 3600 \
  --output /var/lib/tzx-gpu-api-tests/new-run
sudo journalctl -fu tzx-gpu-api-soak
```

每次使用新的目录和服务名。测试并行运行 OpenCL、GLES 计算、像素回读、六种 glmark2 场景，以及 512 MiB 匿名内存全量哈希校验。遇到错值、超时、内核/存储/显示错误、桌面重启、失败服务或达到 85°C 就停止；不写原始存储。检查五路物理温度及板级聚合温度。结果见 `result.json`，分享原始内核日志前请脱敏。

新增 `tzx-gpu-api-health.service` 每 10 秒采样，健康状态每 30 秒保存小型记录，最多保留 32 次启动摘要。systemd 看门狗可以重启失去响应的记录进程。发现问题后保留降级记录；上次记录未正常结束，只能说明监测中断，不能单独判断是断电、强制按键还是系统崩溃。它不重置 GPU、不恢复已撤销的性能资格，也不重启桌面。

```sh
systemctl status tzx-gpu-api-health
cat /run/tzx-gpu-api-health.json
sudo cat /var/lib/tzx-gpu-api-health/latest.json
```

原有内核保护继续管理性能限制：GPU 请求最低 600 MHz，热限制可降至 400/200 MHz。`clinfo` 中静态的 `Max clock frequency: 800MHz` **不是当前频率，也不会启用 800 MHz 档位**；实际频率见 `/sys/class/devfreq/1800000.gpu/cur_freq`。持续性能受平板散热条件限制。

## 回退

保留解压目录，运行：

```sh
sudo python3 gpu/install.py --rollback
sudo reboot
```

回退停止并移除本次记录服务，只删除校验和仍匹配的自有文件，保留本地修改、诊断历史和 Debian 软件包；不改变原有性能保护或恢复整盘旧镜像。

依赖版本和 SHA256 位于 `gpu/packages.json`、`board/gpu-api-packages.tsv`。新增五个源码包随 Release 提供；未改动的 Mesa、LLVM 19、ocl-icd 源码仍在原镜像 Release。`board/gpu-api-debian-sources.json` 列出全部八个源码包的确切文件、校验和及资产位置。许可见 [LICENSE](../../LICENSE)。
