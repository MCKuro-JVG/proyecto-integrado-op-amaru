# Cloudflare R2 — conexión y verificación

Actualización: 26 de octubre de 2026.

## Estado comprobado

La aplicación local en `http://127.0.0.1:8001/app/` utiliza Django, MariaDB y R2 real. `R2_ENABLED=True` en la configuración privada de este equipo. El servidor se reinició y `/api/session/` confirmó `storage: r2`. Se comprobó nuevamente el inicio de sesión, la API de clientes y la descarga autorizada de un comprobante histórico y del nuevo documento de prueba.

Esto conecta el almacenamiento de archivos en la nube; no publica Django ni MariaDB en Internet. El hosting estático anterior continúa siendo una demostración independiente. Cada integrante debe configurar sus propias variables privadas después de clonar el repositorio.

## Almacenamientos y permisos

| Destino | Contenido | Acceso |
|---|---|---|
| `amaru-publico` | Imágenes del catálogo | Dominio r2.dev habilitado para demostración académica. |
| `amaru-privado` | Recetas, firmas y comprobantes PDF | r2.dev deshabilitado y sin dominios públicos personalizados. |

La clave S3 del backend tiene lectura/escritura de objetos limitada a esos dos buckets. Se conserva solo en los archivos locales de entorno, ignorados por Git. Las credenciales no llegan al navegador. Django autoriza al solicitante antes de emitir una URL privada firmada de 600 segundos; quien posea el enlace podrá usarlo mientras esté vigente.

Se aplicaron las instrucciones oficiales de preparación: habilidades oficiales, autorización del MCP y CLI `cf` 1.0.0-beta.23. Las operaciones de Cloudflare se realizaron con `cf`, sin Wrangler. La activación inicial del servicio la completó el propietario en el panel. El error 10042 inicial quedó resuelto; no es un impedimento actual. No se modificaron DNS ni se contrataron servicios desde el proyecto.

## Conservación y migración de medios

Se inventariaron 11 archivos previamente referenciados en MariaDB, todos privados. Se copiaron con sus mismas claves y se comparó SHA-256 entre el origen local y R2: los 11 coincidieron. No se modificaron las referencias SQL ni se borraron los originales.

La entrega de prueba añadió tres archivos: receta ficticia, firma y PDF. También se conservaron copias locales para recuperación. La comprobación final verificó 14 archivos coincidentes. El respaldo de la configuración anterior permanece privado y fuera de Git.

## Pruebas realizadas

| Comprobación | Resultado observado |
|---|---|
| `verify_r2` contra Cloudflare y MariaDB | Subida pública y privada, referencias SQL, descarga S3, descarga pública, URL firmada y rechazo anónimo comprobados; archivos y filas temporales eliminados. Repetido con la configuración normal activada. |
| Privacidad del bucket | API de Cloudflare: acceso r2.dev privado deshabilitado y ausencia de dominios personalizados públicos. |
| Entrega completa desde Chrome | Contacto público, consulta del personal, cliente ficticio, receta, cotización aprobada, OT, disponibilidad, firma dibujada y entrega registradas. |
| Integridad del comprobante | PDF descargado desde R2 coincide con el SHA-256 guardado en MariaDB; OT entregada y diario de intento completo; auditoría presente. |
| Autorización | PDF accesible por personal autorizado; anónimo HTTP 403 y cliente ajeno HTTP 404, sin enlace privado en la respuesta. |
| Navegación | 35 comprobaciones: recorrido funcional y 15 interfaces en 1366×900 y 375×812; sin errores JavaScript ni desbordamiento detectados. Sin datos personales en localStorage. |
| Suite Django sobre MariaDB | 59 pruebas aprobadas, sin omisiones, en 282,577 segundos; base aislada `test_opticas_amaru`, eliminada al finalizar. Estas pruebas automatizadas no sustituyen la comprobación remota anterior. |
| Dependencias | `pip check`: sin dependencias incompatibles detectadas. |
| Django y migraciones | `manage.py check` sin incidencias; `migrate --plan` sin operaciones pendientes. |

El acceso S3 sin firma devolvió HTTP 400 con XML `InvalidArgument / Authorization`, mientras la descarga firmada del mismo objeto devolvió su contenido correcto. El verificador acepta ese rechazo específico; no interpreta cualquier error 400 o 404 como prueba de seguridad. La descarga pública necesitó un User-Agent identificativo de la aplicación; no se deshabilitaron controles de Cloudflare.

`verify_r2` ahora limpia independientemente cada objeto/fila que creó, informa fallos de limpieza y no anuncia éxito antes de completarla. Nueve pruebas adicionales cubren estos fallos y la interpretación de las respuestas de autorización. No imprime secretos ni URLs firmadas.

Se consultó `reconcile_deliveries` en modo de solo lectura: no mostró intentos antiguos pendientes. No fue necesario aplicar borrados ni alterar entregas existentes.

## Reproducción para el equipo

1. Preparar Django y MariaDB siguiendo el README; usar cuentas privadas independientes.
2. Completar localmente `amaru/.env`, utilizando `.env.example` como referencia.
3. Configurar los dos buckets con la separación indicada y una clave S3 limitada a sus objetos.
4. Definir `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_ENDPOINT_URL`, `R2_BUCKET_PUBLICO`, `R2_BUCKET_PRIVADO`, `R2_DOMINIO_PUBLICO` (sin protocolo) y `R2_URL_SECONDS=600`.
5. Antes de activar un equipo con medios locales existentes, respaldarlos, copiarlos conservando sus claves y comprobar hashes. No habilitar R2 dejando archivos referenciados únicamente en el disco local.
6. Ejecutar `python amaru/manage.py verify_r2` únicamente con configuración R2 preparada. Utiliza archivos ficticios y elimina sus filas y objetos temporales; conserva una entrada de auditoría.
7. Iniciar mediante la configuración habitual de PyCharm o `Iniciar_Backend_Amaru`; abrir `/app/` en el servidor local. Las credenciales no se distribuyen mediante Git.

Los inventarios, informes detallados, capturas, registros y respaldos de este equipo se mantienen en `.tools/cloudflare`, excluida de Git. No se publican medios, datos de clientes ni configuraciones privadas.

## Límites y decisiones pendientes

- El dominio público r2.dev corresponde a demostración; para producción se debe preparar un dominio y límites apropiados. Nunca habilitarlo en el bucket privado.
- La aplicación sigue siendo académica y local; no se ha preparado un despliegue de producción, monitorización ni estrategia completa de recuperación ante desastres.
- La firma continúa siendo electrónica simple demostrativa, pendiente de decisión definitiva de la empresa. Las garantías oficiales y la diferencia entre 365 días y un año calendario de vigencia de recetas siguen pendientes de confirmar.
- No hay integración con OptiClick ni incorporación de MongoDB.

## Referencias técnicas oficiales

- [Preparación para agentes](https://developers.cloudflare.com/agent-setup/prompt.md)
- [CLI cf](https://developers.cloudflare.com/cf/get-started/)
- [Credenciales de R2](https://developers.cloudflare.com/r2/api/tokens/)
- [Buckets públicos](https://developers.cloudflare.com/r2/buckets/public-buckets/)
