# Optimización del arranque

[English](../BOOT-STARTUP.md) · [简体中文](../zh-CN/BOOT-STARTUP.md) · [日本語](../ja/BOOT-STARTUP.md)

En dos reinicios normales de la tableta original, los cinco procesos del escritorio aparecieron a los **21.73 / 21.64 segundos desde el inicio de Linux**, frente a **25.48 segundos** de referencia: **3.75 / 3.84 segundos** antes. Son marcas de creación de procesos; no miden cuándo el escritorio se puede usar ni el tiempo desde el botón. La imagen del gato conserva el cargador anterior y registró **5.920 / 5.939 segundos** en el contador del hardware.

La prueba completa de 256MiB se ejecuta antes; el controlador de apagado se registra antes del cambio de voltaje de CPU; HS200/100MHz se activa después de las comprobaciones de memoria, temperatura y CPU, antes de GPU y LightDM. Se elimina una comprobación externa duplicada de GPU y la sincronización global del diagnóstico de pantalla. Se mantienen la comprobación inmediata de GPU, el entrenamiento de DRAM, CRC, hashes, protección térmica y reversión. Bluetooth arranca en segundo plano después de LightDM con su secuencia y esperas originales.

Bluetooth sigue necesitando unos 15 segundos. El fin de todos los trabajos de arranque puede ser posterior aunque los procesos del escritorio aparezcan antes. Ambos reinicios aprobaron CPU, 2.5GiB de RAM, gráficos/cálculo GPU, 600 fotogramas de vídeo por hardware y almacenamiento, sin servicios fallidos ni errores observados de memoria/MMC/IOMMU/pantalla. La orientación horizontal a la derecha y la matriz táctil se comprobaron automáticamente; falta la confirmación visual y la medición física con el botón. Las pruebas limitadas no demuestran fiabilidad a largo plazo.

Esta actualización publica código de investigación y [mediciones](../../reports/boot-startup-20261114.json). **La imagen `v0.1.0-20261114` y el instalador `v0.2.0` no cambian.** Depende de hashes y registros de la unidad original; no es una actualización universal. Consulte [English](../BOOT-STARTUP.md) para los detalles y los ensayos descartados.
