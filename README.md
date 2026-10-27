# Ópticas Amaru

Aplicación académica para atención óptica. Evolución del backend `amaru/gestion` y de las interfaces HTML, CSS y JavaScript existentes; no es un proyecto independiente.

**Estado:** aplicación local Django + MariaDB con Cloudflare R2 activado y verificado el 26 de octubre de 2026. Las recetas, firmas y PDF se guardan en `amaru-privado`; las imágenes del catálogo utilizan `amaru-publico`. Se comprobaron 59 pruebas automatizadas sobre MariaDB y 35 verificaciones de interfaz en Chrome. Consulte [la conexión y las pruebas de R2](docs/CLOUDFLARE_R2.md). El repositorio conserva el historial y el frontend original. Las credenciales y los medios no se publican.

## Tecnologías y estructura

- Python 3.12; Django 5.2.17; Django REST Framework 3.16.1.
- MariaDB 11.4 LTS y mysqlclient 2.2.7; InnoDB, utf8mb4, modo SQL estricto.
- django-storages 1.14.6 y boto3 para R2 privado/público.
- HTML/CSS/JavaScript sin React ni servicios externos de frontend.

```text
amaru/
  config/                Configuración Django y rutas
  gestion/
    models.py            Entidades y restricciones
    serializers.py       Contratos y validaciones de la API
    api.py, api_urls.py   Endpoints y permisos
    services.py          Cotización → OT y entrega transaccional
    storage.py           Almacenamientos R2 separados
    management/commands/ Roles, conciliación y comprobación R2
    migrations/          Historial conservado y migraciones nuevas
    tests.py             Pruebas del backend anterior
    test_api.py          Pruebas de API, permisos y fallos de almacenamiento
  static/server.js       Conecta las interfaces a Django; no usa localStorage
  templates/             Vistas Django anteriores conservadas
frontend_amaru/           Las 15 pantallas, CSS, SVG y motor DEMO anterior
docs/                    Arquitectura, decisiones y verificación
.run/                    Configuración compartida de ejecución para PyCharm
Iniciar_Backend_Amaru.*   Inicio local en Windows, puerto 8001
```

## Preparación en Windows y PyCharm

1. Instalar Python 3.12 de 64 bits, Git y MariaDB 11.4 LTS. La instalación portable local, cuando exista, permanece en `.tools`, excluida del repositorio; cada equipo configura su propia base de datos.
2. Clonar el repositorio y abrir su carpeta raíz en PyCharm:

```powershell
git clone https://github.com/MCKuro-JVG/proyecto-integrado-op-amaru.git OpticasAmaru
Set-Location OpticasAmaru
```

3. En PowerShell, desde esa carpeta:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r amaru\requirements.txt
Copy-Item amaru\.env.example amaru\.env
```

Para reproducir exactamente el entorno completo de desarrollo validado, utilizar `amaru/requirements-lock.txt` en lugar de `requirements.txt`. Ese archivo incluye Playwright y las versiones transitivas; el archivo principal contiene solo dependencias directas de ejecución y conserva psycopg para la compatibilidad anterior.

4. En PyCharm: Settings → Project → Python Interpreter → Add Local Interpreter → Existing → seleccionar `.venv\Scripts\python.exe`. Esto requiere selección manual; no se ha controlado gráficamente PyCharm.
5. Completar `amaru/.env` localmente. Generar la clave Django con:

```powershell
.\.venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

6. Crear una configuración Python: script `amaru/manage.py`, parámetros `runserver 127.0.0.1:8001`, directorio `amaru`, intérprete `.venv`. La configuración compartida `.run/Amaru_Django.run.xml` puede importarse, ajustando el módulo al nombre del proyecto local.

No activar el modo de producción sobre HTTP local. `DEBUG=True` es exclusivamente desarrollo. Producción requiere HTTPS, `DEBUG=False`, clave propia, hosts concretos, servidor WSGI, estáticos recopilados y caché compartida para límites de intentos.

## MariaDB y usuarios

En la consola administrativa de MariaDB, crear la base y dos usuarios locales. Sustituir los textos de ejemplo antes de ejecutar:

```sql
CREATE DATABASE opticas_amaru CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'amaru_app'@'127.0.0.1' IDENTIFIED BY 'CAMBIAR_PASSWORD_APP';
GRANT SELECT, INSERT, UPDATE, DELETE ON opticas_amaru.* TO 'amaru_app'@'127.0.0.1';
CREATE USER 'amaru_migrator'@'127.0.0.1' IDENTIFIED BY 'CAMBIAR_PASSWORD_MIGRACIONES';
GRANT ALL PRIVILEGES ON opticas_amaru.* TO 'amaru_migrator'@'127.0.0.1';
GRANT ALL PRIVILEGES ON test_opticas_amaru.* TO 'amaru_migrator'@'127.0.0.1';
```

La aplicación utiliza `amaru_app`, nunca root. El usuario de migraciones tiene permisos DDL solo en las bases del proyecto y pruebas; no recibe privilegios globales ni GRANT OPTION. MariaDB debe escuchar solo en la interfaz prevista; para el equipo local, `127.0.0.1:3306`.

Comprobar `SHOW GRANTS FOR 'amaru_app'@'127.0.0.1'`. Algunas distribuciones recién inicializadas conceden permisos de bases `test` a `PUBLIC`; el administrador debe revisarlos y retirarlos si existen. En la instancia aislada de este proyecto se retiraron esas concesiones predeterminadas. No ejecutar revocaciones globales sobre un servidor compartido sin revisar a sus demás usuarios.

Variables: `DB_ENGINE=mysql`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`. Para migrar, crear `amaru/.env.migrations` con el mismo contenido pero usuario/contraseña de migraciones. Ambos archivos están excluidos de Git.

```powershell
$env:AMARU_ENV_FILE = "$PWD\amaru\.env.migrations"
.\.venv\Scripts\python.exe amaru\manage.py migrate
.\.venv\Scripts\python.exe amaru\manage.py configure_roles
Remove-Item Env:AMARU_ENV_FILE
.\.venv\Scripts\python.exe amaru\manage.py createsuperuser
```

Antes de migrar una base existente, respaldarla con `mariadb-dump --single-transaction`, guardar el volcado fuera de Git y revisar `showmigrations`. Las migraciones de la nueva base no importan automáticamente datos del antiguo PostgreSQL. Las herramientas del entorno PostgreSQL anterior permanecen en el archivo privado del proyecto y no forman parte de la instalación actual.

## Ejecutar y utilizar

```powershell
.\.venv\Scripts\python.exe amaru\manage.py runserver 127.0.0.1:8001
```

También puede ejecutarse `Iniciar_Backend_Amaru.cmd`. En este equipo inicia la instancia MariaDB portable si está detenida y comprueba Django. En otro equipo se debe instalar/iniciar MariaDB según los pasos anteriores.

- Aplicación conectada: <http://127.0.0.1:8001/app/>
- Personal: <http://127.0.0.1:8001/app/dashboard.html>
- Cliente autenticado: <http://127.0.0.1:8001/app/consulta.html>
- Administración de cuentas, catálogo y convenios: <http://127.0.0.1:8001/admin/>
- Backend anterior conservado: <http://127.0.0.1:8001/>
- API: <http://127.0.0.1:8001/api/>

Crear usuarios desde el administrador y asignar los grupos Administrador, Personal de atención, Taller o Cliente. Para un cliente, vincular su usuario a la ficha `Client.user` en el administrador. No hay autorregistro público ni vinculación automática mediante RUT. Taller puede consultar órdenes/actualizar avance y revisar garantías; no accede a recetas, firmas ni fichas completas de clientes. El cliente solo recibe sus órdenes y documentos. Las contraseñas se almacenan con los mecanismos de Django.

Opcionalmente, `python amaru/manage.py seed_demo` prepara datos ficticios y nuevas cuentas de presentación. Las contraseñas generadas quedan exclusivamente en `amaru/demo-credentials.json`, ignorado por Git. No utilizar este comando para cargar datos comerciales reales.

La demostración estática original sigue en `frontend_amaru`, con almacenamiento local y acceso DEMO. `Abrir_Opticas_Amaru.cmd` y la publicación estática anterior siguen correspondiendo a esa demostración. **Para usar MariaDB hay que abrir `/app/` desde Django.** El hosting estático no ejecuta Python ni MariaDB.

## Cloudflare R2

Configurar únicamente desde la cuenta autorizada:

1. Bucket `amaru-publico`: solo imágenes del catálogo, con dominio público configurado.
2. Bucket `amaru-privado`: sin `r2.dev` público, sin dominio público ni reglas que permitan acceso anónimo. Contiene recetas, firmas y PDF.
3. Credenciales S3 con lectura/escritura limitadas a esos buckets. Guardarlas en `.env`, nunca en HTML, JavaScript o GitHub. No activar servicios de pago desde scripts.
4. En un equipo nuevo, preparar `amaru/.env.r2`, privado, con la configuración MariaDB y Django más `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_ENDPOINT_URL`, `R2_BUCKET_PUBLICO`, `R2_BUCKET_PRIVADO`, `R2_DOMINIO_PUBLICO` (sin https://) y `R2_URL_SECONDS=600`. Mantener `R2_ENABLED=False` en el `.env` normal hasta superar las pruebas iniciales y copiar los archivos que ya existan. En el equipo principal esta transición ya se completó; su `.env` utiliza `R2_ENABLED=True`.
5. Ejecutar la verificación en un proceso separado; no iniciar el servidor con esta configuración:

```powershell
$env:AMARU_ENV_FILE = "$PWD\amaru\.env.r2"
.\.venv\Scripts\python.exe amaru\manage.py verify_r2 --settings=config.r2_verification_settings
Remove-Item Env:AMARU_ENV_FILE
```

Ese comando utiliza archivos ficticios, verifica referencias SQL, subida, recuperación y URL firmada, y elimina los datos temporales. El rechazo de la URL S3 sin firma no demuestra que no exista un dominio público alternativo: revisar también el panel de Cloudflare. Antes de activar R2 para la aplicación, se debe aprobar además el flujo completo de entrega con almacenamiento privado y la migración de los archivos locales existentes. En el equipo principal ambas comprobaciones ya se completaron; el detalle está en [CLOUDFLARE_R2.md](docs/CLOUDFLARE_R2.md). Para comprobar posteriormente la configuración activa basta ejecutar `python amaru/manage.py verify_r2`.

Se utiliza la API `STORAGES` de Django 5.2. El destino predeterminado es **privado**. Cada campo declara su almacenamiento. La base guarda claves de objetos, nunca URLs firmadas permanentes. El backend comprueba permisos antes de entregar la URL de 600 segundos; quien posea esa URL podrá usarla durante su vigencia.

Sin `R2_ENABLED`, los archivos se conservan en `amaru/media/` privado y se sirven mediante endpoints autorizados. **Ese modo no constituye una prueba de conexión R2.** Los archivos anteriores no cambian de proveedor automáticamente: deben copiarse, verificarse mediante hash y conservarse en origen hasta validar las referencias. No activar R2 sobre datos antiguos sin completar esa migración.

Obtención de credenciales: R2 → Overview → Account Details → API Tokens. Crear un token Object Read & Write limitado a los dos buckets; copiar Access Key ID y Secret Access Key al archivo privado. El Account ID y el endpoint S3 se obtienen de la misma cuenta. Véase la [documentación oficial de autenticación R2](https://developers.cloudflare.com/r2/api/tokens/). No activar facturación ni crear nuevos servicios desde scripts.

Fuentes de compatibilidad: [Django y MariaDB](https://docs.djangoproject.com/en/5.2/ref/databases/), [django-storages y R2](https://django-storages.readthedocs.io/en/latest/backends/s3_compatible/cloudflare-r2.html), [URLs firmadas de R2](https://developers.cloudflare.com/r2/api/s3/presigned-urls/).

## Entrega consistente

El personal identifica una OT disponible y abre su documento. El servidor firma temporalmente la versión revisada de datos y garantía. El cliente revisa y acepta, dibuja su firma simple y confirma. El servicio bloquea la OT, valida su versión, genera el PDF y guarda archivos privados antes de confirmar la recepción y el estado `Entregada`. Registra un SHA-256 del PDF y eventos de auditoría.

SQL y R2 no comparten una transacción distribuida. Un diario `DeliveryAttempt` conserva las claves planificadas; si falla la operación, SQL se revierte y se intenta borrar los objetos nuevos. Si el proceso se interrumpe, se revisan los intentos antiguos:

```powershell
python amaru/manage.py reconcile_deliveries
python amaru/manage.py reconcile_deliveries --apply
```

El primer comando es solo diagnóstico; el segundo elimina únicamente archivos de intentos antiguos no referenciados. No ejecutar durante una operación excepcionalmente larga sin comprobar que el proceso responsable terminó. La recepción es única por OT y los reintentos devuelven la recepción existente.

La firma es electrónica simple académica: no acredita firma avanzada ni certifica identidad legal. Las condiciones de garantía son configurables y requieren contenido oficial de la empresa.

## Pruebas

Con MariaDB y usuario de migraciones:

```powershell
$env:AMARU_ENV_FILE = "$PWD\amaru\.env.migrations"
.\.venv\Scripts\python.exe amaru\manage.py test gestion --noinput
Remove-Item Env:AMARU_ENV_FILE
```

Las pruebas crean y destruyen **test_opticas_amaru**, nunca la base principal. Reservar ese nombre exclusivamente para pruebas. Los archivos de prueba se escriben en directorios temporales. El modo aislado sin MariaDB es `--settings=config.test_settings`; no demuestra funcionamiento de MariaDB. Las pruebas de firma de URL con credenciales ficticias son verificaciones locales y no sustituyen `verify_r2` contra Cloudflare.

## Git y trabajo grupal

Repositorio: <https://github.com/MCKuro-JVG/proyecto-integrado-op-amaru>

```powershell
git switch main
git pull --ff-only
git switch -c feature/descripcion-del-cambio
# Revisar git diff y ejecutar pruebas antes de agregar archivos.
git add <archivos-revisados>
git diff --cached
git commit -m "Descripción concreta del cambio"
git push -u origin feature/descripcion-del-cambio
```

Abrir una pull request para revisión del equipo. No hacer force push. Nunca agregar `.env`, `.tools`, bases, respaldos, documentos personales, `media`, credenciales de presentación ni el entorno virtual. El `.gitignore` parte del archivo proporcionado y amplía las exclusiones para este espacio de trabajo. No compartir secretos por el repositorio aunque el proyecto sea académico.

Ver [decisiones de arquitectura](docs/ARQUITECTURA.md) y [estado de verificación](docs/ESTADO_IMPLEMENTACION.md).

## Autorización de GitHub

Para autorizar el equipo con Git Credential Manager:

```powershell
git credential-manager github login --username MCKuro-JVG --device --no-ui
```

El comando genera un código temporal para introducir en <https://github.com/login/device>. El propietario aprueba la aplicación en su navegador; las credenciales quedan en el almacén del sistema. No guardar tokens en el repositorio ni en la URL de `origin`. Antes de publicar, ejecutar `git fetch origin` y revisar el estado remoto; utilizar únicamente push normal. Cada integrante debe autorizar su propia cuenta con permisos concedidos por el propietario.

La organización y verificación de la ubicación principal se documentan en [FINALIZACION.md](docs/FINALIZACION.md).
