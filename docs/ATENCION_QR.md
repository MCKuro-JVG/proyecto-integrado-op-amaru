# Atención QR y demostración conectada a MariaDB

Actualización: 2 de noviembre de 2026.

## Implementación conservada

Se trabajó sobre el proyecto existente y su historial Git. Antes de modificar el esquema se guardaron un archivo de la versión anterior y un respaldo SQL privado en `.tools/attention`. La migración `0004_attention_qr` es aditiva: amplía `gestion_inquiry` con origen, RUT de registro y relación opcional con cliente, y agrega el tipo de solicitud de registro. No borra tablas ni datos. La base habitual conserva 27 tablas.

R2 ya estaba conectado y verificado en la etapa anterior. Esta etapa no sustituye su configuración ni modifica los buckets. La demostración remota desactiva R2 y no utiliza documentos de clientes reales.

## Recorrido funcional

1. En Resumen o Solicitudes recibidas, un trabajador autorizado pulsa **Mostrar QR de atención**.
2. El diálogo muestra el QR, su URL, la advertencia de demostración, copia de enlace, ampliación, descarga PNG e impresión.
3. El QR abre `/app/formulario_remoto.html?origen=qr`. Solo contiene una URL pública, sin RUT, claves ni sesión del trabajador.
4. El visitante elige atención, contacto, orientación o registro. Ingresa nombre, teléfono, correo opcional, servicio, motivo y consentimiento de contacto. El RUT se exige únicamente para registro; fecha y horario, únicamente para agendamiento. Las observaciones pueden agregarse al motivo.
5. Django valida el envío y guarda la información en una transacción MariaDB. La confirmación informa recepción para revisión, sin confirmar una reserva ni mensajes enviados.
6. El trabajador consulta **Solicitudes recibidas**: identificador, recepción, nombre, tipo, origen, estado y detalle. Puede filtrar por fecha y estado y actualizar el estado según sus permisos.

La procedencia QR identifica el enlace de entrada declarado; no acredita identidad ni demuestra por sí sola un escaneo físico.

## Entidades y reglas

| Operación | Tablas y comportamiento |
|---|---|
| Contacto u orientación | `gestion_inquiry`; no crea ficha de cliente. |
| Solicitud de hora | `gestion_inquiry` y `gestion_appointmentreservation`. La restricción de horario único impide reservas simultáneas del mismo espacio académico. |
| Registro con RUT nuevo | `gestion_inquiry` y `gestion_client`, relacionadas por clave foránea. La ficha queda inactiva para revisión, sin usuario y con consentimiento comercial falso. El personal revisa y activa la ficha desde su módulo. |
| Registro con RUT existente | Conserva íntegra la ficha anterior; asocia la nueva solicitud para revisión. La respuesta pública no revela si el RUT ya existía. |
| Auditoría | `gestion_audit` conserva las operaciones relevantes. No se convierte automáticamente la consulta pública en una solicitud de lentes de `gestion_request`. |

El consentimiento de gestión de la solicitud no modifica el consentimiento comercial o de posventa. Los datos recibidos se conservan en SQL; no dependen de localStorage. Repetir exactamente el mismo identificador de envío devuelve el resultado anterior; reutilizarlo con datos diferentes se rechaza. También se rechazan solicitudes equivalentes dentro de cinco minutos, salvo solicitudes cerradas/canceladas. El teléfono admite entre 8 y 15 dígitos y formatos habituales; el RUT se normaliza y valida con su dígito verificador. Se validan correo, longitudes, horarios, fechas y campos obligatorios en el backend.

Se mantiene CSRF incluso para el POST anónimo, un campo señuelo para robots y un límite de 15 intentos por diez minutos y dirección. El entorno temporal usa un proceso Waitress con caché en memoria compartida por sus hilos. Reiniciarlo reinicia el límite; producción requiere un almacenamiento de límites compartido y medidas de abuso adicionales según el tráfico.

## Separación de entornos

| Entorno | Dirección | Base | Exposición |
|---|---|---|---|
| Aplicación habitual | `http://127.0.0.1:8001/app/` | `opticas_amaru` | Solo computador local; conserva R2 y los módulos existentes. |
| Personal de demostración | `http://127.0.0.1:8003/app/` | `opticas_amaru_qr_demo` | Solo computador local, autenticado. |
| Formulario de demostración | URL HTTPS temporal mostrada en el QR | `opticas_amaru_qr_demo` | Cloudflare hacia Waitress en 127.0.0.1:8004. |

**Las solicitudes del QR temporal se ven en el panel del puerto 8003, no en la base habitual del puerto 8001.** Esta separación evita publicar los datos reales del proyecto. El panel normal puede mostrar ese mismo QR e indica expresamente a qué panel de demostración acudir.

La configuración pública exige DEBUG desactivado y el nombre exacto de la base ficticia. Usa el hostname concreto del túnel, el origen HTTPS correspondiente y cookies seguras. Solo confía en el esquema reenviado por el proxy local. El perímetro permite el formulario y sus recursos, catálogo ficticio, obtención de CSRF y envío de solicitudes. No publica login, administración, lectura de solicitudes, clientes, pedidos, documentos ni panel del personal. El usuario SQL del servidor público tiene únicamente CRUD sobre la base ficticia. Las conexiones de revisión son de solo lectura.

## Cloudflare y URL

La consulta de zonas con la CLI oficial `cf` no devolvió dominios administrados. No se registró ni compró un dominio ni se modificaron DNS o facturación. Se optó por Quick Tunnel. `scripts/attention_demo.py` inicia `cf tunnels quick-start http://127.0.0.1:8004` y registra la URL actual, el proceso y su vencimiento en un archivo privado. El QR la consulta centralmente; el supervisor cierra el túnel tras dos horas o al ejecutar el iniciador de detención.

Para un dominio estable se puede configurar `ATTENTION_PUBLIC_BASE_URL` en el entorno privado y desplegar un túnel administrado sobre un dominio propio previamente disponible. El QR no se genera si no existe una URL HTTPS adecuada. Reiniciar Quick Tunnel cambia el hostname: el diálogo QR abierto consulta la configuración cada diez segundos y actualiza el código si cambia el enlace. También se puede cerrar y volver a abrir el diálogo. No imprimir códigos temporales como material permanente.

| Servicio | Papel real |
|---|---|
| R2 | Almacena archivos; no ejecuta Django ni aloja MariaDB. |
| Tunnel | Hace accesible un servidor encendido. Se interrumpe al apagar el equipo o detener el proceso. |
| Alojamiento permanente | Debe ejecutar Django con WSGI/ASGI, conectar con MariaDB, gestionar HTTPS, respaldos, secretos, disponibilidad y monitorización. No se contrató ni migró a otro proveedor. |
| Hosting estático anterior | Sirve HTML/CSS/JS demostrativos; no ejecuta este backend ni actualiza su MariaDB. |

## Preparación reproducible

En este equipo ya existen los entornos privados, el usuario ficticio y las conexiones visuales. Para otro integrante:

1. Instalar las dependencias del README. Para las verificaciones y la presentación automatizada de Chrome, usar `amaru/requirements-lock.txt`; requiere Google Chrome instalado.
2. Crear **otra** base MariaDB llamada `opticas_amaru_qr_demo`, con InnoDB/utf8mb4. Utilizar una cuenta de migración privada para preparar el esquema y otra cuenta de aplicación con SELECT, INSERT, UPDATE y DELETE solo sobre esa base. Nunca copiar datos de la base habitual.
3. Copiar `amaru/attention-demo.env.example` a `amaru/.env.qr-demo`; completar una clave Django aleatoria y credenciales propias. No versionar ese archivo.
4. Con las credenciales de migración y `AMARU_ENV_FILE` configurado en el proceso, ejecutar `python amaru/manage.py migrate --settings=config.attention_demo_settings` y `configure_roles` con la misma configuración. El archivo usado puede ser otro entorno privado; el servidor usa `.env.qr-demo` con permisos CRUD.
5. Crear usuarios de demostración desde Django y asignarles los grupos apropiados. No distribuir contraseñas por Git. El iniciador de Chrome de este equipo lee sus credenciales ficticias desde un archivo privado; en otro equipo se puede iniciar sesión manualmente.
6. Instalar y autorizar la CLI oficial `cf`. Quick Tunnel no requiere comprar un dominio. El iniciador utiliza `cf` del PATH; este equipo conserva su ubicación en una configuración privada.
7. Preparar PyCharm con `.venv/Scripts/python.exe` y conectar DBeaver a la base ficticia mediante un usuario de lectura. Las conexiones y sus credenciales quedan fuera de Git.
8. Ejecutar `Iniciar_Atencion_QR.cmd`. El iniciador evita duplicar los puertos de los servicios y abre las aplicaciones instaladas. La ruta de PyCharm puede configurarse mediante `AMARU_PYCHARM`; las herramientas portables locales no se distribuyen en el repositorio.
9. Ejecutar `Detener_Atencion_QR.cmd` al terminar la exposición pública. Las solicitudes permanecen en MariaDB para revisión.

## Pruebas y evidencias

Se ejecutó la suite anterior y los nuevos casos de QR, validaciones, protección del RUT existente, duplicados, roles, CSRF y frontera pública. La suite completa sobre MariaDB descubrió **80 pruebas y las aprobó todas**, sin omisiones (925,469 segundos en esta ejecución, durante el inicio del IDE). Después del refuerzo de reintentos concurrentes se ejecutaron además las 21 pruebas de atención, todas aprobadas. El registro final queda en `.tools/attention/tests-release.log`. Las verificaciones de navegador están en `browser-result.json` y las del recorrido anterior en `browser-regression.log`. Las evidencias son privadas.

Se completaron 8 comprobaciones del nuevo flujo QR y 35 del recorrido anterior. `pip check` no detectó incompatibilidades; Django no detectó errores ni cambios de modelos sin migración.

El navegador de escritorio simuló una pantalla móvil de 390×844 y abrió la URL HTTPS externa. Se registró una ficha ficticia; el personal la vio, consultó su detalle y la volvió a consultar después de cerrar el contexto del navegador. Se comprobó por SQL la fila única, la relación con cliente, el origen QR y la ficha sin usuario ni consentimiento comercial. Se probaron el rechazo de datos inválidos, un reintento idempotente, la modificación indebida del mismo identificador y las rutas privadas no publicadas.

Se detectó y corrigió un error real: el buscador de estáticos con prefijo en Windows necesitaba normalizar los separadores de ruta. Se agregaron pruebas de CSS y bootstrap para evitar que se repita. El recorrido anterior de 35 comprobaciones pasó y mostró las 15 interfaces en escritorio y móvil, sin errores JavaScript.

El escaneo con un teléfono físico y el acceso mediante una red móvil distinta requieren confirmación del usuario. No se consideran aprobados solo por haber probado la URL desde Chrome en el mismo equipo.

## Archivos principales

- `gestion/attention.py`: configuración central, generación del QR y límite de envíos.
- `gestion/serializers.py`, `services.py`, `api.py`: validación, transacción, registro y consulta privada.
- `gestion/models.py`, migración `0004`: vínculo entre solicitud y ficha, origen y tipo de registro.
- `amaru/static/server.js`, `attention.css`: diálogo QR, formulario y solicitudes.
- `config/attention_demo_settings.py`, `attention_public_urls.py`, `gestion/attention_public.py`, `serve_attention_demo.py`: separación y servidor WSGI.
- `scripts/attention_demo.py`, `start_attention_review.py`, `open_review.py`, `show_attention.py`: inicio y presentación.

Quedan por confirmar las condiciones oficiales de garantía, el mecanismo definitivo de firma y la vigencia de recetas, como en las etapas anteriores. Esta funcionalidad no incorpora OptiClick.

## Referencias

- [Quick Tunnels y sus límites](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)
- [Cloudflare Tunnel](https://developers.cloudflare.com/tunnel/get-started/)
- [Waitress](https://docs.pylonsproject.org/projects/waitress/en/latest/)


## Entorno visual de este equipo

Se abrió PyCharm con el proyecto y se asignó el intérprete `.venv/Scripts/python.exe` registrado en el equipo. Quedaron accesibles models, api, serializers, services, settings, attention y server.js. El inicio original falló por un archivo `.port` inaccesible en la caché anterior: se usó un directorio de sistema nuevo y privado, conservando la caché y la configuración originales. Las herramientas privadas se excluyeron del índice local del proyecto.

DBeaver quedó abierto y conectado con dos conexiones de lectura: base habitual y QR DEMO. Se expandió la base ficticia y se visualizaron sus 27 tablas. Las consultas de `consultas_demostracion_qr.sql` permiten revisar los registros y las relaciones reales sin modificaciones.

Chrome quedó abierto en un perfil privado de presentación con el trabajador mostrando el QR, el formulario público y la lista de solicitudes. No se publican sesiones ni perfiles del navegador. El panel de solicitudes se actualiza con el botón correspondiente.
