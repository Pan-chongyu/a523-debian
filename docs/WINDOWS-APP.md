# Windows standalone flasher / Windows 独立刷机工具

[Download EXE / 下载程序](https://github.com/Pan-chongyu/a523-debian/releases/tag/flasher-v0.2.0)

## 简体中文

下载 `A523-Debian-Flasher-v0.2.0-Windows-x64.exe`，双击并接受管理员权限提示。**无需安装 Python，无需解压脚本包。** 进入 FEL 并连接 USB，核对板号、勾选清空确认，点击“开始刷机”并确认。程序自动下载对应公开镜像，校验 SHA256，识别 eMMC，写入临时安装器及系统，并逐块读回校验。

首次使用如果缺少 FEL 驱动，按[完整教程](zh-CN/FLASHING.md)用 Zadig 为 **1f3a:efe8 的 FEL 接口**安装 WinUSB。系统运行时的 USB 网卡/COM 接口不等于 FEL，不要替换它们的驱动。进入 FEL 的实体按键仍需手动操作。

“只下载并检查”不打开 USB、不刷写，可提前下载到用户目录 `.cache/a523-debian/v0.1.0-20261114`。下载支持续传；下载阶段可取消，写入开始后不能取消或退出。默认在线下载约 770 MB 镜像，不内嵌镜像，因此 EXE 较小。没有代码签名证书；可用 Release 的 SHA256SUMS 核对文件。程序不会修改 Windows 安全策略。

**仅支持指定 TZX 板型，刷机会清空数据。** 仍使用 `v0.1.0-20261114` 实验性公开镜像；本次是刷机工具升级，没有重新验证整包实机刷写。默认账号 `debian / debian`，SSH 默认关闭。

## English

Download and double-click `A523-Debian-Flasher-v0.2.0-Windows-x64.exe`, accepting administrator elevation. **No Python installation or script extraction is required.** Enter FEL, connect USB, verify the exact board, check the data-erasure box, then click **Start flashing** and confirm. Download, SHA256 validation, device identification, installer bootstrap, image writing and block readback are automatic.

Entering FEL and first-time WinUSB driver setup remain manual. Follow the [full guide](en/FLASHING.md); use Zadig only for the **1f3a:efe8 FEL interface**. The normal USB network/COM interfaces are different. **Download and check only** downloads and verifies without opening USB or writing a disk. Downloads resume from cache; cancellation is available before installation begins. The image is downloaded separately (about 770 MB). This unsigned executable has checksums; it does not alter Windows security settings.

Exact supported TZX board only. All tablet data will be replaced. The image remains the experimental `v0.1.0-20261114`; a complete hardware reflash of that public image is untested. Login `debian / debian`; SSH is disabled by default.

## 日本語

EXE をダウンロードしてダブルクリックし、管理者権限を許可してください。**Python のインストールや展開は不要です。** FEL に入り USB 接続、基板と全データ消去を確認して「書き込み開始」を押します。ダウンロード・SHA256 検証・書き込み・読み戻し検証を自動実行します。

FEL への操作と初回 WinUSB 設定は手動です。[手順](ja/FLASHING.md)に従い、Zadig は **1f3a:efe8 の FEL インターフェースのみ**に使用してください。「ダウンロードと検証のみ」は USB やディスクにアクセスしません。ダウンロードのみ中止可能です。未署名の EXE です。イメージは約770 MBを別途ダウンロードします。指定 TZX 基板専用、全データが置き換わります。公開イメージの実機全体書き込みは未検証です。

## Español

Descarga el EXE, haz doble clic y acepta los permisos de administrador. **No requiere instalar Python ni extraer scripts.** Entra en FEL, conecta USB, confirma la placa y el reemplazo de datos, pulsa **Iniciar instalación** y confirma. Descarga, SHA256, identificación, escritura y lectura de verificación son automáticas.

La entrada en FEL y la primera instalación de WinUSB son manuales: sigue la [guía](es/FLASHING.md), usando Zadig solo para **1f3a:efe8 FEL**. **Solo descargar y verificar** no abre USB ni escribe discos. Se puede cancelar la descarga, pero no la escritura. El EXE no tiene firma digital; hay sumas de verificación. Descarga la imagen por separado (unos 770 MB). Solo la placa TZX indicada; se reemplazan todos los datos. La instalación completa de la imagen pública en hardware sigue sin probarse.

## Build from source

On Windows x64 with Python 3.11:

```powershell
py -3.11 -m venv .venv-build
.\.venv-build\Scripts\python -m pip install -r packaging/requirements-windows.txt
.\.venv-build\Scripts\python packaging/build_windows.py --output dist/windows --work build/windows
```

PyInstaller packages the Python/Tk runtime, PyUSB, pySerial and the dynamically loaded libusb DLL. The exact manifest is bundled, pointing to the existing image Release. The build includes dependency notices and LGPL text. To replace libusb, install a compatible modified DLL in the build environment's `libusb_package` directory and rebuild with the same recipe; sources accompany the Release. This project does not prohibit debugging modifications of the LGPL library.

Read-only checks of the **actual EXE** (no USB device is opened):

```powershell
.\A523-Debian-Flasher-v0.2.0-Windows-x64.exe --dependency-check --report dependency-check.json
.\A523-Debian-Flasher-v0.2.0-Windows-x64.exe --self-test --cache PATH_TO_ASSETS --report self-test.json
```

The first command checks bundled dependencies; the second also downloads/verifies every installer input. Use `Start-Process -Wait` when automation needs to wait for a windowed executable.
