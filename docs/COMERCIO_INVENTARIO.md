# Beneficios, transferencias académicas e inventario

Esta ampliación conserva Django, MariaDB, las interfaces HTML y la separación entre convenios tradicionales y sindicatos. Se utiliza el perfil académico del hosting y datos ficticios.

## Registro de trabajadores

En Panel del Sindicato → Crear trabajador, el sindicato autenticado se obtiene de la sesión. Django comprueba su activación, vigencia, RUT, teléfono, correo y duplicados. El RUT inválido se devuelve como error de campo HTTP 400. Una coincidencia con una ficha anterior conserva el procedimiento de verificación de identidad.

El formulario muestra progreso, impide un segundo envío mientras está procesando y conserva los campos ante errores. La petición tiene un límite de 25 segundos. Si no se conoce el resultado de un envío, se debe consultar el listado antes de repetirlo. Al registrar, aparece Mis trabajadores con fecha, estado de validación y cuenta. La invitación individual mantiene su vencimiento y uso único. El registro tradicional continúa en `/app/portal_convenios.html` y `/app/formulario_remoto.html`.

## Beneficios

En Convenios → Beneficios o `/app/beneficios.html`, una cuenta con permisos puede asociar condiciones a una organización. El administrador configura nombre, descripción, tipo, porcentaje o monto, productos, categoría, vigencia, calidad de beneficiario y estado. Los porcentajes admiten entre 0 y 100 y los montos CLP son enteros no negativos.

El cliente consulta `/app/mis_beneficios.html`. Se comprueban la afiliación validada, la vigencia y si corresponde a titular o carga. El representante puede consultar los beneficios institucionales de su organización sin acceso a pagos individuales.

Los descuentos porcentuales, fijos, aportes y precios preferenciales se calculan con Decimal en Django. Se aplica el beneficio monetario que produzca el mayor descuento entre los elegibles, sin acumulación. El redondeo CLP usa mitad hacia arriba. El carrito muestra una referencia y el vendedor vuelve a comprobar las condiciones al confirmar el monto.

`Quote.original_amount`, `Quote.amount` y `Quote.benefit_snapshot` conservan precio original, total final y condiciones aplicadas al confirmar. Esa confirmación bloquea ediciones posteriores de la cotización. Los tipos de evaluación, cargas, catálogo y otros permiten registrar condiciones informativas. El catálogo minero conserva el control de afiliación sindical vigente implementado anteriormente.

## Transferencias

1. El cliente envía el carrito con receta cuando corresponde. La solicitud se conserva en Inquiry y PurchaseLine.
2. El vendedor abre Solicitudes, prepara el borrador y registra la aprobación del cliente en Cotizaciones.
3. En Cotizaciones, Confirmar monto y pago exige revisar precios, cantidades, disponibilidad y receta. Todas las líneas deben tener una variante inventariable configurada.
4. Django congela el monto, reserva existencias y crea un único TransferPayment por cotización.
5. El cliente entra a Mis pedidos → Mis pagos. Puede consultar productos, referencia, monto y datos de transferencia ficticios.
6. Carga un comprobante privado JPG, PNG o PDF válido de hasta 5 MB. Su estado pasa a Comprobante enviado.
7. En Pagos y comprobantes, el personal autorizado descarga la evidencia, contrasta el movimiento bancario y registra aprobación, rechazo o revisión, con observaciones.
8. La aprobación crea una única orden de trabajo. La entrega conserva el documento, firma y código de retiro existentes y registra la salida física del stock.

La pantalla muestra **DEMOSTRACIÓN ACADÉMICA — No realizar transferencias reales**. El banco, número de cuenta y RUT bancario entregados son inoperativos. TransferConfiguration prepara campos administrativos para una aprobación comercial futura. La versión actual mantiene el modo académico aunque se cambien esos campos.

Los estados son Pendiente de pago, Comprobante enviado, En revisión, Pago aprobado, Pago rechazado y Cancelado. Las revisiones son históricas, identifican al usuario y comprueban estado y comprobante vigente bajo bloqueo SQL. Un rechazo permite subir un archivo corregido, conservando los anteriores. Un pago aprobado permanece cerrado. La cancelación previa a crear la orden libera sus reservas. El vendedor puede cancelar órdenes sin entregar y liberar sus reservas. Si la orden está pagada, la cancelación requiere al administrador. El pago aprobado conserva su historial y la devolución del dinero debe revisarse por un canal autorizado. Una orden entregada requiere un procedimiento de devolución posterior.

Los archivos se guardan mediante private_storage en `pagos/<pago>/<UUID>.<extensión>`. En alwaysdata utilizan el almacenamiento privado del perfil, fuera del código y de STATIC_ROOT. El endpoint autenticado comprueba propiedad o permiso de revisión, agrega Cache-Control privado y registra la consulta. La configuración R2 previa sigue siendo independiente de este despliegue académico.

## Inventario

`/app/inventario.html` contiene Resumen, Productos y variantes, Marcas, Modelos, Categorías, Proveedores, Entradas, Salidas, Ajustes, Kardex, Alertas y Reportes.

Product sigue siendo la ficha del catálogo. Brand tiene múltiples ProductModel. StockCategory permite categorías administrables, manteniendo las categorías técnicas anteriores para compatibilidad. ProductVariant normaliza los datos propios de cada combinación. Cada variante tiene SKU único, código de barras opcional único, proveedor, color, tamaño y estado. Inventory conserva sus registros anteriores y permite asociar una variante 1:1.

El ID de MariaDB, SKU y código de barras son identificadores distintos. Las etiquetas PDF usan Code 128 con el código asignado o SKU como identificador interno. Los lectores USB con entrada de teclado pueden escribir el código en el buscador y pulsar Enter. Los identificadores internos no se presentan como EAN o GTIN comerciales registrados.

El buscador filtra en Django por ID, SKU, código de barras, nombre, marca, modelo, categoría o proveedor. Los filtros incluyen disponibilidad, estado, categoría, marca y proveedor. El listado y Kardex están paginados. Los reportes se descargan en CSV. Los costos se muestran a usuarios con la autorización administrativa de configuración y se omiten en las respuestas de los vendedores.

Las entradas, salidas y ajustes producen StockMovement con cantidad anterior, variación, saldo resultante, responsable, motivo y referencia. Un UUID impide repetir el movimiento de una misma operación. El ajuste recibe el stock físico contado. No se permiten saldos negativos ni consumir unidades reservadas para otras cotizaciones. El endpoint de inventario anterior también registra sus ajustes en el historial. Los saldos y datos anteriores a esta ampliación se conservan, sin atribuir movimientos históricos a personas desconocidas.

## Reservas y concurrencia

- Stock físico es Inventory.quantity.
- Stock reservado suma reservas activas no vencidas.
- Stock disponible es físico menos reservado.

Agregar al carrito o enviar una solicitud no produce una salida permanente. Al confirmar el monto se reserva por la duración configurada, inicialmente 48 horas. Al vencer, la reserva deja de bloquear unidades inmediatamente en las consultas. `python amaru/manage.py expire_stock_reservations` marca esas reservas como liberadas. Puede programarse con la infraestructura disponible.

Al cargar un comprobante o aprobarlo se verifica nuevamente la disponibilidad. Un comprobante rechazado conserva la política de vencimiento de la reserva. Una aprobación conserva las unidades hasta entregar o tramitar una revisión administrativa. La entrega consume una sola vez cada reserva y registra una salida. Una repetición no genera otra salida.

Los servicios bloquean la cotización y los artículos por orden de ID. La revisión bloquea pago y cotización, y coteja estado y comprobante. MariaDB arbitra el acceso concurrente. Las pruebas incluyen dos cotizaciones disputando la última unidad y dos revisores aprobando un mismo pago.

## Esquema y permisos

La migración 0015 agrega el estado Cancelada y actualiza su restricción sin borrar órdenes. La migración 0014 agrega doce modelos y la relación M:N entre beneficios y productos. Las nuevas tablas son `gestion_brand`, `gestion_productmodel`, `gestion_stockcategory`, `gestion_supplier`, `gestion_productvariant`, `gestion_agreementbenefit`, `gestion_agreementbenefit_products`, `gestion_transferconfiguration`, `gestion_transferpayment`, `gestion_paymentvoucher`, `gestion_paymentreview`, `gestion_stockmovement` y `gestion_stockreservation`.

Las tablas ampliadas son gestion_product, gestion_inventory y gestion_quote. Se utilizan PROTECT en referencias históricas, unicidad para SKU/código, cotización/pago, variante/artículo y cotización/reserva, e índices por vigencia, estado y fecha. La aplicación no expone eliminaciones de estos registros.

Administrador administra beneficios, maestros, inventario y configuración. Vendedor consulta maestros, registra movimientos autorizados y revisa pagos. Cliente y trabajador asociado consultan sus propios pagos. Sindicato conserva la administración de sus vinculaciones y consulta beneficios institucionales. El acceso a comprobantes individuales requiere la cuenta propietaria o permiso de personal.

## Preparación académica reproducible

Ejecuta configure_roles después de migrar. `seed_commercial_demo --academic --credentials-file RUTA_PRIVADA` agrega datos ficticios mediante get_or_create y conserva los anteriores. Las contraseñas nuevas se generan aleatoriamente y quedan únicamente en el archivo privado indicado. La ruta debe permanecer fuera de los archivos publicados.

El comando prepara un convenio, condiciones ficticias, marca, modelo, categoría, proveedor, tres productos con dos variantes cada uno, saldos disponibles/bajos/agotados, entradas y salidas, pagos pendientes, enviados, aprobados y rechazados. Sus documentos indican expresamente que son ficticios.

Antes del despliegue se necesita respaldo de MariaDB, revisión de migrate --plan, migración, configure_roles, check --deploy y collectstatic con una nueva raíz versionada. Conserva la raíz anterior y recarga WSGI antes de comprobar el CSS y JavaScript públicos.

## Condiciones que debe confirmar la empresa

Beneficios y reglas de acumulación, precios, catálogo oficial, reservas, devoluciones y cancelaciones después de emitir orden, cuentas bancarias autorizadas, permisos de quienes revisan pagos, conservación de comprobantes, condiciones de firma y garantías. Los datos clínicos, nóminas y documentos reales requieren infraestructura y procedimientos aprobados por Ópticas Amaru.
