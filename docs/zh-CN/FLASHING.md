# 刷机教程

[English](../en/FLASHING.md) · [日本語](../ja/FLASHING.md) · [Español](../es/FLASHING.md)

## 1. 确认硬件

仅支持板号 **TZX P30A523_20T5G**（丝印 `TZX P30A523-56T5G-240321`）、A523/sun55iw3p1、LPDDR3 **4 GiB**、UEM **128 GB** eMMC（244318208 个 512 字节扇区）、JL_M1010WX92_M4027 800×1280 DSI 屏。工具还要求 FEL 芯片 ID `0x00189000`、eMMC CID 产品前缀 `3e01ff55454d2020`。

这些检查不能识别主板上的每个器件，必须人工核对板号。其他 A523 平板不可直接使用。公开版为实验性预发布，完整刷写流程尚未做整包实机验证。

**全部平板数据会被替换；没有自动备份。** 使用可靠的数据线，保持供电和电脑运行。这里是重建系统，不是安全擦除工具；不会对全部剩余扇区做安全清零。

## 2. Windows 一键安装

**推荐独立程序：** 下载 [Windows x64 EXE](https://github.com/Pan-chongyu/a523-debian/releases/download/flasher-v0.2.0/A523-Debian-Flasher-v0.2.0-Windows-x64.exe)，双击并接受管理员权限提示；无需安装 Python。完成下述 FEL / WinUSB 设置后，勾选板型和清空确认，点击“开始刷机”并确认即可。提供下载进度、SHA256 校验和逐块读回验证；“只下载并检查”不接触 USB 或磁盘。[详细说明](../WINDOWS-APP.md)。

以下步骤保留给脚本 ZIP 用户；独立 EXE 用户可跳过第 1、2、5 步，改用上述图形界面：

1. 从 [Releases](https://github.com/Pan-chongyu/a523-debian/releases) 下载 `a523-debian-flasher-v0.1.0-20261114.zip`，完整解压到本地目录。保留子目录。
2. 安装 Python 3.10 或更新版本，启用 Python Launcher（`py` 命令）。需要联网下载依赖和约 1 GB 量级镜像，并预留至少 8 GB 磁盘空间。
3. 用本机已确认有效的按键方式进入 **FEL**，连接一台平板。设备管理器应能看到 USB VID:PID **1f3a:efe8**。进入方式随整机设计变化，本项目不假定统一按键组合。
4. 若缺少 FEL 驱动，用 [Zadig](https://zadig.akeo.ie/) 为 **该 1f3a:efe8 设备**安装 WinUSB。只替换 FEL 接口的驱动。安装器后续出现的 USB 存储、COM 和网卡使用 Windows 自带驱动。
5. 双击 **flash.cmd**，接受 Windows 管理员权限提示。核对显示的板型，输入 **FLASH** 确认清空。工具自动下载、SHA256 校验、写入临时 FEL 安装引导、等待 USB 磁盘、逐块写入并读回校验，最后重建 GPT 并尝试重启。
6. 等待完成提示。首次启动扩展根文件系统，不要中途断电。若提示无法自动重启，请安全断开 USB 后长按电源重新启动。

也可从 PowerShell 指定语言或预演。预演只下载并检查文件，不接触 USB 或磁盘：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\flash.ps1 -Language zh-CN
powershell -NoProfile -ExecutionPolicy Bypass -File .\flash.ps1 -Language zh-CN -DryRun
```

管理员权限用于访问平板的物理 USB 磁盘。工具不接受手填磁盘号，而是要求容量及本次 FEL 写入的随机会话标记同时匹配，并排除 Windows 系统盘和启动盘。

## 3. Linux

```sh
sudo apt install python3 python3-venv curl libusb-1.0-0
chmod +x flash.sh
sudo ./flash.sh --lang zh-CN
```

同样先进入 FEL，只连接一台目标平板。不要挂载安装器导出的分区；如桌面自动挂载，请先卸载。可使用 `sudo ./flash.sh --lang zh-CN --dry-run` 只检查资源。

macOS 的原始磁盘刷写流程未实现，请使用 Windows 或 Linux。

## 4. 首次进入系统

本地账号和密码：**debian / debian**。桌面默认自动登录，默认向右横屏。立即在终端执行 `passwd` 设置自己的密码。root 密码登录已锁定，SSH 默认关闭。

需要远程管理时，在改密后执行：

```sh
sudo systemctl enable --now ssh
```

USB 网络平板地址为 `192.168.77.2/30`；主机网卡手动设为 `192.168.77.1`、掩码 `255.255.255.252`，无需网关。之后可 `ssh debian@192.168.77.2`。系统首次启动重新生成主机身份和 SSH 主机密钥；不要复用别人的密钥或 Wi-Fi 配置。

CPU 默认性能模式，GPU 使用原生 Panfrost，eMMC HS200，zram 2 GiB；不预加载浏览器。温控仍会限制频率。详见首页的完成范围。

## 5. 故障与恢复

下载中断可重新运行，下载使用 `.part` 续传并检查 SHA256。校验失败时删除对应缓存文件后重试；不要关闭校验。缓存默认在用户目录 `.cache/a523-debian/v0.1.0-20261114`，Windows 提权时以运行账户为准。

找不到 FEL：确认 USB 数据线、设备 `1f3a:efe8` 和 WinUSB 驱动，断开其他 FEL 设备。安装器 180 秒内未出现 USB 磁盘，或写入中断：强制关机，再用已经验证的方式进入 FEL，重新运行工具。刷写过程不支持从任意块恢复；重新运行会从头写入镜像。临时安装引导会改写用户区引导位置，失败后原系统可能无法启动。

若不满足 CID 或容量检查，停止刷写，提供板号与脱敏日志进行适配，不能修改检查来强刷。本工具不写 eMMC boot0/boot1/RPMB 或熔丝。没有备份不影响 FEL 恢复，但恢复依赖设备仍可进入 FEL 以及正确的板级内存初始化参数。

提交问题时附系统版本、板号、失败阶段和日志，删除 Wi-Fi 密码、密钥、账户信息及 eMMC 序列号。
