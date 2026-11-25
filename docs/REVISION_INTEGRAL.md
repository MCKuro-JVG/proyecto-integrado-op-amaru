# Revisión integral de Ópticas Amaru

## Convenios y trabajadores

En **Convenios → Trabajadores registrados** se puede consultar el resumen, buscar por RUT completo o nombre, filtrar por estado o fecha, y abrir la ficha. Los contadores abarcan toda la organización y los filtros afectan a la tabla. La vista visible consulta cambios cada 20 segundos y evita volver a dibujar un listado idéntico. Los registros nuevos por código, QR o personal comienzan pendientes. Un RUT existente solo se asocia después de verificar al titular o mediante su sesión personal autorizada. Solo el personal con los permisos correspondientes puede validar, desactivar o reactivar una afiliación tradicional. En los sindicatos se conservan las invitaciones y el acceso del representante a su organización.

**Códigos QR de atención** contiene los enlaces de registro y de consultas por separado. Cada tarjeta permite mostrar, ampliar, copiar, descargar e imprimir el QR. Regenerar un código afecta únicamente a ese enlace. Ambos comprueban la vigencia de la organización. El QR de consultas genera una solicitud asociada a la organización.

## Compras y beneficios

Una clave del carrito anterior quedaba guardada después de la confirmación. Cuando se repetía la misma cesta, Django devolvía el pago previo y la vista mostraba su estado anterior. Ahora se conserva la clave mientras se espera la confirmación del mismo envío. Al recibirla, se retira la cantidad comprada del carrito y se cierra el intento. Una nueva compra idéntica tiene su propia cotización, pago y comprobante. Reenviar el comprobante idéntico en revisión devuelve el registro actual; el reemplazo sigue disponible después del rechazo. Los archivos se descargan desde el historial mediante las rutas privadas existentes.

El catálogo y la ficha muestran estimaciones unitarias de descuentos porcentuales y precios preferentes. Los aportes fijos se calculan en el carrito. Django evalúa productos, categoría, vigencia y calidad del beneficiario. En la compra se aplica automáticamente el mayor descuento compatible y se guarda la copia de las condiciones en la cotización. Un convenio sin afiliación validada no obtiene descuentos. Los beneficios de atención o de acceso conservan su finalidad. El sitio académico usa transferencia ficticia.

## Inventario y MariaDB

Inventario separa la vista del producto comercial de las variantes inventariables. Muestra ID interno de artículo y producto, SKU, código de barras, modelo, color, tamaño, ubicación, precio de venta, costo sujeto a autorización y existencias físicas, reservadas y disponibles. Los filtros se ejecutan con Django ORM. Las entradas, salidas y ajustes se reflejan en el Kardex. Las reservas se generan al confirmar la operación.

Para verificar un artículo ficticio en DBeaver, buscar su SKU o código de barras y consultar `gestion_productvariant`, `gestion_inventory`, `gestion_stockmovement` y `gestion_stockreservation`. El producto padre se conserva en `gestion_product`. Para convenios y comprobantes, las tablas principales son `gestion_agreement`, `gestion_inquiry`, `gestion_unionmembership`, `gestion_agreementbenefit`, `gestion_transferpayment`, `gestion_paymentvoucher` y `gestion_paymentreview`.

La migración `0018_inactive_agreement_affiliation` añade el estado de afiliación inactiva al campo existente. Conserva el historial en las tablas actuales. Los filtros por fecha calculan límites de calendario en la zona horaria de Django y comparan instantes sin depender de las tablas de zonas horarias de MariaDB.

## Interfaz

La portada presenta una fotografía principal, entradas por categoría, un carrusel manual con controles y teclado, y accesos a servicios y convenios. Las seis fotografías ilustrativas generadas para la demostración se distribuyen en WebP. Las fotos propias de productos tienen prioridad. El encabezado usa los recursos oficiales existentes. El catálogo, los comprobantes y las herramientas de trabajo mantienen la navegación y los permisos de la aplicación.
