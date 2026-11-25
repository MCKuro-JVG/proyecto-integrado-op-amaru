# Dos QR por convenio o sindicato

Cada organización conserva su código manual y dispone además de **dos enlaces independientes** en **Códigos QR de atención**. Se accede desde Convenios, Sindicatos o el panel del representante. Los botones permiten mostrar, ampliar, descargar, copiar e imprimir cada QR. Solo el personal con permiso de modificar la organización puede regenerarlo, revocarlo o habilitarlo; el representante comparte únicamente los de su organización.

## Registro de trabajador

El primer QR abre `/app/registro_trabajador.html?qr=<identificador>`. La organización se resuelve en Django: el visitante no la selecciona ni puede cambiarla enviando otro identificador. Se solicitan nombre, RUT chileno válido, correo, teléfono, calidad de titular/carga cuando se permita y aceptación de privacidad.

El resultado es una **solicitud de vinculación de trabajador**, pendiente de verificar identidad y pertenencia. Se guarda inmediatamente y aparece en el listado y los contadores de la organización. No se activa ningún beneficio, cuenta ni acceso al catálogo minero por conocer el QR.

- Convenio tradicional: `gestion_inquiry`, con `kind=registro`, `origin=qr_worker`, `agreement_id` y `verification_state=pendiente`. El listado utiliza esa relación existente; no hay una tabla nueva de trabajadores de convenio.
- Sindicato: además se crea `gestion_unionmembership`, con `state=pending`, `origin=qr_worker` y relación con `gestion_union`. La solicitud apunta a ella mediante `union_membership_id`.
- Una ficha `gestion_client` anterior no se sobrescribe ni se reclama por conocer su RUT. Un cliente autenticado puede identificar su propia ficha; cualquier vinculación posterior requiere el procedimiento autorizado.
- No se crea una cuenta ni se envía un correo en este formulario. No se piden contraseñas porque esta etapa es la solicitud de pertenencia. En sindicatos se utiliza después la invitación individual existente para que el titular establezca su acceso; si ya existe ficha, debe autenticarse como su propietario. Aceptar una invitación originada en QR mantiene la afiliación pendiente hasta revisión administrativa.
- Para un convenio tradicional, el revisor debe confirmar explícitamente que verificó la identidad. Solo después se vincula una ficha existente o se crea una nueva, con permisos de gestión de clientes. El registro de cuentas particular y su activación se conservan por separado.

Los beneficios y productos exclusivos siguen dependiendo de afiliación aprobada, convenio vigente y comprobaciones del backend.

## Consultas

El segundo QR abre `/app/consulta_convenio.html?qr=<otro-identificador>`. Muestra la organización, los beneficios autorizados para publicación y un formulario de consulta, orientación/cotización o solicitud de hora. Los enlaces al catálogo público se conservan; consultar por lentes mineros no expone el catálogo exclusivo.

Se guarda en `gestion_inquiry`, con `origin=qr_inquiry` y `agreement_id`. **No crea User, Client ni UnionMembership.** El personal consulta estas entradas en Solicitudes, filtradas por organización y con el origen visible. Los representantes no reciben acceso a estas consultas privadas por poder compartir el QR.

Solo se publican beneficios activos, dentro de sus fechas y con **Autorizado para publicación en QR de consultas** habilitado expresamente en Beneficios. Los anteriores quedan ocultos de manera predeterminada. Pedir una hora conserva el calendario y el control de cupos existentes; la confirmación indica recepción y no aprobación de una reserva.

## Persistencia y actualización

El formulario envía JSON a Django con CSRF, un desafío firmado vinculado al QR y un identificador de reintento. Django realiza las operaciones en una transacción con bloqueos de la organización. MariaDB conserva los registros y restricciones. El listado consulta el servidor cada 10 segundos mientras la pestaña está visible y no hay un diálogo abierto; también ofrece Actualizar registros. No depende de localStorage.

Un error de validación o de red conserva los campos y vuelve a habilitar el botón. Un reintento idéntico devuelve el registro ya recibido; cambiar el contenido de ese mismo reintento produce conflicto. Se rechazan duplicados de afiliación, RUT inválidos, cargas no admitidas, códigos revocados, organizaciones inactivas y convenios vencidos o aún no vigentes. La agenda mantiene su restricción única de fecha y hora.

`origin` diferencia `qr_worker`, `qr_inquiry`, `qr_general`, `manual_code`, `administrative` y `web`. Los QR generales y formularios manuales anteriores conservan su funcionamiento. Un cliente particular no se convierte automáticamente en afiliado activo.

## Seguridad y configuración

Los dos UUID se generan en el servidor y no contienen personas, contraseñas ni sesiones. Revocar uno no deshabilita el otro. Regenerarlo invalida el enlace anterior. Cada GET y POST público comprueba finalidad, token, estado y vigencia. Las imágenes y listados administrativos requieren sesión y autorización por organización.

La URL base procede de `ATTENTION_PUBLIC_BASE_URL` mediante la configuración existente. Se exige HTTPS y se rechaza localhost como destino del QR. En alwaysdata corresponde a `https://opticaamaru.alwaysdata.net`. No hay direcciones repetidas en JavaScript. La verificación local puede abrir el mismo camino en loopback, pero no constituye prueba de acceso externo ni escaneo físico.

El desafío dura una hora y evita envíos inmediatos automatizados. Se conservan honeypot, límite de envíos y throttling DRF. Para varios procesos en producción se necesita una caché de limitación compartida; la caché de memoria no ofrece un límite global entre procesos. No se declara protección completa contra bots.

## Migración y despliegue

`0017_organization_qr` amplía Agreement, Inquiry, UnionMembership y AgreementBenefit, incorpora un índice de organización/origen y crea UUID distintos para los convenios anteriores. **No crea ni elimina tablas.** La base local conserva 49 tablas. Respalda cada base antes de migrar; la reversión del esquema no recupera registros nuevos sin un respaldo.

1. Revisar `migrate --plan` y guardar un respaldo privado de MariaDB.
2. Aplicar migraciones, ejecutar `check --deploy` y `configure_roles` con el perfil del hosting.
3. Preparar estáticos en una nueva `AMARU_STATIC_RELEASE`; no sobrescribir la versión que sigue sirviendo WSGI.
4. Activar esa versión y reiniciar el sitio desde Web → Sites. Comparar SHA-256 de los scripts y CSS públicos con los publicados.
5. Probar ambas URLs con Chrome, enviar únicamente datos ficticios y comprobar MariaDB y los listados.

El comando `seed_organization_qr_demo --academic --credentials-file <archivo-privado> --metadata-file <archivo-privado>` prepara un convenio ficticio y reutiliza un sindicato DEMO que ya esté activo. No firma documentos, no activa sindicatos ni cambia sus estados. Si falta uno, se detiene y debe seguirse el proceso administrativo habitual. Guarda la contraseña nueva del representante solo en el archivo privado; no restablece cuentas existentes.

## Recorrido de revisión

1. Iniciar sesión con una cuenta académica autorizada y abrir Convenios o Sindicatos.
2. Pulsar Códigos QR de atención en la organización ficticia elegida.
3. Abrir el QR de registro en otro navegador, completar datos ficticios y enviar.
4. Volver al listado visible: esperar como máximo un ciclo de 10 segundos o pulsar Actualizar registros. Abrir Ver registro. Debe estar pendiente.
5. Abrir el QR de consultas, enviar otra consulta ficticia y buscarla en Solicitudes. No debe haber generado un trabajador adicional.
6. Utilizar [las consultas de solo lectura](consultas_qr_organizaciones.sql) en la base seleccionada para mostrar las relaciones.
7. Revisar identidad y pertenencia con el proceso correspondiente; compartir individualmente una invitación cuando se prepare el acceso del titular. El QR compartido nunca sustituye esa invitación.

Las capturas, resultados de navegador, credenciales, referencias y respaldos permanecen en `.tools`, fuera de GitHub. El escaneo desde un teléfono real debe confirmarse por separado; decodificar la imagen o abrir el enlace en Chrome no demuestra ese paso.

`Abrir_QR_Organizaciones.cmd` vuelve a abrir los módulos de Convenios y Sindicatos del hosting, además de las organizaciones ficticias cuando el equipo conserva sus metadatos privados. No inicia Django, MariaDB ni túneles adicionales. La conexión de DBeaver se conserva localmente; el archivo de consulta no incluye credenciales.
