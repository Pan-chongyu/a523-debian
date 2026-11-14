# TZX P30 A523 平板 Debian 适配

[English](README.md) · [中文刷机教程](docs/zh-CN/FLASHING.md) · [日本語](docs/ja/FLASHING.md) · [Español](docs/es/FLASHING.md)

提供板级适配源码、完整 Debian ARM64/XFCE 镜像、一键刷机工具和四种语言教程。**仅面向 TZX P30A523_20T5G、LPDDR3 4 GiB、UEM 128 GB eMMC 这一硬件组合**，不能凭 A523 芯片型号通刷。

这是**实验性预发布**。原机的桌面、触摸、扬声器、实体按键、亮度、横屏和重启已有验证；公开镜像额外进行了账号脱敏、身份重置和 eMMC 产品前缀适配，尚未完成整包实机重刷验证。请保留 FEL 恢复方式。

在 [Releases](https://github.com/Pan-chongyu/a523-debian/releases) 下载并解压 `a523-debian-flasher-v0.1.0-20261114.zip`。Windows 安装 Python 3.10+ 后双击 **flash.cmd**；Linux 使用 `sudo ./flash.sh --lang zh-CN`。工具会自动下载对应镜像并校验。首次进入 FEL 和安装 USB 驱动需要手动操作。开始前请阅读[完整教程](docs/zh-CN/FLASHING.md)。

**刷机会替换平板 eMMC 上的全部现有数据。** 初始本地账号为 **debian / debian**，root 已锁定，SSH 默认关闭；启用远程访问前请修改密码。

默认向右横屏 1280×800，使用星空猫开屏图；CPU 为性能模式，两个集群上限 1416/1800 MHz，GPU 原生 Panfrost 加速并请求最低 600 MHz，eMMC 为 HS200 100 MHz，zram 为 2 GiB。不预加载浏览器，保留温控和故障保护。当前图像引导器计时约 7.8 秒，不保证所有启动条件均为此前彩条阶段的约 2 秒。

**尚未完整适配或验证：** HS400、摄像头、整机休眠、耳机与蓝牙音频端到端、Vulkan/OpenCL，以及其他内存、屏幕或 eMMC 的变体。

源码构建见 [BUILD.md](docs/BUILD.md)，测试范围见 [VALIDATION.md](docs/VALIDATION.md)。开源及第三方许可见 [LICENSE](LICENSE) 和 [THIRD_PARTY.md](THIRD_PARTY.md)。发布包包含修改后的内核和模块源码、镜像构建工具及脱敏模板；DRAM 训练库与部分无线固件属于无源码的二进制组件，已单独说明。它不是 Debian 官方硬件镜像。
