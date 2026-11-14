# GPU API・安定性更新 v0.3.0

[English](../GPU-API.md) · [简体中文](../zh-CN/GPU-API.md) · [Español](../es/GPU-API.md)

対象は既存の適合作業済み **TZX P30A523_20T5G / Mali-G57 / LPDDR3 4 GiB / UEM 128 GB** です。Rusticl OpenCL、API テスト、継続的な状態記録を追加します。カーネル、起動領域、パーティション、画面設定、温度・障害保護は変更しません。

**既存イメージ `v0.1.0-20261114` と Windows ツール `flasher-v0.2.0` は変更されていません。イメージを書き込んだ後に、この追加パッケージをインストールしてください。** 元のタブレットでの検証であり、公開用イメージ全体の実機書き込み・起動試験ではありません。

| API | 実機で確認した範囲 |
|---|---|
| EGL / OpenGL | EGL 1.5、OpenGL 3.1 / GLSL 1.40、Mesa 25.0.7-2+deb13u1、Panfrost |
| OpenGL ES | GLES 3.1 / ESSL 3.10、シェーダー、ピクセル読出し、コンピュートと同期 |
| WebGL 1 / 2 | Firefox ESR 内部で Mali-G57 を確認。各 API 120 フレームを検証 |
| OpenCL | Rusticl GPU デバイスが OpenCL 3.0 を報告。標準の OpenCL C 表示は 1.2。CL3.0 指定のコンパイルと一部の任意機能も検証 |
| OpenCL IL | SPIR-V 1.0 カーネルの 65,536 結果が一致 |
| Vulkan | この Mali-G57 / Valhall v9 用の適合したハードウェア実装はありません |

対応範囲は [Mesa Panfrost](https://docs.mesa3d.org/drivers/panfrost.html) と [Rusticl](https://docs.mesa3d.org/rusticl.html) に基づきます。CPU OpenCL、ソフトウェア Vulkan、API バージョン偽装は使いません。OpenCL の整数・浮動小数点、ローカルメモリ同期、画像、int64、アトミック操作、キュー間イベントをテストします。完全な Khronos CTS や新たな認証ではありません。FP16、FP64、SVM、CL/GL オブジェクト共有は、このデバイスでは利用可能として公開されていません。

Firefox が Web ページに表示する「Mali-G51, or similar」は匿名化された名称の場合があります。テストは Firefox 内部の Mali-G57 レンダラーも確認し、ブラウザーのプライバシー設定を変更しません。

## インストール

[GPU API Release](https://github.com/Pan-chongyu/a523-debian/releases/tag/gpu-api-v0.3.0) から `a523-gpu-api-v0.3.0.tar.gz` と `SHA256SUMS` を取得し、**タブレットの Debian 上で**実行します。

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

11 個の新規 Debian 依存パッケージを同梱します。ボード、eMMC 容量、Panfrost 構成、Mesa バージョン、SHA256 を確認し、依存関係の置換・削除、他のファイルの上書きを拒否します。有効化前に一般ユーザーで GPU テストを実行します。eMMC 消去は行いません。公開イメージと異なる依存バージョンに更新済みの場合は停止します。

再起動後はログインシェル、X11 アプリ、新しい systemd ユーザーセッションで OpenCL が利用できます。即時利用には `tzx-opencl clinfo -l` または `tzx-opencl アプリ名` を使います。`DISPLAY=:0 tzx-gpu-check info` で診断できます。`sudo tzx-gpu-check webgl --output /var/lib/tzx-gpu-api-tests/webgl.json` は、独立した一時 Firefox ウィンドウを開いて検証し、正常終了します。既存のブラウザープロファイルは使用しません。

## 継続試験・記録・削除

実際の試験時間、回数、温度と再起動結果は Release の `gpu-api-validation.json` を参照してください。一定時間の成功は長期の無故障を保証しません。過去の開発中のハングや未解明の GPU 障害も考慮する必要があります。

```sh
sudo systemd-run --unit=tzx-gpu-api-soak \
  --property=MemoryMax=1600M --property=RuntimeMaxSec=3950 \
  /usr/local/bin/tzx-gpu-check soak --duration 3600 \
  --output /var/lib/tzx-gpu-api-tests/new-run
sudo journalctl -fu tzx-gpu-api-soak
```

毎回、新しい出力ディレクトリとユニット名を使います。OpenCL、GLES、glmark2 と 512 MiB RAM 校正を同時実行し、不一致、タイムアウト、新規障害、デスクトップ再起動、85°C 以上で停止します。既存の温度保護により GPU は 600 MHz 要求から 400/200 MHz に下がる場合があります。`clinfo` の静的な 800 MHz 表示は実クロックではなく、800 MHz OPP を有効にしません。

`tzx-gpu-api-health.service` は 10 秒ごとに確認し、正常時は 30 秒ごとに最大 32 起動分の概要を保存します。状態は `/run/tzx-gpu-api-health.json`、永続記録は root 用の `/var/lib/tzx-gpu-api-health/` です。systemd watchdog は記録プロセスを監視します。異常終了の記録だけでは、停電、電源ボタン、カーネル障害の区別はできません。GPU リセットやデスクトップ再起動は行いません。

削除は展開したフォルダーから `sudo python3 gpu/install.py --rollback`、続いて `sudo reboot`。未変更の自有ファイルと記録サービスを削除し、Debian パッケージ、診断履歴、既存の保護機能は保持します。ソースと依存関係の詳細は [英語版](../GPU-API.md) を参照してください。
