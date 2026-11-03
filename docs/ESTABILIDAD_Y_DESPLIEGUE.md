# Disponibilidad, servicios y publicación estable

Revisión: 2 de noviembre de 2026. Se conserva el proyecto existente; no hay cambios de esquema ni migraciones nuevas en esta etapa.

## Qué está comprobado y qué falta

| Componente | Estado real |
|---|---|
| Registro QR previo | Se encontró una solicitud de atención en la base QR, con origen QR y estado Nueva. Tiene horario relacionado y no tiene ficha de cliente porque se envió como agenda. El detalle personal está solo en el informe local privado. |
| Bases | `opticas_amaru` y `opticas_amaru_qr_demo` permanecen separadas, con 27 tablas cada una. No se copiaron registros entre ellas. |
| MariaDB | Servicio Windows instalado y comprobado con cuenta LocalService. |
| Origen de atención | Servicio Windows con Waitress, salud SQL, bloqueo de instancia, recuperación y cierre controlado. Sin temporizador de dos horas. |
| Dominio y túnel administrado | La cuenta consultada no devolvió zonas ni túneles administrados. No se creó un dominio, DNS ni túnel vacío. |
| URL definitiva | Pendiente de disponer de dominio o seleccionar un alojamiento con dirección propia. |
| Publicación estática anterior | Sigue siendo una demostración independiente; no ejecuta MariaDB ni este backend. |
| R2 | Conserva su integración anterior para archivos. No proporciona ejecución Django ni sustituye Tunnel. |

El informe personal y las consultas específicas están en `.tools/stability`, excluido de Git. No se crean ni actualizan fichas para aparentar que un formulario de agenda fue un registro de cliente. Las consultas de búsqueda fueron de solo lectura.

## Servicios Windows instalados

| Servicio | Ejecución y responsabilidades |
|---|---|
| `OpticasAmaruDatabase` | MariaDB 11.4.13 con el directorio de datos y configuración existentes, puerto 3306 en loopback. |
| `OpticasAmaruAttention` | Supervisor Python y Waitress, puerto 8005 en loopback, base QR aislada y frontera pública sin administración. Depende del servicio Database. |

Ambos usan LocalService, inicio automático diferido y recuperación de Windows: reinicio tras 15, 30 y 60 segundos, con restablecimiento del contador tras una hora. WinSW 2.12.0 NET461 se descargó del repositorio oficial y se conserva privadamente; el preparador verifica su hash. No se usa LocalSystem ni se guarda una contraseña de Windows en la configuración.

Se restringieron archivos de credenciales al propietario, administradores y SYSTEM, concediendo únicamente los accesos requeridos a los SID de servicio. El servicio web lee su entorno QR, no el entorno de la aplicación habitual. MariaDB tiene acceso a su directorio de datos. El cierre controlado utiliza una cuenta SQL exclusiva con permiso SHUTDOWN; no usa root como cuenta de aplicación. Se conserva el acceso del propietario. No se modificaron suspensión, actualizaciones, firewall ni políticas globales de PowerShell.

La instalación necesitó elevación aceptada por el propietario. Windows PowerShell no ejecutó el primer intento por su política predeterminada; se utilizó PowerShell 7 sin cambiar la política global. Los archivos del instalador permiten previsualizar; no instalar automáticamente al clonar.

## Puertos y separación

| Puerto | Uso | Acceso |
|---|---|---|
| 3306 | MariaDB del proyecto | Loopback; no publicado en Internet. |
| 8001 | Backend habitual de desarrollo | Local; no es el servidor público permanente. |
| 8003 | Personal de demostración con Waitress | Local y autenticado. |
| 8004 | Demostración anterior mediante Quick Tunnel | Temporal y separada del origen estable. |
| 8005 | Origen público estable con Waitress | Loopback, preparado para el futuro túnel administrado. |

El panel local permite consultar las solicitudes guardadas en la base QR. El perfil estable rechaza otra base, DEBUG activo, hostnames no permitidos y rutas privadas. Sin dominio configurado admite únicamente hosts locales para las comprobaciones previas; no inventa un hostname público.

## Supervisión y seguridad

`attention_runtime.py` mantiene una sola instancia por puerto mediante bloqueo de archivo. Comprueba `/healthz/` periódicamente; la vista realiza SELECT 1 y devuelve únicamente `ok` o `unavailable`, sin nombres de bases, usuarios ni datos personales. Reinicia el trabajador si termina o acumula fallos, con espera progresiva. El cierre deja de aceptar conexiones y espera a los trabajos activos antes de finalizar. El reinicio automático de MariaDB corresponde a Windows; el supervisor web no fuerza reinicios del motor SQL por una respuesta de salud fallida.

El origen configura cookies seguras, CSRF, hosts y orígenes HTTPS concretos, HSTS y encabezados de seguridad. Solo confía en el esquema reenviado por el proxy loopback. El perímetro no permite login público, panel, clientes, órdenes, lectura de solicitudes ni administración. Las solicitudes públicas conservan las validaciones, CSRF, límite de envíos, campo señuelo e idempotencia existentes.

Los logs rotan y filtran detalles de solicitudes y excepciones. Se separaron los archivos operativos de los informes personales. Los límites de envíos son de un único proceso en memoria: un despliegue con varios procesos requerirá caché compartida. Esto no constituye una certificación de seguridad ni un despliegue de producción terminado.

`check --deploy` del perfil estable no informó incidencias relevantes. Se silenció explícitamente W021 porque no se solicita incluir en listas preload un dominio que todavía no se administra. No se cambió DEBUG del entorno privado de desarrollo para ocultar advertencias.

## Pruebas realizadas

- 85 pruebas Django sobre la base MariaDB reservada de pruebas: todas aprobadas. Incluyen las 80 anteriores y cinco pruebas de salud, frontera pública, servicios y privacidad de logs.
- Ocho comprobaciones del flujo QR en Chrome: URL HTTPS temporal, formulario móvil simulado, persistencia, consulta del personal, rechazo de datos inválidos y rutas privadas.
- Instalación y arranque de ambos servicios: Running, Automatic y LocalService comprobados.
- Reinicio controlado del servicio de atención: proceso cambiado y salud recuperada, sin detener MariaDB.
- Fallo controlado del trabajador Waitress: proceso reemplazado y salud recuperada. Se detectó y corrigió un fallo del contador de reinicios; la prueba posterior verificó contador y recuperación.
- Reinicio controlado del trabajador: salud recuperada después del cierre ordenado.
- Restauración de un respaldo QR en una base nueva privada: las 27 tablas y sus cantidades de registros coinciden. La solicitud revisada se conserva. No se restauró encima de las bases originales.
- Migraciones sin operaciones pendientes y `pip check` sin incompatibilidades detectadas.

No se reinició Windows para probar el arranque después del inicio del sistema. Se verificó la configuración automática, sus dependencias y los arranques/reinicios concretos descritos. No se provocó una caída abrupta de MariaDB para no arriesgar datos. No se probó un dominio estable inexistente. El envío físico del QR fue realizado por el propietario; las verificaciones automatizadas no acreditan otra red móvil ni un nuevo escaneo realizado por el agente.

## Respaldos

`python scripts/backup_attention.py` crea un volcado QR con manifiesto SHA-256. `--env-file amaru/.env` permite respaldar la base habitual con sus credenciales locales. La contraseña viaja en el entorno privado del proceso, nunca en los argumentos. Los archivos parciales no se presentan como respaldos completos. Se guardaron respaldos de ambas bases antes de convertir MariaDB a servicio.

La prueba de restauración dejó una copia de verificación privada en otra base. No es una base pública ni un origen para Django. Los volcados, manifiestos detallados y resultados personales no se publican.

Para una operación prolongada falta acordar conservación, programar copias con una cuenta apropiada y mantener otra copia cifrada fuera de este computador. La existencia de un volcado local no protege frente a pérdida completa del disco o ransomware. No se configuró almacenamiento externo ni una tarea periódica sin definir sus permisos y destino.

## Conseguir una dirección fija

La cuenta de Cloudflare fue comprobada con cf 1.0.0-beta.23; el agente observado es cloudflared 2026.10.7. R2 no aporta un dominio para ejecutar Django. Quick Tunnel cambia de dirección y continúa siendo exclusivamente demostrativo.

Para usar un subdominio estable:

1. Utilizar un dominio que ya pertenezca al equipo o registrar uno con autorización. Comprobar su titularidad; no se comprobó la disponibilidad de ningún nombre comercial concreto.
2. Incorporarlo a Cloudflare y verificar que la zona esté activa.
3. Crear un túnel administrado con cf y una ruta del hostname real hacia `http://127.0.0.1:8005`, con regla final de rechazo.
4. Crear el registro DNS correspondiente y comprobar HTTPS. No exponer directamente 3306, 8001 o el panel del personal.
5. Guardar el token de ejecución en un archivo privado y restringirlo al servicio del conector. cloudflared soporta TUNNEL_TOKEN_FILE; no colocar el token en argumentos, Git ni el navegador. La sesión OAuth del usuario no debe ser la credencial permanente de un servicio.
6. Configurar `ATTENTION_PUBLIC_BASE_URL` con el origen HTTPS realmente aprobado, reiniciar el perfil correspondiente y comprobar el formulario, el QR y la persistencia desde fuera del equipo.
7. Instalar y verificar el servicio del conector con esa configuración. Todavía no se instaló porque faltan dominio y túnel.

No existe una URL definitiva asignada por esta revisión. El QR usa la variable central y conserva su ruta funcional. No se sustituyó el dominio por uno inventado. Los enlaces de demostración anteriores pueden caducar y no deben imprimirse como material permanente.

## Alternativas de disponibilidad y presupuesto

| Alternativa | Coste orientativo consultado | Ventajas y límites |
|---|---|---|
| Computador actual y dominio propio | Equipo/conexión existentes; dominio .cl en NIC Chile: CLP 9.990 por un año | Reutiliza servicios locales; depende de electricidad, suspensión, conexión y actualizaciones del equipo. Tunnel no mantiene el computador encendido. |
| DigitalOcean Basic Linux, 2 GiB | USD 12/mes, 1 vCPU y 50 GiB SSD; copias y otros cargos aparte | Permite conservar Django y MariaDB en un VPS. Requiere administración del sistema, parches y respaldos. |
| AWS Lightsail Linux, 2 GB con IPv4 | USD 12/mes, 2 vCPU y 60 GB SSD; copias, impuestos y cargos adicionales según uso | Presupuesto inicial comparable y un servidor separado del computador personal. Sigue siendo una sola instancia, sin alta disponibilidad automática. |
| Plataforma con subdominio propio, por ejemplo Render | Cotizar web, base privada y disco según plan | Proporciona dirección onrender.com sin registrar dominio. Mantener MariaDB en un contenedor privado persistente requeriría validación específica; no se hizo una migración ni se presupone un servicio MariaDB gestionado. |

Para un proyecto académico pequeño se recomienda evaluar un VPS Linux de 2 GB y un dominio propio si se necesita mantener Django + MariaDB sin cambiar la arquitectura. Son precios orientativos consultados, no una contratación ni una garantía de disponibilidad. Deben añadirse respaldos externos, mantenimiento y presupuesto de almacenamiento/transferencia aplicable. Una sola VM o este computador sigue siendo un punto único de fallo.

## Abrir y operar

- `Abrir_Revision_Estable.cmd`: reutiliza el origen instalado y abre PyCharm, DBeaver y las vistas disponibles. No crea un Quick Tunnel nuevo.
- `Iniciar_Origen_Estable.cmd`: comprueba o inicia el origen, respetando un servicio existente; no crea un proceso paralelo si Windows lo tiene registrado.
- `python scripts/attention_runtime.py status`: muestra salud y estado operativo sin secretos.
- `python scripts/backup_attention.py`: respaldo local QR.
- `pwsh -File deploy/windows/Install-AmaruServices.ps1`: previsualización de instalación, sin cambios de servicios.

Para otro equipo es necesario configurar credenciales propias y MariaDB; el instalador corresponde a la instalación portable documentada y exige sus archivos locales. Preparar el envoltorio con `python scripts/fetch_service_wrapper.py`. Revisar la previsualización como propietario antes de elevar. La instalación efectiva requiere `-Apply -ApproveDatabaseStop`, consentimiento del propietario y permisos de administrador. No sobrescribe servicios previos ni ejecutables activos de otra versión. Las configuraciones y claves locales permanecen fuera del repositorio.

## Referencias oficiales

- [Cloudflare Tunnel y dominio requerido](https://developers.cloudflare.com/tunnel/get-started/)
- [Parámetros y token en archivo](https://developers.cloudflare.com/tunnel/reference/run-parameters/)
- [WinSW 2.12 y configuración](https://github.com/winsw/winsw/blob/v2.12.0/doc/xmlConfigFile.md)
- [NIC Chile: tarifas](https://www.nic.cl/dominios/tarifas.html)
- [DigitalOcean: precios](https://www.digitalocean.com/pricing/droplets)
- [Lightsail: paquetes](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-bundles.html)
- [Render: servicios web y subdominio](https://render.com/docs/web-services)
