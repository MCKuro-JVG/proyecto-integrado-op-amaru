# Demostración académica en alwaysdata

El perfil usa Python 3.12 con WSGI y una base MariaDB nueva cuyo nombre termina en `_amaru_demo`. Usa datos ficticios. Se conserva la configuración local y no se importan volcados, medios ni credenciales de los entornos anteriores.

## Preparar el alojamiento

1. Comprueba en Abonnements que la cuenta tiene el plan Free y confirma el hostname que muestra Web → Sites.
2. En Bases de données → MySQL, crea `amaru_demo` en esa cuenta y asigna un usuario dedicado exclusivamente a esa base. Usa las rutas y credenciales que indique el panel.
3. Copia los archivos versionados en `~/opticas-amaru` mediante SSH. Conserva el código fuera del directorio del sitio estático predeterminado. Usa `git archive` de un commit revisado o un clon, sin directorios de trabajo privados.
4. Crea `~/.amaru-demo` con modo 0700 y el archivo `~/.amaru-demo/.env` con modo 0600, a partir de `.env.example`. Rellena los campos con valores propios de la demo y genera una clave Django aleatoria con `python -c 'import secrets; print(secrets.token_urlsafe(64))'` en tu terminal. No publiques el resultado ni las contraseñas.
5. Ejecuta desde `~/opticas-amaru`:

```sh
umask 077
PYTHON_VERSION=3.12 python -m venv "$HOME/.amaru-venv"
. "$HOME/.amaru-venv/bin/activate"
python -m pip install --no-cache-dir -r amaru/requirements-alwaysdata.txt
export AMARU_ENV_FILE="$HOME/.amaru-demo/.env"
export DJANGO_SETTINGS_MODULE=config.alwaysdata_settings
python amaru/manage.py check --deploy
python amaru/manage.py migrate --plan
python amaru/manage.py migrate --noinput
python amaru/manage.py collectstatic --noinput
python amaru/manage.py configure_roles
```

El comando `seed_demo` crea datos y cuentas ficticios con contraseñas aleatorias. Si lo ejecutas, usa `umask 077` y guarda de inmediato el archivo generado `amaru/demo-credentials.json` en `~/.amaru-demo`. Comparte esas credenciales exclusivamente con el equipo encargado de revisar la demo.

## Configuración del sitio

En Web → Sites selecciona **Python WSGI** para el subdominio asignado. Rellena:

- Aplicación WSGI: `/home/<cuenta>/opticas-amaru/amaru/config/alwaysdata_wsgi.py`
- Directorio de trabajo: `/home/<cuenta>/opticas-amaru/amaru`
- Python: `3.12`
- Entorno virtual: `/home/<cuenta>/.amaru-venv`
- Variable de entorno: `AMARU_ENV_FILE=/home/<cuenta>/.amaru-demo/.env`

Activa la redirección HTTPS. Mantén el caché HTTP del proveedor desactivado para la API. Django protege las sesiones con cookies seguras y CSRF. WhiteNoise sirve solo el directorio de archivos estáticos recopilados. Los documentos ficticios permanecen en `~/.amaru-demo/media` y su acceso pasa por Django. El QR usa el hostname del perfil mediante HTTPS.

## Verificar antes de presentar

- Abre `/healthz/` en HTTPS y confirma que devuelve `ok`. Comprueba `/app/`, CSS, JavaScript y el logo.
- Envía una solicitud con datos ficticios. Consulta el registro en MariaDB y confirma que el personal autorizado puede revisarlo. Verifica que una sesión anónima no pueda leer `/api/inquiries/`, fichas ni documentos.
- Prueba el QR desde un celular y verifica la solicitud registrada con origen `qr`.
- Revisa consumo de memoria y disco en el panel. Si `mysqlclient` no compila, verifica `pkg-config` y las bibliotecas de MariaDB en el servidor antes de cambiar el conector. Revisa los logs de uWSGI si la aplicación no arranca.

Los límites del plan Free son 1 GB de disco, 256 MB de RAM y un cuarto de CPU. La disponibilidad de WSGI y MariaDB no demuestra que el despliegue haya sido realizado.

- [Python WSGI](https://help.alwaysdata.com/en/docs/web-hosting/languages/python/configuration/)
- [MariaDB](https://help.alwaysdata.com/en/docs/web-hosting/databases/mariadb/)
- [Plan Free](https://www.alwaysdata.com/en/offers/)

## Decisiones pendientes con Ópticas Amaru

- ¿OptiClick valida automáticamente la fecha de emisión y vigencia de las recetas ópticas?
- ¿Qué período de vigencia aplica a las recetas? El código actual conserva un año calendario. El informe académico menciona 365 días.
- ¿Cuáles son los días, horarios y cupos oficiales de atención?
- ¿Qué convenios permiten cargas familiares y qué responsable valida la pertenencia?
- Confirmar la propuesta de salmón `#FF7E70` para la interfaz. El logo se extrajo de la imagen original del PDF, con su naranja, negro, símbolo, proporciones y lema. La interfaz anterior usaba naranja como acento predominante.

## Estado de la preparación

El panel confirmó el plan Free de `opticaamaru`, el subdominio `opticaamaru.alwaysdata.net` y MariaDB 11.8. Se creó `opticaamaru_amaru_demo` vacía, sin usuarios asignados. El subdominio responde por HTTPS con el sitio inicial del proveedor. Falta autorizar la clave de despliegue, crear el usuario dedicado, instalar las dependencias, aplicar las migraciones remotas y configurar el sitio WSGI.

El perfil pasó la verificación local de WSGI, `collectstatic`, redirección HTTPS, CSRF y permisos con SQLite temporal. Las 94 pruebas en MariaDB 11.4 local pasaron en una base descartable, incluida la carrera entre una solicitud y un bloqueo. Las migraciones 0005–0008 se aplicaron en las dos bases locales después de respaldarlas.

## Flujos agregados

- **Agenda:** el formulario consulta cupos disponibles de los próximos 30 días. La configuración académica semanal se edita en Configuración del sitio del administrador Django. En Solicitudes recibidas, el personal con permiso puede bloquear un día o una hora, liberar bloqueos y cancelar solicitudes. Se conserva un cupo por hora y queda el historial de solicitudes y acciones.
- **Catálogo:** búsqueda, filtros y administración autenticada. Las bajas se realizan desactivando, para conservar referencias históricas. Los precios son referencias académicas.
- **Recetas:** el cliente autenticado con ficha activa puede cargar JPG, PNG o PDF privado y seleccionar su receta vigente al solicitar un producto. La orientación y el agendamiento público siguen disponibles. En alwaysdata se usa almacenamiento privado local para documentos ficticios, separado de las credenciales R2 y los datos operativos existentes.
- **Convenios:** desde el panel se puede crear un convenio y obtener su código o QR. La pertenencia se registra como pendiente y un usuario autorizado documenta la revisión por nómina, responsable o en persona. Las nóminas se contrastan fuera del sistema. La ficha del cliente muestra la vigencia, la calidad validada y la posibilidad de registrar la visita en la bitácora.
