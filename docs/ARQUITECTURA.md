# Arquitectura implementada y diferencias con el informe

## Evolución conservada

Se reutilizan `amaru/gestion`, sus dos migraciones originales, servicios, formularios, pruebas y plantillas. Se mantienen las 15 interfaces de `frontend_amaru`, sus estilos naranjas, recursos y motor de demostración. La vista `/app/` sirve esos mismos HTML con `amaru/static/server.js` y API de Django; no carga `storage.js` ni `app.js` de la demostración.

La arquitectura vigente es **Django + MariaDB + Cloudflare R2**. R2 quedó activado y verificado en el equipo local el 26 de octubre de 2026; véase [CLOUDFLARE_R2.md](CLOUDFLARE_R2.md). MongoDB no se incorpora: los archivos son objetos en R2 y sus referencias están en MariaDB. PostgreSQL permanece respaldado y sin migración automática de sus datos. No hay integración con OptiClick.

## Relaciones y almacenamiento

| Entidad | Relaciones principales y propósito |
|---|---|
| Client | RUT único normalizado; usuario opcional 1:1; convenio opcional N:1; consentimiento y estado activo. Se conserva nombre completo para compatibilidad con datos previos, sin dividir apellidos arbitrariamente. |
| Agreement | Empresa/sindicato y convenio vigente. Nombre único. |
| Consent | Historial N:1 con cliente y usuario responsable opcional. |
| Prescription | N:1 cliente, emisión, referencia privada, responsable y fechas. La vigencia previa de un año calendario se mantiene; el informe menciona 365 días y debe confirmarse esa diferencia antes de cambiar reglas. |
| Product | Catálogo público, SKU único, descripción, categoría, cristal, tratamientos, color e imagen en almacenamiento público explícito. |
| Quote | N:1 cliente/receta/convenio; solicitud previa 1:1 opcional; token único, monto no negativo, aprobación y características de fabricación. |
| QuoteLine | N:1 cotización y producto. Producto único dentro de cada cotización, cantidad positiva y precio no negativo. El detalle normaliza el catálogo; características JSON conservan especificaciones variables y versiones previas. |
| Order | Cotización 1:1; cliente/receta/personal/insumo N:1; estado validado, fecha de creación y modificación. Los productos se consultan a través de su cotización. |
| Inventory | Artículo, categoría, cantidad y observaciones. Consumo opcional de una unidad al convertir cotización; no constituye gestión comercial completa de inventario. |
| Warranty | N:1 OT, motivo, falla, resolución, destino de armazón, estado y fechas. Los cambios generan bitácora. |
| Receipt | OT 1:1; condiciones y observaciones conservadas; firma privada, PDF privado, hash, fecha y responsable. |
| Inquiry | Contacto/agenda/orientación pública independiente de Client; consentimiento de contacto específico, estado, token e identificador de reintento únicos. |
| AppointmentReservation | Solicitud 1:1; fecha y hora únicas. Una plaza académica por horario; no se presupone capacidad oficial de la óptica. Se libera al cerrar/cancelar, conservando la solicitud histórica. |
| DeliveryAttempt | Intento N:1 OT; claves de objetos y estado de compensación. Permite reconciliar interrupciones sin marcar entregas falsas. |
| Audit | Responsable opcional, acción, entidad, identificador y fecha; historial de operaciones. |
| SiteConfiguration | Condiciones de garantía configurables. Los documentos ya emitidos conservan su copia. |
| Django auth | Usuarios, contraseñas derivadas, grupos, permisos, sesiones y administración. |

La API no ofrece eliminación masiva de entidades históricas. Se utilizan `PROTECT` para clientes, recetas, cotizaciones, OT y documentos relacionados; `SET_NULL` conserva operaciones si se elimina un responsable. Clientes y catálogo se desactivan.

## Índices y consultas

- RUT, SKU, tokens e identificadores de reintento: UNIQUE; no se añaden índices redundantes.
- Relaciones FK y 1:1: índices de Django para buscar por cliente, receta, OT y cotización.
- OT y garantías: `(status, created_at)` para filtros por avance y antigüedad.
- Solicitudes públicas: `(status, created_at)` para la cola de atención.
- Auditoría: `(model, record_id, at)` para historial de una ficha concreta.
- Agenda: UNIQUE `(day, slot)` para arbitrar concurrencia incluso entre procesos.
- La API usa paginación, `select_related` en relaciones de lectura y `prefetch_related('lines__product')` para cotizaciones.
- Las búsquedas parciales por nombre/RUT con `icontains` no garantizan uso de índices B-tree. Evaluar búsqueda exacta/prefijo según volumen real antes de agregar índices.

El folio anterior combina prefijo, PK y parte del UUID; se conserva como propiedad calculada. No existe una columna folio duplicada que pueda desincronizarse. Los endpoints utilizan PK con autorización; la consulta pública anterior exige RUT y folio impredecible y solo expone avance, sin datos personales.

## Permisos y seguridad

Autenticación de sesión Django con CSRF en operaciones del navegador. Cuatro grupos configurados mediante `configure_roles`. El taller puede trabajar sobre avance y garantías, con datos mínimos de la OT; no recibe recetas ni archivos privados. Los clientes solo consultan pedidos y comprobantes vinculados a su usuario, nunca por RUT público. Las firmas no se retornan como base64 en listados.

R2 privado es el destino predeterminado. El acceso autorizado se audita y entrega un archivo privado local o una URL firmada de duración limitada. Las claves nunca se envían al navegador. Los permisos del bucket deben comprobarse contra Cloudflare; el código no habilita acceso público a ningún bucket.

Las reglas EPS se materializan parcialmente en autenticación, permisos, validación, control de archivos, auditoría y configuración separada. No se declara certificación de cumplimiento EPS01–EPS14. Para producción falta validar infraestructura, HTTPS, secretos, caché compartida, recuperación de respaldos, políticas de conservación y políticas operativas de R2. La conexión remota y el flujo de entrega de prueba sí se verificaron, según el registro de Cloudflare.

## Límites conservados

La agenda registra solicitudes, no confirma citas con la empresa ni envía mensajes. Catálogo/precios de ejemplo no son comerciales. No se trasladan datos de localStorage ni PostgreSQL sin una migración revisada. La versión estática alojada anteriormente continúa siendo DEMO; publicar un backend exige un hosting con Python y acceso a MariaDB/R2.
