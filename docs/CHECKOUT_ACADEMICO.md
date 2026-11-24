# Checkout académico desde Mi carrito

El cliente completa el recorrido en `/app/carrito.html`: selección → transferencia bancaria → envío del comprobante. Se reutilizan las solicitudes, cotizaciones, pagos, documentos privados, revisión y reservas de inventario existentes. No se implementan cobros ni conexión bancaria real.

## Habilitar un producto

En Administración de catálogo, una cuenta con permiso para modificar productos configura un precio positivo y selecciona **Pago académico desde carrito → Precio habilitado para checkout**. La migración `0016_precio_checkout_academico` agrega `Product.direct_checkout`, desactivado por defecto, sin crear tablas ni cambiar precios anteriores. El comando de demostración habilita únicamente los accesorios ficticios `DEMO-COM-*`.

La selección necesita variantes inventariables activas y existencias suficientes. Los productos con receta conservan la revisión óptica previa, incluso si se cargó un archivo vigente. Los productos sin precio habilitado pasan por **Solicitar revisión previa**. El cliente puede consultar esa revisión desde Mis pedidos y retomar el pago cuando el personal lo confirme. Una carga de receta no constituye revisión profesional.

## Recorrido del cliente

1. Inicia sesión con una cuenta de cliente activa. Selecciona un producto y variante en el catálogo y agrégalo al carrito.
2. Mi carrito muestra imagen, características, cantidad, precio unitario, subtotal, beneficio elegible, receta requerida y total CLP calculado por Django.
3. Autoriza el contacto y confirma la selección y el total. Pulsa **Continuar al pago**. También se conserva la alternativa de solicitar cotización sin pagar.
4. **Finalizar compra** muestra los tres pasos, el folio, la referencia, el total exacto y los datos bancarios inoperativos, con botones para copiar. Nunca se muestran instrucciones operativas de pago real.
5. En **Subir comprobante de transferencia**, selecciona JPG, JPEG, PNG o PDF de hasta 5 MB. Se muestran el nombre y la vista previa de imágenes; puedes reemplazarlo antes del envío.
6. Pulsa **Enviar comprobante de pago**. Django valida el contenido real, conserva el archivo en almacenamiento privado y cambia el pago a Comprobante enviado, pendiente de revisión.
7. Consulta **Mis pedidos → Mis compras y pagos**. El comprobante no aprueba automáticamente el pago. Si es rechazado, revisa las observaciones y envía un archivo corregido.

## Revisión del personal

En **Pagos y comprobantes**, busca el pago por cliente, RUT, folio, referencia, fechas o estado. Abre el comprobante privado y utiliza Aprobar pago, Rechazar pago o Solicitar nuevo comprobante. Los botones seleccionan una decisión que requiere observaciones y confirmación antes de guardarse. La aprobación académica exige comprobar el monto de la evidencia ficticia; crea una sola orden. Las revisiones y los comprobantes anteriores se conservan.

Los pagos reales permanecerán deshabilitados hasta una aprobación empresarial y un procedimiento de contraste bancario efectivo.

## Integridad y seguridad

- `POST /api/checkout-payment/` requiere sesión Django, CSRF, ficha activa y confirmación explícita; limita los intentos de checkout.
- El servidor utiliza los precios del catálogo y los beneficios vigentes y validados. `expected_amount` solo permite comprobar que el total mostrado no cambió: no establece el precio.
- Una transacción y el bloqueo de cliente, productos y existencias conservan una sola solicitud/cotización/pago para la misma referencia de reintento. La referencia del intento se conserva durante la sesión de pestaña, sin guardar datos personales en el almacenamiento de interfaz.
- La confirmación reserva unidades según la política existente. El carrito no descuenta stock físico. La salida ocurre durante la entrega; una cancelación autorizada libera reservas. Se conservan las comprobaciones de concurrencia e idempotencia previas.
- `GET /api/purchases/<id>/` permite retomar un pago revisado, exclusivamente a su propietario o personal autorizado.
- La evidencia usa `PaymentVoucher.file` y el almacenamiento privado existente. En el perfil académico de alwaysdata permanece fuera de estáticos y código. Su descarga requiere sesión y propiedad o permiso de revisión; las respuestas privadas no se cachean.
- Tablas reutilizadas: `gestion_inquiry`, `gestion_purchaseline`, `gestion_quote`, `gestion_quoteline`, `gestion_transferpayment`, `gestion_paymentvoucher`, `gestion_paymentreview`, `gestion_stockreservation`, `gestion_stockmovement`, `gestion_order` y `gestion_audit`.

## Verificación reproducible

Ejecuta las pruebas Django de `gestion.test_checkout` y la suite completa antes de publicar. La revisión funcional debe empezar en el catálogo y pasar por el botón de pago del carrito, sin crear cotizaciones manualmente mediante herramientas externas. Comprueba rechazo, reenvío, aprobación, persistencia al volver a iniciar sesión y ausencia de órdenes duplicadas. Usa únicamente datos ficticios.

Antes de aplicar la migración 0016, respalda MariaDB y revisa `migrate --plan`. Publica estáticos en una nueva raíz versionada, conserva la anterior, recarga WSGI y verifica los archivos servidos y el recorrido sobre HTTPS.
