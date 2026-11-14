# Guía de instalación

[简体中文](../zh-CN/FLASHING.md) · [English](../en/FLASHING.md) · [日本語](../ja/FLASHING.md)

## Hardware compatible

Solo **TZX P30A523_20T5G**, inscripción `TZX P30A523-56T5G-240321`, A523/sun55iw3p1, **4 GiB LPDDR3**, **eMMC UEM de 128 GB** (244318208 sectores de 512 bytes) y pantalla DSI JL_M1010WX92_M4027 de 800×1280. También se comprueban el ID FEL `0x00189000` y el prefijo de producto CID `3e01ff55454d2020`. Esto no identifica todos los componentes: verifica físicamente la placa.

Es una versión preliminar experimental. Se verificó la tableta original; todavía no se ha comprobado en hardware una instalación completa de esta imagen pública anonimizada. **Se reemplazarán todos los datos de la tableta, sin copia automática.** No es un borrado seguro de todos los sectores. Usa alimentación estable y un cable USB de datos fiable.

## Windows

1. Descarga `a523-debian-flasher-v0.1.0-20261114.zip` de [Releases](https://github.com/Pan-chongyu/a523-debian/releases) y extrae todo el archivo.
2. Instala Python 3.10 o posterior con Python Launcher (`py`). Necesitas Internet para dependencias y una imagen del orden de 1 GB; reserva al menos 8 GB libres.
3. Entra en **FEL** mediante el procedimiento de botones ya verificado para tu tableta y conecta una sola unidad. Confirma USB **1f3a:efe8** en el Administrador de dispositivos. No existe una combinación de botones universal en este proyecto.
4. Si falta el controlador, usa [Zadig](https://zadig.akeo.ie/) para instalar **WinUSB únicamente en ese dispositivo FEL**. No cambies los controladores de almacenamiento, puerto serie o red que aparecerán después.
5. Haz doble clic en **flash.cmd**, acepta los permisos de administrador, confirma el modelo y escribe **FLASH**. La descarga, SHA256, el instalador temporal, la selección del disco, escritura, lectura de comprobación y expansión GPT son automáticos.
6. Espera el mensaje de finalización. El primer inicio amplía el sistema de archivos. Si no se reinicia automáticamente, desconecta USB de forma segura y reinicia con el botón de encendido.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\flash.ps1 -Language es
powershell -NoProfile -ExecutionPolicy Bypass -File .\flash.ps1 -Language es -DryRun
```

`-DryRun` solo descarga y verifica: no abre dispositivos USB ni discos. Los permisos elevados permiten acceder al disco físico USB. No se admite un número de disco arbitrario: deben coincidir la capacidad y un identificador aleatorio de esta sesión. Se excluyen los discos de sistema y arranque de Windows.

## Linux

```sh
sudo apt install python3 python3-venv curl libusb-1.0-0
chmod +x flash.sh
sudo ./flash.sh --lang es
```

Entra antes en FEL y conecta solo una tableta. Desmonta las particiones de la tableta si el escritorio las monta automáticamente. Usa `sudo ./flash.sh --lang es --dry-run` para comprobar archivos. No se ha implementado la escritura de discos en macOS.

## Primer inicio

Usuario y contraseña local: **debian / debian**. El escritorio inicia sesión automáticamente en horizontal girado a la derecha. Ejecuta `passwd` de inmediato. Root está bloqueado y SSH desactivado. Solo después de cambiar la contraseña, puedes ejecutar `sudo systemctl enable --now ssh`.

Para la red USB, configura el equipo con `192.168.77.1`, máscara `255.255.255.252` y sin puerta de enlace; la tableta usa `192.168.77.2`. Conecta mediante `ssh debian@192.168.77.2`. La identidad del sistema y las claves SSH se generan al instalar. No se distribuyen las claves del propietario, las redes Wi-Fi ni su perfil de navegador.

Se configuran el modo de rendimiento, Panfrost, HS200 y 2 GiB de zram; la precarga del navegador está desactivada. La protección térmica sigue activa. Consulta las funciones no verificadas en la página principal.

## Recuperación

Puedes repetir una descarga interrumpida: se reanuda `.part` y se verifica SHA256. Si falla la suma, elimina ese archivo de la caché y vuelve a descargarlo; no desactives la verificación. La caché predeterminada es `~/.cache/a523-debian/v0.1.0-20261114`.

Si no aparece FEL, revisa cable, ID USB, WinUSB y otras unidades conectadas. Si el almacenamiento USB no aparece en 180 segundos o se interrumpe la escritura, fuerza el apagado, vuelve a FEL y ejecuta de nuevo. La escritura de la imagen comienza desde cero. El instalador temporal cambia zonas de arranque del área de usuario; tras un fallo, el sistema anterior puede dejar de arrancar.

No evites las comprobaciones de CID o capacidad. No se escriben boot0, boot1, RPMB ni fusibles. La recuperación requiere FEL funcional y parámetros de DRAM correctos. Elimina contraseñas, claves y números de serie eMMC de los registros antes de informar de problemas.
