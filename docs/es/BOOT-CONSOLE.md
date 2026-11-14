# Registro de arranque y pantalla continua

[English](../BOOT-CONSOLE.md) · [简体中文](../zh-CN/BOOT-CONSOLE.md) · [日本語](../ja/BOOT-CONSOLE.md)

En la tableta original, la pantalla permanece activa al pasar del cargador SRAM a Linux DRM. La imagen del gato aparece primero, seguida de **mensajes reales del kernel y del escritorio XFCE en horizontal hacia la derecha**. El propietario confirmó los registros, la ausencia de barras de color y de apagones intermedios, y el funcionamiento del escritorio y del táctil.

La nueva ruta valida los registros de arranque, la temporización, la dirección de imagen y la alimentación. Conserva PWM, DSI, la alimentación del panel y los dominios VO0, VO1 y DE ya activos. El controlador nativo toma los relojes y GPIO sin reiniciar el panel ni apagar la luz, copia la imagen de los registros a sus búferes DMA32 y activa la salida normal. La inicialización en frío oculta las fuentes de diagnóstico hasta confirmar el primer fotograma; se eliminaron sus barras y búferes de cuatro colores.

El renderizador ARM64 lee `/dev/kmsg` y dibuja registros auténticos en el búfer reservado con la rotación correcta. Al asumir el módulo nativo el control, deja de escribir en la dirección física anterior y continúa en VT1 hasta el escritorio. No simula progreso. La primera imagen SRAM permanece; los registros comienzan cuando el espacio de usuario de Linux puede leerlos. No se afirma que aparezcan inmediatamente al pulsar el botón ni que se haya adelantado la primera iluminación.

Dos arranques normales registraron 422 / 424 mensajes y completaron la transferencia nativa. En el segundo, el servicio confirmó el primer fotograma de registros a los **5,48 segundos desde Linux**; los cinco procesos del escritorio existían a los **20,69 segundos**. No son tiempos desde el botón ni mediciones visuales. Pasaron cargas simultáneas de 42,51 / 44,06 segundos con CPU, 2,5 GiB de RAM, gráficos/cálculo GPU, 600 fotogramas decodificados por hardware y archivos con I/O directo. Cinco ciclos reales de reposo y reactivación del panel verificaron DSI, estado DCS y luz. No hubo errores de pantalla, MMC o IOMMU ni servicios fallidos. [Datos completos](../../reports/boot-console-20261114.json).

Se mantienen CPU performance 1416/1800 MHz, petición mínima GPU de 600 MHz con límites térmicos y de fallo, HS200 a 100 MHz y zram de 2 GiB. No se precarga el navegador. Se comprobaron sin cambios el cargador firmado, la imagen, el paquete comprimido, las GPT y la ranura de recuperación. Este componente usa su propio verificador: el búfer contiene registros y DE continúa activo; las pruebas históricas no se reescriben.

Construcción con los árboles de fuente y configuración exactos del kernel de destino:

```sh
sh research/tools/build_boot_console.sh KERNEL_SOURCE KERNEL_BUILD OUTPUT_DIRECTORY
```

La entrada publicada se ejecutó y produjo los mismos SHA-256 de los dos módulos, el renderizador y la fuente 8×16 GPL del kernel que los instalados. Véanse el [controlador](../../research/firmware/screen-boot-console) y los archivos relacionados en su directorio superior. Construir no instala. Los verificadores dependen de la instalación previa exacta y del instalador protegido de la unidad original; son registros de investigación y no un procedimiento genérico. No se publican credenciales, claves ni capturas privadas de identidad.

Los tres dominios de pantalla siguen alimentados; la suspensión completa no está validada. Este componente no tiene una nueva prueba del botón físico ni de encendido sin batería/USB. Las pruebas finitas no certifican fiabilidad a largo plazo. **Los archivos Release de la imagen `v0.1.0-20261114` y del instalador `v0.2.0` siguen sin cambios.** Se publican fuentes y resultados de la unidad original. [Construcción](../BUILD.md) · [Capa de arranque anterior](BOOT-COMPACT.md).
