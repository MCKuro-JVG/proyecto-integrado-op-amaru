# Reparación de carga y revisión visual de Ópticas Amaru

Fecha: 19 de octubre de 2026. Se corrigió la versión existente de `frontend_amaru`; no se creó un proyecto nuevo.

## 1. Diagnóstico y causa reproducida

El servidor entregaba el HTML, JavaScript y CSS actuales con HTTP 200. Los hashes de los recursos servidos coincidían con los archivos del disco y el análisis de sintaxis de JavaScript no detectó errores. En una pestaña nueva de Google Chrome el frontend actual mostraba contenido. Por tanto, no había evidencia de que los módulos hubiesen sido eliminados ni de un 404 general del servidor.

Se reprodujo exactamente el síntoma de menú visible y área principal vacía, en Inicio y Resumen, usando el HTML actual y el JavaScript del frontend anterior conservado en el respaldo. El resultado no generaba excepciones: el script antiguo manejaba elementos que ya no existían y nunca construía el nuevo contenedor `#screen`. El HTML dejaba ese contenedor vacío y no existía control de versión entre los recursos ni una comprobación de que se hubiera renderizado la vista. La evidencia anterior a la corrección está en `../verificacion_reparacion/reproduccion_antes.json`, `antes_index.png` y `antes_dashboard.png`.

Esto confirma el fallo de compatibilidad entre versiones y la falta de recuperación de la carga. No se recuperó la entrada de caché de la pestaña original del usuario, por lo que no se presenta esa entrada concreta como un hecho comprobado. La sesión nueva de Chrome sí fue inspeccionada y funcionó. Tampoco se atribuyó el fallo original a localStorage sin evidencia: su validación se reforzó por separado.

Además, las estructuras antiguas incompletas podían romper componentes: por ejemplo, un pedido con `history: null` o un documento con `customer: null`. Se reprodujeron esos casos en un contexto aislado y se agregó adaptación con respaldo previo del valor original. No se necesita borrar todos los datos del navegador.

## 2. Correcciones implementadas

- HTML y recursos enlazados por versión calculada desde el hash de su contenido. Cambiar el JavaScript o CSS produce una URL diferente y evita reutilizar silenciosamente el recurso anterior.
- Nuevo servidor estático local `servidor_amaru.py`, limitado a `127.0.0.1` y a la carpeta del frontend. Envía `Cache-Control: no-store` y evita respuestas 304 con recursos antiguos durante la edición.
- Nuevo módulo de arranque `js/bootstrap.js`: comprueba el resultado después de los scripts diferidos en `DOMContentLoaded`, sin depender de temporizadores que Chrome puede limitar en segundo plano. Diagnostica 404 de script, excepciones de ejecución o una vista que no terminó de renderizarse. Si falta `#screen`, crea un contenedor de recuperación.
- Los 15 HTML tienen una salida inicial visible, un mensaje comprensible y reintento, en lugar de un `main` vacío. El contenido funcional sigue generado por los módulos existentes.
- Límite de error por vista en `app.js`, referencias opcionales a controles y validación de fechas antes de formatearlas. No se consideran vigentes recetas sin fecha.
- Nuevo módulo `js/storage.js` con adaptación conservadora del estado. Las estructuras conocidas se normalizan y se conserva el valor original en una clave `opticas-amaru.demo.v2.respaldo.*` antes de guardar una migración.
- Ante JSON dañado, esquema no reconocible, cuota agotada o almacenamiento bloqueado, se conserva el original y se muestra un escenario temporal de solo lectura. Los formularios no pueden anunciar una escritura que no ocurrió. Los datos originales y sus respaldos se pueden descargar desde el aviso.
- El generador de HTML existente llama al preparador de recursos para conservar estas protecciones al regenerar las rutas.

## 3. Funcionalidades conservadas y recuperadas

Se mantienen las rutas de clientes, ficha, recetas, cotizaciones, pedidos, tablero/listado, historial de avance, retiro, documentos, solicitudes, garantías e inventario. El problema de las pantallas vacías se corrigió en su carga; no se sustituyeron por módulos decorativos.

Las solicitudes de agenda, contacto y lentes se guardan en el navegador y aparecen en el panel. El avance de un pedido se consulta en el perfil correspondiente. El retiro exige disponibilidad, prepara un documento, conserva las condiciones revisadas y registra firma o aceptación. Al confirmar se actualizan conjuntamente documento y pedido a Confirmado/Entregado. El documento se consulta e imprime mediante el navegador. Se conserva el bloqueo de pedidos ajenos dentro de la experiencia de cliente DEMO, sin afirmar que exista autenticación real.

OptiClick sigue fuera del alcance. No se modificó el sistema anterior en Django/PostgreSQL ni la carpeta `mockups_opticas_amaru`; sus archivos comparables siguen coincidiendo con el respaldo anterior, excluyendo cachés y logs.

## 4. Mejora visual

El menú del personal usa naranja intenso y oscuro, texto claro y selección blanca con acento naranja. Se diferenciaron las superficies de contenido mediante fondo gris claro, tarjetas blancas, bordes y encabezados naranjas. La portada mantiene un bloque naranja fuerte y suma una sección ilustrada de atención óptica, servicios y llamadas a agendar/contactar. Las imágenes SVG son locales y demostrativas.

El Resumen muestra seis indicadores calculados desde los datos: clientes, pedidos, pendientes, listos para entregar, entregas completadas y solicitudes. También ofrece pedidos recientes, una tabla resumida de consultas y actividad reciente. No son cantidades decorativas fijas. El catálogo incorpora categoría y búsqueda combinadas, conservando la descripción de servicios.

## 5. Archivos modificados

- Los 15 HTML de `frontend_amaru`: scripts/estilos versionados y salida inicial de carga.
- `frontend_amaru/js/app.js`: adaptación del acceso al estado, defensas de renderizado, fechas, catálogo y Resumen.
- `frontend_amaru/css/actualizacion.css`: identidad naranja, jerarquía y adaptación visual.
- `Abrir_Opticas_Amaru.ps1`: servidor local nuevo y apertura preferente en Google Chrome; se conserva el `.cmd` existente.
- `actualizar_frontend_amaru.py`: preparación de recursos al regenerar HTML.
- `frontend_amaru/GUIA_PRESENTACION.md`: instrucciones de inicio y recuperación actualizadas.

Archivos añadidos: `frontend_amaru/js/bootstrap.js`, `frontend_amaru/js/storage.js`, `frontend_amaru/img/atencion_optica.svg`, `servidor_amaru.py`, `preparar_recursos_amaru.py` y los scripts de reproducción/verificación. El inventario de cambios está en `../verificacion_reparacion/archivos_modificados.json`.

## 6. Pruebas ejecutadas

Se ejecutó Chrome instalado en Windows, con automatización Playwright en contextos aislados y datos ficticios. También se inspeccionó la pestaña abierta de Chrome: inicio con contenido, navegación pública, filtrado por categoría, Resumen con seis indicadores, pedidos y actividad, menú del personal y consola sin errores durante ese recorrido.

La suite funcional pasó: 15 rutas, contenido visible, enlaces internos, recursos, formularios inválidos, agenda/contacto reflejados en el panel, horario duplicado, perfil propio y documento ajeno, retiro completo con firma y limpieza, confirmación, persistencia al recargar, impresión a PDF, garantía conservada por documento, mecanismo configurable, clientes y RUT duplicado, cotización a OT, garantías, recetas, inventario, aviso entre pestañas y firma táctil móvil. Se revisaron 1920, 1366, 768 y 375 píxeles sin desbordamiento horizontal.

La suite de resiliencia pasó: recurso anterior de la caché simulada, 404 y excepción de script, contenedor ausente, datos antiguos nulos/incompletos, adaptación de Listo para retiro, conservación/descarga del original, JSON dañado, almacenamiento bloqueado y cabeceras del servidor. Los fallos deliberados de esos casos se registran como pruebas de error; la navegación funcional normal no produjo errores JavaScript ni recursos HTTP fallidos.

Resultados completos: `../verificacion_frontend_2026-10-19/resultados.json` y `../verificacion_reparacion/resultados_resiliencia.json`. Capturas finales: `../verificacion_reparacion/inicio_corregido.png` y `panel_corregido.png`.

El PowerShell de inicio pasó el análisis sintáctico y se ejecutó correctamente, reutilizando el servidor local activo y abriendo la página en Chrome. El servidor fue iniciado y comprobado por separado. Se conservaron copias de los archivos anteriores en `../respaldos/antes_reparacion_20261019_144343.zip`.

## 7. Inicio y límites

En Windows, abre `../Abrir_Opticas_Amaru.cmd`. En Chrome entra a **http://127.0.0.1:8000/** o a **http://127.0.0.1:8000/dashboard.html**. Alternativa desde la carpeta principal: `python servidor_amaru.py --port 8000`; mantén esa terminal abierta.

No se requiere borrar caché ni historial como procedimiento normal. Mantén el mismo navegador y la dirección `127.0.0.1:8000` para conservar el escenario. Si ya tenías una pestaña abierta antes de esta reparación, vuelve a cargarla para que use el HTML y los recursos versionados actuales.

El alcance sigue siendo académico: localStorage no sincroniza dispositivos, no hay autenticación real, mensajes externos ni reservas comerciales. Las recetas conservan solo referencias ficticias, no contenido clínico; la firma es simple y demostrativa. Pendientes con la empresa: garantía oficial, mecanismo de firma, acceso/QR definitivo y catálogo/horarios comerciales. No quedaron errores detectados en las rutas y escenarios probados; no se certifica el comportamiento de extensiones de Chrome o perfiles distintos que no participaron en la verificación.
