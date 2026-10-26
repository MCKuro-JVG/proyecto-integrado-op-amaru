# Actualización del prototipo Ópticas Amaru

Se actualizó `frontend_amaru`, la versión local más reciente (5 de octubre de 2026, posterior a `mockups_opticas_amaru`). Se revisaron las 12 pantallas originales, sus formularios, navegación y las interacciones de `js/app.js`. El inventario de esa revisión está en `../revision_frontend_amaru.json`.

La copia original completa se conserva en `../respaldos/frontend_amaru_antes_actualizacion_2026-10-19.zip`. No se modificaron `amaru` (Django/PostgreSQL), `mockups_opticas_amaru` ni el respaldo anterior de octubre.

## Organización y reutilización

Se mantienen las 12 rutas originales. `index.html` pasa de acceso ilustrativo a inicio público; `consulta.html` se convierte en Mis pedidos del perfil ficticio; `formulario_remoto.html` reúne agenda, contacto y solicitud de lentes. `recepcion.html` integra identificación, documento, conformidad, impresión e historial sin duplicar una pantalla de entrega.

Solo se añadieron tres rutas: `catalogo.html`, `solicitudes.html` y `documentos.html`. El panel conserva resumen, clientes, ficha, recetas, cotizaciones, pedidos, garantías e inventario. Se reutilizan la marca SVG, las clases de componentes, el CSS original y su diseño adaptable. `css/actualizacion.css` amplía la identidad naranja, navegación pública, documentos, formularios y estilos de impresión. Las ilustraciones del catálogo son SVG locales, no fotografías ni productos oficiales.

## Cuatro requerimientos de la encargada

| Requerimiento | Implementación dentro del alcance académico |
|---|---|
| 1. Integrar retiro | Identificación por cliente/RUT DEMO/pedido, comprobación de disponibilidad, creación de borrador, revisión, conformidad, cambio a Entregado e historial. No es necesario un formulario externo. |
| 2. Documento digital | Incluye cliente, RUT ficticio, producto, pedido, fecha de preparación, fecha/hora efectiva de retiro, condiciones conservadas, observaciones, estado y firma dibujada o aceptación. Vista previa, consulta e impresión/Guardar PDF del navegador. |
| 3. OptiClick fuera de alcance | No hay módulos, importaciones, sincronización ni dependencia de OptiClick en el frontend actualizado. |
| 4. Potenciales clientes | Catálogo, servicios y formularios públicos sin registro previo. Capturan nombre, teléfono, correo, motivo, tipo de atención y horario solicitado. La solicitud aparece en el panel del personal con estados editables. |

El frontend anterior no tenía lector ni generador de QR operativo: mostraba una referencia de URL directa. Se integró el trámite completo en su propia ruta de recepción. No se eliminó un generador existente. Si la empresa desea continuar usando QR físico, podrá dirigir a la entrada de pedidos del cliente sin incluir datos personales; la generación/lectura de QR y un acceso autenticado entre dispositivos no forman parte de esta actualización.

## Persistencia y coherencia

Los datos ficticios se guardan en `localStorage`, clave `opticas-amaru.demo.v2`, dentro del mismo origen (por ejemplo, `http://127.0.0.1:8000`). Clientes, pedidos, documentos, solicitudes, cotizaciones, referencias de recetas, garantías e inventario comparten una instantánea. `sessionStorage` conserva únicamente la selección del perfil ficticio de Elena, clave `opticas-amaru.perfil-demo`.

Cada confirmación de entrega vuelve a leer el estado local, comprueba disponibilidad, evita confirmar nuevamente el mismo documento y guarda documento y pedido en una operación de almacenamiento. No se permite marcar Entregado desde el selector de avance. Los documentos preparados conservan las condiciones y el mecanismo de aceptación que el cliente revisó; los cambios de configuración solo afectan a documentos nuevos. Un borrador puede descartarse explícitamente antes de preparar otro.

Las pestañas del mismo navegador notifican cambios y ofrecen actualizar. Esto no sustituye transacciones de servidor ni resuelve escrituras simultáneas desde dispositivos diferentes. No se garantiza inmutabilidad ni auditoría contra manipulación del almacenamiento local. Si no hay espacio o el formato está dañado, la interfaz informa el problema sin mostrar una confirmación falsa ni borrar automáticamente los datos existentes.

## Funciones conservadas y ampliadas

- Directorio y ficha de clientes con búsqueda, verificación de RUT para registros nuevos y prevención de duplicados.
- Referencias de recetas y vigencia por año calendario. Se seleccionan archivos de prueba, pero se conserva solo el nombre, fecha y relación; no se almacena su contenido clínico.
- Cotizaciones con cambios particular/seguridad, armazón/modelo, monofocal/multifocal, color, tratamientos y convenio. El resumen calcula valores ficticios. Guardado de borrador y aprobación con creación de OT si existe referencia de receta vigente.
- Pedidos en tablero y listado, búsqueda, filtros, historial y cambios de estado.
- Posventa asociada a pedidos, con justificación obligatoria al rechazar.
- Inventario con búsqueda y ajuste de cantidades enteras no negativas.
- Solicitud de lentes con receta ficticia opcional y selección de producto. Agenda y contacto se integran en la misma pantalla pública.
- Mensajes de éxito, validaciones, estados vacíos y navegación móvil.

## Alcance de seguridad y pendientes

La navegación pública no permite consultar pedidos por un folio libre ni mostrar documentos de otro perfil desde la vista cliente. Sin embargo, este es un prototipo con todos sus datos ficticios en el navegador. El panel del personal es de libre acceso DEMO; no existe autenticación real y no se debe usar con datos reales. La selección de Elena no aparenta ser una verificación de identidad.

Para producción se necesitan backend, autenticación, autorización por titularidad, almacenamiento y protección de documentos, gestión de sesiones y copias de seguridad, agenda compartida, comunicaciones reales y validación del contenido de archivos. El prototipo funciona sin servicios externos mientras el servidor local esté iniciado; cargar desde otro teléfono no sincroniza automáticamente los datos de su navegador.

Pendiente de confirmar con la encargada: texto oficial de garantía; preferencia por firma dibujada o aceptación; cómo identificar al cliente y entregar el acceso al retiro; continuidad del QR y su destino; servicios, catálogo, disponibilidad y horarios oficiales. Los precios de cotización son solo académicos. No se añadieron dirección, teléfono comercial, precios ni coberturas oficiales inventadas.

## Verificación

El script `../verificar_frontend_amaru.py` usa un navegador aislado y datos TEST, sin modificar el almacenamiento del navegador del usuario. Los resultados y capturas se guardan en `../verificacion_frontend_2026-10-19`. Se comprueban los flujos de atención y entrega, estados, persistencia, documento, impresión, módulos anteriores, recursos, enlaces y resoluciones. El PDF de prueba corresponde a una entrega ficticia y no a una persona real.
