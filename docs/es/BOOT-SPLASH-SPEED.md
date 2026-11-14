# Tiempo de la imagen de arranque

[English](../BOOT-SPLASH-SPEED.md) · [简体中文](../zh-CN/BOOT-SPLASH-SPEED.md) · [日本語](../ja/BOOT-SPLASH-SPEED.md)

La tableta original muestra la imagen del gato a los **5,889 / 5,918 segundos**, frente a **7,887 segundos** con el cargador inicial de esta sesión. Son medidas del contador de arranque de 24MHz tras enviar la imagen y verificar el barrido. No miden el tiempo desde el botón físico ni hasta el escritorio. La confirmación visual de esta versión y el encendido después de apagar siguen pendientes.

La CPUA usa los 1416MHz/1150mV ya verificados antes del entrenamiento de DRAM. La espera mínima de un segundo de la alimentación de la pantalla se solapa con dicho entrenamiento, sin acortarla. Se conservan el entrenamiento en cada arranque, los parámetros de memoria, los píxeles y la secuencia de reinicio y activación DSI. Antes de TF-A y si falla el entrenamiento se restauran el voltaje y el reloj originales de la CPU.

Dos reinicios normales superaron pruebas mixtas de aproximadamente 42–43 segundos con CPU, 2,5GiB de memoria, GPU, vídeo y almacenamiento. La configuración horizontal hacia la derecha, la matriz táctil y Bluetooth se restauraron automáticamente, sin errores observados ni servicios fallidos. Se mantienen las protecciones térmicas y de fallos. Esto no demuestra estabilidad a largo plazo. Un candidato anterior tuvo un fallo de inicialización Bluetooth que se recuperó reiniciando el servicio.

**Los archivos de la imagen `v0.1.0-20261114` y del instalador `v0.2.0` no han cambiado.** Esta actualización publica código de investigación y el [informe de medidas](../../reports/boot-splash-speed-20261114.json), no un paquete de arranque que pueda instalarse directamente en otras unidades. Consulte la [descripción en inglés](../BOOT-SPLASH-SPEED.md) y [BUILD.md](../BUILD.md) para los requisitos de compilación. No se publican claves privadas ni credenciales.
