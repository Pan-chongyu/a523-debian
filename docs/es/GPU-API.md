# Actualización de API de GPU y estabilidad v0.3.0

[English](../GPU-API.md) · [简体中文](../zh-CN/GPU-API.md) · [日本語](../ja/GPU-API.md)

Complemento para la instalación adaptada de **TZX P30A523_20T5G / Mali-G57 / LPDDR3 de 4 GiB / UEM de 128 GB**. Añade OpenCL mediante Rusticl, pruebas y registro persistente del estado. Conserva el kernel, el arranque, las particiones, la pantalla y las protecciones térmicas y de fallos.

**La imagen `v0.1.0-20261114` y la herramienta Windows `flasher-v0.2.0` no cambian. Instale este complemento después de grabar esa imagen.** Las pruebas en la instalación original no equivalen a una prueba completa de grabación y arranque de la imagen pública saneada.

| API | Alcance comprobado |
|---|---|
| EGL / OpenGL | EGL 1.5; OpenGL 3.1 / GLSL 1.40; Mesa 25.0.7-2+deb13u1 y Panfrost |
| OpenGL ES | GLES 3.1 / ESSL 3.10; sombreadores, lectura de píxeles, cálculo y sincronización |
| WebGL 1 / 2 | Firefox ESR con Mali-G57 interno; 120 fotogramas comprobados por API |
| OpenCL | Rusticl identifica la GPU como OpenCL 3.0; la consulta de OpenCL C por defecto indica 1.2; compilación CL3.0 y algunas funciones opcionales comprobadas |
| OpenCL IL | Programa SPIR-V 1.0 ejecutado; coinciden los 65.536 resultados |
| Vulkan | No hay una implementación de hardware cualificada para Mali-G57 / Valhall v9 en esta pila |

Consulte [Mesa Panfrost](https://docs.mesa3d.org/drivers/panfrost.html) y [Rusticl](https://docs.mesa3d.org/rusticl.html). No se simulan versiones ni se usa OpenCL de CPU o Vulkan por software para aprobar las pruebas. Se verifican enteros, float32, barreras, imágenes, int64, atómicos y eventos entre colas. Esto no es el CTS completo de Khronos ni una nueva certificación. Este dispositivo no anuncia FP16, FP64, SVM ni objetos compartidos CL/GL.

Firefox puede mostrar a las páginas el nombre anonimizado «Mali-G51, or similar». La prueba comprueba por separado el renderizador Mali-G57 interno y conserva las opciones de privacidad del navegador.

## Instalación

Descargue `a523-gpu-api-v0.3.0.tar.gz` y `SHA256SUMS` de la [versión de API de GPU](https://github.com/Pan-chongyu/a523-debian/releases/tag/gpu-api-v0.3.0). Ejecute **en Debian de la tableta**:

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

Se incluyen las once nuevas dependencias Debian. El instalador comprueba la placa, capacidad eMMC, configuración Panfrost, versión Mesa y SHA256. Rechaza actualizaciones o eliminaciones de dependencias y archivos ajenos. Ejecuta la aceptación de GPU con el usuario normal antes de activar los cambios. No borra eMMC. Si las dependencias ya difieren de las de la imagen publicada, la instalación se detiene.

Tras reiniciar, OpenCL estará disponible en sesiones nuevas de shell, X11 y systemd del usuario. Para usarlo de inmediato: `tzx-opencl clinfo -l` o `tzx-opencl su-programa`. El comando `DISPLAY=:0 tzx-gpu-check info` muestra el diagnóstico. `sudo tzx-gpu-check webgl --output /var/lib/tzx-gpu-api-tests/webgl.json` abre una ventana Firefox temporal, utiliza un perfil independiente y cierra el navegador correctamente; no lee el perfil personal.

## Pruebas, diagnóstico y reversión

El archivo `gpu-api-validation.json` de la versión contiene la duración real, repeticiones, temperaturas y comprobación de reinicio. Una prueba finita no garantiza fiabilidad permanente ni elimina los fallos históricos de desarrollo o el fallo GPU anterior de causa no resuelta.

```sh
sudo systemd-run --unit=tzx-gpu-api-soak \
  --property=MemoryMax=1600M --property=RuntimeMaxSec=3950 \
  /usr/local/bin/tzx-gpu-check soak --duration 3600 \
  --output /var/lib/tzx-gpu-api-tests/new-run
sudo journalctl -fu tzx-gpu-api-soak
```

Use nombres de unidad y directorios nuevos. La prueba combina OpenCL, GLES, glmark2 y comprobación de 512 MiB de RAM. Se detiene ante resultados erróneos, tiempos agotados, nuevos fallos, reinicio del escritorio o 85 °C. No escribe almacenamiento en bruto. El control térmico conserva las reducciones de GPU de 600 a 400/200 MHz. Los 800 MHz estáticos de `clinfo` no son la frecuencia real ni habilitan un OPP de 800 MHz.

`tzx-gpu-api-health.service` toma muestras cada diez segundos y guarda resúmenes cada treinta segundos durante el funcionamiento sano, hasta 32 arranques. Estado actual: `/run/tzx-gpu-api-health.json`; historial privado de root: `/var/lib/tzx-gpu-api-health/`. El watchdog de systemd vigila el registrador. Un registro incompleto no distingue entre pérdida de energía, botón forzado o fallo de kernel. El servicio no reinicia la GPU ni el escritorio.

Para revertir, desde el directorio extraído: `sudo python3 gpu/install.py --rollback` y `sudo reboot`. Se retiran el servicio y los archivos propios sin modificaciones; se conservan paquetes Debian, historial y protecciones originales. Consulte la [guía inglesa](../GPU-API.md) para versiones y fuentes correspondientes.
