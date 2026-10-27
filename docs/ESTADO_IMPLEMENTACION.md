# Registro técnico de implementación — 25 de octubre de 2026

Este documento conserva los resultados de la implementación inicial. El estado posterior de R2, activado y verificado el 26 de octubre, está en [CLOUDFLARE_R2.md](CLOUDFLARE_R2.md). Para el traslado, la nueva verificación y la publicación oficial, consulte [FINALIZACION.md](FINALIZACION.md).

## Resultado y alcance verificado

El backend Django existente está conectado a **MariaDB 11.4.13** mediante **mysqlclient 2.2.7**. Se aplicaron las migraciones originales `0001`, `0002` y la nueva `0003` en una base nueva `opticas_amaru`. La conexión normal utiliza `amaru_app@127.0.0.1` con SELECT, INSERT, UPDATE y DELETE exclusivamente sobre esa base. Las migraciones y pruebas utilizan otro usuario restringido a las dos bases del proyecto.

Se instalaron DRF 3.16.1, django-storages 1.14.6 y boto3 1.43.118 en el entorno virtual Python 3.12.10 ya existente. Django 5.2.17 y las dependencias anteriores se conservaron. `pip check` no detectó incompatibilidades. `requirements-lock.txt` registra las versiones completas del entorno validado, incluidas herramientas de desarrollo.

**R2 no está verificado contra Cloudflare.** El documento proporcionado contiene ejemplos, no credenciales reales. La integración, los campos privados/públicos, las URLs firmadas, el comando de comprobación remota y la compensación de entregas están implementados. En este equipo `R2_ENABLED=False`: los archivos reales de las pruebas funcionales se almacenaron en carpetas privadas locales, con sus referencias en MariaDB. No se presenta ese resultado como subida a R2.

## Trabajo conservado

- Copia previa completa del backend y frontend en el archivo privado del proyecto, excluida de Git.
- Configuración PostgreSQL anterior conservada en el archivo privado, fuera de Git. Su clúster y sus archivos no se eliminaron ni migraron.
- Aplicación `gestion`, modelos de clientes/recetas/cotizaciones/OT/garantías/recepción/auditoría, formularios, plantillas, servicios y migraciones anteriores reutilizados.
- Las 15 interfaces HTML, los estilos naranjas, ilustraciones y funciones DEMO de `frontend_amaru` permanecen. El modo conectado utiliza esos HTML con otro motor JavaScript servido por Django.
- El hosting estático anterior y su publicación no se modificaron. Continúan como demostración independiente del servidor local.

## Archivos principales nuevos o adaptados

| Archivos | Cambio |
|---|---|
| `.gitignore` | Integra el archivo `git.gitignore` de Documentos y excluye archivos privados, entornos, medios, respaldos y bases. |
| `amaru/config/settings.py`, `.env.example`, `test_settings.py` | MariaDB, DRF, R2 privado por defecto, sesión, configuración de producción y pruebas aisladas. Los secretos reales permanecen en archivos ignorados. |
| `amaru/gestion/models.py`, migración `0003_*` | Catálogo, detalle de cotización, agenda/contacto, reserva única, diario de entrega, fechas, índices y restricciones. |
| `api.py`, `api_urls.py`, `serializers.py`, `errors.py` | Endpoints, validación, paginación, permisos, acceso propio y errores sin detalles de SQL/almacenamiento. |
| `services.py` | Conversión transaccional e idempotente; verificación de receta propia; entrega con PDF, firma, hash, bloqueo de OT y compensación de archivos. |
| `storage.py` | Destinos R2 separados, campos explícitos, nombres únicos y URLs privadas de 600 segundos. |
| `auth.py`, `views.py` | Límites de intentos en acceso API/HTML y auditoría de lectura de archivos privados. |
| `frontend.py`, `amaru/static/server.js`, `config/urls.py` | Interfaces actuales conectadas a la API, sesión real y CSRF; sin almacenar registros personales en localStorage. |
| `configure_roles`, `reconcile_deliveries`, `verify_r2` | Roles, revisión de intentos de entrega y prueba remota con archivos ficticios. |
| `seed_demo.py`, `admin.py` | Datos explícitamente ficticios, catálogo y administración. Contraseñas fuera del README y del repositorio. |
| `test_api.py`, `tests.py`, `browser_integration.py` | Pruebas de API, permisos, integridad, errores, concurrencia y recorridos en Chrome. |
| `Iniciar_Backend_Amaru.*`, `.run/Amaru_Django.run.xml`, README | Inicio Windows/PyCharm, puerto 8001 y documentación del equipo. |

## Tablas y diseño

MariaDB contiene **27 tablas**, todas comprobadas con motor InnoDB y colación utf8mb4. Diecisiete pertenecen a `gestion`:

`agreement`, `appointmentreservation`, `audit`, `client`, `consent`, `deliveryattempt`, `inquiry`, `inventory`, `order`, `prescription`, `product`, `quote`, `quoteline`, `receipt`, `request`, `siteconfiguration` y `warranty` (con prefijo `gestion_`). Las restantes corresponden a usuarios, permisos, grupos, sesiones, administración y migraciones de Django.

Las relaciones y restricciones se detallan en [ARQUITECTURA.md](ARQUITECTURA.md). Se conservan claves foráneas y relaciones 1:1 previas; se agregan índices por estado/fecha e historial por entidad. Se usan transacciones y bloqueos al convertir cotizaciones, modificar estados, reservar horarios y entregar lentes. Los datos históricos no se exponen a eliminación desde la API; clientes y productos se desactivan.

Se ejecutó `EXPLAIN` sobre cuatro consultas reales con datos ficticios:

| Consulta | Índices seleccionados en esta base de prueba |
|---|---|
| Cliente por RUT exacto | `rut`, acceso `const`. |
| OT por estado y fecha | `order_status_date`, acceso `ref`. |
| Pedidos del usuario cliente | `username`, `user_id` y FK de cliente en orden. |
| Auditoría de una ficha | `audit_record_date`, acceso `ref`. |

Esto verifica la estructura y planes de esas consultas; no demuestra rendimiento con volúmenes productivos. No se ejecutaron pruebas de carga ni estrés.

## Pruebas ejecutadas

| Verificación | Resultado observado |
|---|---|
| Suite Django contra MariaDB temporal | **49 pruebas aprobadas**, 195,928 segundos. Base `test_opticas_amaru` creada y eliminada por Django. |
| Permisos y autenticación | Inicio/salida de sesión, CSRF, límite de intentos, denegación anónima, taller sin recetas y cliente sin pedidos ajenos. |
| Persistencia e integridad | Altas, consultas, actualización/desactivación, RUT inválido/duplicado, FK protegidas, cotización sin aprobación y receta de otro cliente rechazadas. |
| Agenda | Registro público, reintento sin duplicado, conflicto de horario, liberación por cancelación y rechazo de reapertura sobre horario ocupado. |
| Entrega | Vista previa sellada, aceptación, firma, PDF, hash, entrega y bitácora; bloqueo de revisión desactualizada y firma vacía. |
| Fallo de archivos | Fallo de almacenamiento simulado: orden permanece disponible, recepción se revierte y firma huérfana se limpia. |
| Entrega simultánea | Dos conexiones MariaDB sobre la misma OT producen una única recepción y el mismo identificador. |
| Chrome, recorrido funcional | Formulario público → personal; registro de cliente/receta; cotización → OT → retiro con firma → documento persistido. |
| Chrome, pantallas | **35 comprobaciones**: cinco etapas funcionales y las 15 pantallas a 1366×900 y 375×812. Sin errores JavaScript ni desbordamiento horizontal detectado. |
| Chrome, perfil cliente | Solo su pedido, historial autorizado, navegación sin menú administrativo y sin datos en localStorage. |
| Persistencia desde otra conexión | Cliente, receta, cotización, OT entregada, solicitud y PDF recuperados; SHA-256 del PDF coincide. |
| R2, prueba local | Configuración de buckets separados y generación de URL S3 firmada de 600 segundos con credenciales ficticias, sin conexión a Cloudflare. |
| R2, prueba remota | **Pendiente**. `verify_r2` informó que R2 no está habilitado; no se simularon resultados remotos. |
| Dependencias y esquema | `pip check` sin incompatibilidades; `makemigrations --check --dry-run` sin cambios pendientes; `manage.py check` sin errores. |
| Preparación de Git | Revisión de archivos seleccionados y búsqueda de coincidencias con secretos locales: sin coincidencias; bases, medios, `.env` y respaldos excluidos. |

Los registros técnicos y capturas de las ejecuciones están en `logs/` y `.tools/backend-qa/`, fuera del repositorio. Se utilizaron exclusivamente datos ficticios. Las pruebas aisladas no constituyen certificación de seguridad ni de producción.

## Operaciones reales y pendientes

Ya utilizan MariaDB: clientes, recetas y referencias privadas, cotizaciones, conversión a OT, avance, recepción, documentos, garantías, inventario, catálogo, contactos/agendas, roles/sesiones y auditoría. Las API permiten consultar los productos de cotización; su detalle de catálogo se incorpora mediante `/api/quotes/<id>/items/`, disponible antes de aprobar la cotización. El formulario visual conserva las especificaciones de lentes del proyecto anterior.

Continúan siendo académicos: catálogo y precios ficticios, capacidad/horarios de agenda, datos de presentación, garantía pendiente de términos oficiales, firma simple sin certificación avanzada, ausencia de envío de mensajes y la versión estática con localStorage. No hay integración con OptiClick ni MongoDB.

Pendientes indispensables:

1. Configurar credenciales y buckets reales R2; ejecutar y aprobar `verify_r2`, comprobar privacidad desde Cloudflare y repetir la entrega contra R2.
2. Confirmar condiciones de garantía, mecanismo de firma y diferencia entre vigencia de 365 días del informe y año calendario del código conservado.
3. Revisar datos PostgreSQL/archivos previos y preparar una migración con respaldo y conciliación antes de mover información histórica.
4. Crear cuentas personales del equipo en lugar de compartir cuentas de presentación.
5. Para publicar la aplicación conectada en internet: infraestructura con Python/MariaDB, HTTPS, configuración de producción, secretos, caché compartida, respaldos y políticas de documentos. El hosting estático anterior no ofrece esa ejecución.
6. Revisar mejoras posteriores: búsqueda/paginación de selectores grandes (los formularios iniciales muestran la primera página de clientes/recetas/convenios), edición visual de múltiples líneas del catálogo, historial de inventario completo y automatización operativa de conciliación y respaldos.

**No se declara terminada la integración completa Django + MariaDB + R2 mientras la conexión remota de R2 siga pendiente.**

## GitHub y publicación

Se creó el commit local inicial `a4edb65` con 91 archivos revisados, en `main`, y el remoto `origin` apunta al repositorio oficial. La consulta remota confirmó el repositorio público inicialmente vacío. La publicación no se pudo completar:

- Git CLI no encontró credenciales para HTTPS en el entorno de ejecución sin interacción.
- La conexión GitHub devolvió **403 — Resource not accessible by integration** al intentar crear el primer archivo. No se publicó una copia parcial.

El estado local posterior se consulta con `git log -1`. Una vez autorizada una identidad con escritura en el repositorio, ejecutar desde la raíz:

```powershell
git push -u origin main
```

No se utilizó force push ni se reescribió historial compartido. Antes de repetir la publicación, comprobar que el remoto no recibió cambios del equipo. Las credenciales de GitHub no deben copiarse a `.env` ni incluirse en la URL del remoto.
