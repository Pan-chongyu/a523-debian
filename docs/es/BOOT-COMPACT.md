# Arranque con núcleo comprimido

[English](../BOOT-COMPACT.md) · [简体中文](../zh-CN/BOOT-COMPACT.md) · [日本語](../ja/BOOT-COMPACT.md)

Dos reinicios normales de la tableta original aprobaron las pruebas. Las lecturas y CRC bajaron de **5.00 s a 2.22 / 2.22 s**; la nueva descompresión, reubicación, CRC y limpieza de caché añaden **0.265 / 0.265 s**. Se leen aproximadamente un 55% menos de bytes y el núcleo descomprimido coincide exactamente con el original. Los cinco procesos del escritorio aparecen a los **19.83 / 19.96 s desde el inicio de Linux**, frente a21.64 s antes. No mide cuándo la pantalla se puede usar.

La primera imagen del gato sigue a los **5.912 / 5.916 s** del contador; esta capa no adelanta esa imagen. No se ha repetido la medición física del botón. Se usa LZ4 con límites, un mapa de identidad y caché temporales para RAM, limpieza a PoC y restauración de MMU/caché y registros EL2 antes de Linux. Se mantienen entrenamiento de DRAM, CRC, recuperación USB, imagen y partición alternativa. Se eliminan BusyBox duplicado, documentación y salida UART temprana forzada.

Ambos reinicios aprobaron CPU, 2.5GiB de RAM, gráficos/cálculo GPU, 600 fotogramas decodificados por hardware y almacenamiento simultáneos, sin servicios fallidos ni errores observados de memoria/MMC/IOMMU/pantalla. Se conservan CPU performance 1416/1800MHz, petición GPU de 600MHz con límites térmicos, HS200 100MHz y zram de 2GiB. Tras el segundo arranque, el propietario confirmó imagen, escritorio horizontal a la derecha y pantalla táctil normales, además de los controles automáticos. Las pruebas limitadas no demuestran fiabilidad a largo plazo.

Esta actualización publica investigación y [mediciones](../../reports/boot-compact-20261114.json). **La imagen `v0.1.0-20261114` y el instalador `v0.2.0` no cambian.** No es una actualización universal. Requiere los archivos históricos de la unidad original. Consulte [English](../BOOT-COMPACT.md) para la prueba sin caché descartada, la restauración probada y los detalles.
