# TZX P30 A523 平板 Debian 适配

[English](README.md) · [中文刷机教程](docs/zh-CN/FLASHING.md) · [日本語](docs/ja/FLASHING.md) · [Español](docs/es/FLASHING.md)

提供板级适配源码、完整 Debian ARM64/XFCE 镜像、一键刷机工具和四种语言教程。**仅面向 TZX P30A523_20T5G、LPDDR3 4 GiB、UEM 128 GB eMMC 这一硬件组合**，不能凭 A523 芯片型号通刷。

这是**实验性预发布**。原机的桌面、触摸、扬声器、实体按键、亮度、横屏和重启已有验证；公开镜像额外进行了账号脱敏、身份重置和 eMMC 产品前缀适配，尚未完成整包实机重刷验证。请保留 FEL 恢复方式。

Windows 推荐直接下载 [独立刷机程序 EXE](https://github.com/Pan-chongyu/a523-debian/releases/download/flasher-v0.2.0/A523-Debian-Flasher-v0.2.0-Windows-x64.exe)：**双击打开，无需安装 Python**，勾选板型及清空确认后点击“开始刷机”。提供中文、英文、日文、西班牙文界面，自动下载、校验、写入并读回检查。[独立程序说明](docs/WINDOWS-APP.md)。

Linux 使用 [镜像 Release](https://github.com/Pan-chongyu/a523-debian/releases/tag/v0.1.0-20261114) 的脚本 ZIP，运行 `sudo ./flash.sh --lang zh-CN`；Windows 也保留 Python 3.10+ 加 `flash.cmd` 的脚本方式。首次进入 FEL 和安装 USB 驱动需要手动操作。开始前请阅读[完整教程](docs/zh-CN/FLASHING.md)。

**刷机会替换平板 eMMC 上的全部现有数据。** 初始本地账号为 **debian / debian**，root 已锁定，SSH 默认关闭；启用远程访问前请修改密码。

默认向右横屏 1280×800，使用星空猫开屏图；CPU 为性能模式，两个集群上限 1416/1800 MHz，GPU 原生 Panfrost 加速并请求最低 600 MHz，eMMC 为 HS200 100 MHz，zram 为 2 GiB。不预加载浏览器，保留温控和故障保护。当前图像引导器计时约 7.8 秒，不保证所有启动条件均为此前彩条阶段的约 2 秒。

[开屏提速研究更新](docs/zh-CN/BOOT-SPLASH-SPEED.md)已在原机测得约 5.9 秒，两次重启与联合负载通过。本次公开源码和实测记录，尚未替换上述镜像或刷机 EXE 的 Release 文件；计数器时间与实体按键秒表时间不同。

[启动流程精简](docs/zh-CN/BOOT-STARTUP.md)进一步将原机桌面进程全部创建时间从内核启动后 25.48 秒缩短到 21.73/21.64 秒，提前启用 HS200、并行内存检查并去除重复等待，两次重启与联合负载通过。首次图片计数仍约 5.9 秒，蓝牙在后台初始化；公开镜像和 EXE 文件未替换。

[GPU API 补充更新](docs/zh-CN/GPU-API.md)增加 Rusticl OpenCL 3.0、选定 OpenCL C 3.0 功能、SPIR-V 输入测试和持久健康记录，已验证 WebGL 1/2 使用真实 GPU。原镜像与刷机工具内容未变，新刷机后需另装本补充包；实际持续测试结果见更新 Release。

**尚未完整适配或验证：** HS400、摄像头、整机休眠、耳机与蓝牙音频端到端，以及其他内存、屏幕或 eMMC 的变体。当前开源驱动栈不提供这块 Mali-G57 的合格 Vulkan 硬件实现。

源码构建见 [BUILD.md](docs/BUILD.md)，测试范围见 [VALIDATION.md](docs/VALIDATION.md)。开源及第三方许可见 [LICENSE](LICENSE) 和 [THIRD_PARTY.md](THIRD_PARTY.md)。发布包包含修改后的内核和模块源码、镜像构建工具及脱敏模板；DRAM 训练库与部分无线固件属于无源码的二进制组件，已单独说明。它不是 Debian 官方硬件镜像。
