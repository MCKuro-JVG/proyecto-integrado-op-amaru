# Sindicatos, trabajadores y retiro de lentes

## Roles y alcance

| Perfil | Operaciones |
| --- | --- |
| Administrador | Crea y suspende sindicatos. Asocia versiones privadas del convenio, revisa la firma y activa el sindicato. Supervisa afiliaciones y recuperaciones. Mantiene la administración general de usuarios y permisos. |
| Vendedor | Conserva las operaciones del grupo Personal de atención, incluidas cotizaciones, órdenes, recetas autorizadas y recepciones. Valida, reemite y revoca códigos de retiro. |
| Cliente | Consulta catálogo general, recetas, solicitudes, cotizaciones, pedidos y documentos propios. El registro público requiere activación administrativa. |
| Sindicato | Revisa y firma su convenio. Administra los datos administrativos y las afiliaciones de su organización. Puede iniciar la recuperación de una cuenta mediante Ópticas Amaru. |
| Trabajador asociado | Utiliza una cuenta Cliente. La afiliación activa y vigente habilita el catálogo minero y su uso en solicitudes. |
| Taller | Conserva su perfil técnico auxiliar para órdenes, inventario y garantías. |

Los convenios y representantes anteriores conservan su circuito de validación. Los sindicatos registrados en el nuevo módulo usan invitaciones individuales.

## Demostración académica

1. Entra como administrador y abre **Gestión de sindicatos** en `/app/sindicatos.html`. Registra un sindicato ficticio, su vigencia y un correo institucional dedicado. Guarda el enlace mostrado y entrégalo directamente al representante.
2. Adjunta un PDF de prueba autorizado y rotulado **Demostración académica**. Con la invitación, el representante establece su propia contraseña. Inicia sesión en `/app/sindicato.html` y consulta **Mi convenio**. En **Firmar convenio** confirma la aceptación de la versión revisada.
3. Vuelve al panel de administración, abre el PDF privado, comprueba la versión y usa **Activar sindicato**. Registra una referencia breve de la revisión.
4. Desde **Crear trabajador**, el representante ingresa datos ficticios y entrega el enlace individual. Si ya existe ficha, el trabajador entra con su cuenta personal desde el mismo enlace y acepta la vinculación. Ópticas Amaru verifica la identidad y la aprueba. Las fichas sin cuenta utilizan el registro público verificado primero.
5. El trabajador inicia sesión y abre **Lentes mineros**. En el administrador de catálogo, un vendedor autorizado puede crear un producto ficticio marcado como **Exclusivo de lentes mineros**. Usa el carrito para enviar una cotización. Adjunta una receta ficticia si el producto la requiere.
6. El vendedor abre **Solicitudes recibidas**, prepara una cotización y, con aprobación y receta vigente, crea la orden. Al marcar **Disponible para retiro**, el cliente ve **Ver código de retiro** en **Mis pedidos**.
7. El vendedor abre `/app/retiro.html`, busca el código y verifica la identidad o autorización. Confirma la recepción con el documento y la firma simple. El pedido pasa a **Entregada** y el código queda consumido en la misma transacción.
8. Para revisar en DBeaver, consulta las tablas `gestion_union`, `gestion_uniondocument`, `gestion_unionmembership`, `gestion_accessinvitation` y `gestion_pickupcode`. Relaciona la afiliación con `gestion_client` y el retiro con `gestion_order`, `gestion_receipt` y `gestion_audit`. Las invitaciones y los códigos se visualizan mediante sus estados, identificadores y fechas.

## Credenciales y baja

Las invitaciones vencen en 24 horas por defecto. Se guardan por hash y solo se pueden utilizar una vez. El panel entrega el enlace individual para distribución privada. La reemisión invalida la invitación anterior. `UNION_INVITE_HOURS` permite ajustar la vigencia entre 1 y 72 horas.

Al desactivar a un trabajador se revoca su afiliación y se invalidan las invitaciones vigentes. Su cuenta personal, pedidos, recetas y comprobantes se conservan. Para reincorporarlo, reemite la invitación y solicita una nueva aceptación. Las recuperaciones de contraseña de cuentas personales requieren verificación del titular por Ópticas Amaru, que entrega el enlace directamente a la persona verificada. La cuenta institucional puede recuperar su acceso mediante una nueva invitación de administración.

Los códigos de retiro se emiten en el servidor al pasar la orden a **Disponible para retiro**. `PICKUP_CODE_HOURS` se configura entre 1 y 720 horas y tiene un valor inicial de 168 horas. La comprobación del vendedor genera una autorización temporal asociada a su sesión de trabajo y a esa emisión. Las órdenes de sindicatos administrados requieren esa validación para completar el comprobante. El código también está disponible en órdenes particulares como apoyo al retiro.

## Firma, documentos y decisiones pendientes

La aceptación académica registra la cuenta autenticada, identidad declarada del representante, organización, versión, fecha, texto de aceptación y SHA-256 del PDF original. El archivo queda en almacenamiento privado y el proceso verifica su integridad antes de firmar y activar. Los convenios e imágenes mineras usan almacenamiento privado. El hosting Free usa su almacenamiento privado local con datos ficticios.

Antes de un uso comercial, Ópticas Amaru debe validar la representación y su alcance, el texto contractual autorizado, el mecanismo de autenticación y aceptación, la conservación de evidencias y las exigencias de firma aplicables a cada convenio. La demostración registra una firma electrónica simple y requiere revisión jurídica antes de aplicarla a convenios reales. [Ley 19.799 en la Biblioteca del Congreso Nacional](https://www.bcn.cl/leychile/navegar?idNorma=196640)

También quedan por definir el canal institucional para entregar invitaciones, la política de verificación y retiro por terceros, las vigencias y los precios o beneficios comerciales. El flujo registra solicitudes y cotizaciones académicas sin cobro.
