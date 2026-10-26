# Organización, traslado y verificación de Ópticas Amaru

Fecha del informe: 25 de octubre de 2026.

## Ubicación principal

El proyecto se verificó desde **C:\Proyectos\OpticasAmaru**. Es la ubicación principal de desarrollo local. La carpeta anterior se conserva intacta como archivo histórico y no debe utilizarse simultáneamente para iniciar otra instancia sobre los mismos puertos.

Se reconstruyó `.venv` con Python 3.12.10 y las versiones de `amaru/requirements-lock.txt`. El historial Git anterior se conserva, incluidos los commits `a4edb65` y `dc30c58`, sin alterar autores, fechas ni contenido histórico. Los cambios de presentación se registran mediante commits nuevos.

Se creó un respaldo completo externo de la ubicación anterior y un volcado lógico de MariaDB. La base se detuvo de manera ordenada antes de copiar su directorio de datos. Se compararon **35.161 archivos, 2.874.941.334 bytes**, con SHA-256 frente al original: **sin diferencias**. El volcado lógico también tiene un hash de control. Los respaldos permanecen fuera del repositorio; su registro detallado de integridad es privado.

## Estructura

```text
OpticasAmaru/
├── amaru/
│   ├── config/                 Configuración Django y verificación R2 aislada
│   ├── gestion/                Modelos, migraciones, API, servicios y pruebas
│   ├── static/                 Cliente JavaScript de la aplicación conectada
│   ├── templates/              Plantillas conservadas
│   ├── manage.py
│   ├── .env.example            Configuración de ejemplo sin secretos
│   ├── requirements.txt
│   └── requirements-lock.txt
├── frontend_amaru/             Las 15 pantallas y recursos visuales originales
├── docs/                      Arquitectura, instalación y registros técnicos
├── .run/                      Configuración compartida de PyCharm
├── .gitignore
├── .gitattributes
├── README.md
└── Iniciar_Backend_Amaru.*
```

El entorno virtual, los archivos de entorno reales, medios privados, binarios y datos locales de MariaDB, registros y evidencias están excluidos de Git. Las pruebas permanecen en la aplicación Django para conservar su descubrimiento e importaciones.

## Limpieza de presentación

Se retiró del lanzador de la demostración la dependencia de un runtime externo de asistencia. Se actualizó el nombre del módulo de PyCharm y se sustituyeron ejemplos de ramas por nombres funcionales. El código y la documentación actuales no dependen de la ubicación personal anterior. Los archivos HTML/CSS/JS/SVG del frontend conservan el mismo contenido, salvo la normalización de finales de línea realizada por Git; se compararon 22 recursos de ejecución.

Las referencias históricas que corresponden a commits previos se conservan en el historial. No se han falsificado atribuciones ni reescrito commits para ocultar su procedencia.

## MariaDB y persistencia

- MariaDB 11.4.13, mediante mysqlclient 2.2.7.
- Base `opticas_amaru`, 27 tablas: todas InnoDB y utf8mb4.
- Migraciones `gestion.0001`, `0002` y `0003` aplicadas; sin migraciones nuevas pendientes.
- Usuario de aplicación limitado a SELECT, INSERT, UPDATE y DELETE sobre la base del proyecto; usuario distinto para migraciones/pruebas.
- Proceso MariaDB iniciado desde la instalación portable de la nueva carpeta. Se actualizaron sus rutas privadas de datos y plugins.
- El servidor Django usa el intérprete nuevo y el directorio de trabajo de la nueva ubicación.
- Se recuperaron los documentos existentes y se verificó una entrega nueva mediante la interfaz. No faltan recetas, firmas ni PDF referenciados; se comprobaron los hashes de los tres PDF existentes. La variable `datadir` de MariaDB apunta a la nueva ubicación.

El frontend conectado utiliza la API y MariaDB. La demostración con localStorage permanece conservada, pero no se carga desde `/app/`. Una prueba introdujo un dato ficticio únicamente en el almacenamiento de la demostración y comprobó que no se mostró en los registros del servidor.

## Pruebas repetidas

| Comprobación | Resultado real |
|---|---|
| Suite Django completa sobre MariaDB temporal | **50 pruebas aprobadas en 165,353 segundos**, sin fallas. El código actual contiene una prueba más que el informe inicial de 49. |
| Migraciones | Las tres migraciones de `gestion` aplicadas; `makemigrations --check --dry-run` sin cambios. |
| Django | `manage.py check --database default`: sin errores. |
| Dependencias | `pip check`: sin incompatibilidades detectadas. |
| Chrome | 35 comprobaciones: cinco etapas de integración y las 15 pantallas en escritorio 1366×900 y móvil 375×812. Sin errores JavaScript ni desbordamiento horizontal detectado. |
| Cierre y reapertura de Chrome | El cliente y el documento creados en la prueba siguieron disponibles tras autenticar una sesión nueva. |
| Perfil cliente | Solo su pedido, documentos propios y navegación sin menú administrativo; sin datos personales persistidos en localStorage. |
| Seguridad de archivos y entrega | La suite comprueba autorización, firma, PDF, hash, reversión ante fallo de almacenamiento y recepción única ante dos conexiones simultáneas. |
| Conciliación | Ejecutada en modo de solo lectura. La consulta de control mostró únicamente intentos completados; no fue necesario aplicar limpieza. |

La suite incluye clientes, RUT, recetas, cotizaciones, OT, garantías/reparaciones, agenda/contacto, catálogo, roles y auditoría. Se usaron datos ficticios. Las pruebas no constituyen certificación de seguridad de producción.

Las evidencias de esta ejecución se conservan privadamente en `logs/` y `.tools/backend-qa/`; no se publican junto al código.

## Cloudflare R2

**Pendiente por instrucción del propietario, hasta que autorice continuar.** No se realizaron conexiones remotas ni se activó R2 como almacenamiento principal. El `.env` normal conserva `R2_ENABLED=False`.

Se revisaron las clases de almacenamiento y el comando `verify_r2`: utiliza una imagen y una receta ficticias, registra referencias en MariaDB, obtiene una URL firmada y comprueba el rechazo de la ruta S3 anónima. Sus operaciones de limpieza eliminan los registros y objetos de verificación. Requiere lectura/escritura/eliminación de objetos y permisos SQL sobre sus datos ficticios. El rechazo S3 no demuestra la ausencia de un dominio público alternativo; esa configuración debe verificarse también en Cloudflare.

Se preparó `config.r2_verification_settings` para ejecutar la prueba en un proceso separado sin cambiar el almacenamiento normal. Las instrucciones y las variables necesarias se encuentran en el README. El archivo privado `.env.r2` no tiene credenciales R2 configuradas; conserva la configuración privada de Django/MariaDB y no se incluye en Git.

Quedan pendientes: existencia y permisos reales de `amaru-publico` y `amaru-privado`, subida/descarga/borrado remoto, cierre de accesos públicos alternativos del bucket privado, entrega completa con firma/PDF almacenados en R2, acceso autorizado/denegado y migración de los medios locales antes de activar el proveedor nuevo.

## GitHub

Repositorio oficial: <https://github.com/MCKuro-JVG/proyecto-integrado-op-amaru>.

La autorización de Git Credential Manager se completó mediante el flujo oficial de dispositivo. Se verificó que la identidad autenticada es el propietario y tiene permisos de escritura sobre el repositorio. Las credenciales permanecen en el almacén del sistema, fuera del código.

La publicación en `main` se completó mediante push normal. La comprobación inicial encontró el mismo commit local y remoto: `d37e3505a313187b49a0729ff59552472ac10230`. La API pública de GitHub confirmó 93 archivos, las 15 interfaces y el README accesible; el árbol remoto coincide con el local. Los commits anteriores permanecen como ancestros. Este informe puede añadir un commit documental posterior; la versión vigente se consulta así:

```powershell
git rev-parse HEAD
git ls-remote origin refs/heads/main
```

La identidad y los permisos efectivos se verificaron mediante la autenticación CLI, resolviendo el bloqueo de publicación anterior. Se utilizó push normal, sin force push ni modificación del historial compartido.

La revisión previa cubrió los 93 archivos seleccionados y 90 blobs históricos: no detectó coincidencias con las credenciales locales, claves privadas, bases, medios ni registros privados. Las referencias personales y de preparación innecesarias fueron retiradas del contenido vigente; el historial original se conserva. La revisión no equivale a una certificación universal de ausencia de secretos desconocidos.

## PyCharm y ejecución

1. Abrir la carpeta `C:\Proyectos\OpticasAmaru`.
2. Seleccionar el intérprete `.venv\Scripts\python.exe` de esa carpeta.
3. Usar la configuración compartida `Amaru Django` o crear una configuración Python con script `amaru/manage.py`, argumentos `runserver 127.0.0.1:8001` y directorio `amaru`.
4. Abrir <http://127.0.0.1:8001/app/> en Chrome.
5. También puede ejecutarse `Iniciar_Backend_Amaru.cmd` desde la raíz.

Se comprobó el intérprete, los comandos y el servidor desde la nueva ubicación. No se afirma haber operado gráficamente PyCharm. El README contiene los pasos completos para un equipo nuevo, MariaDB, cuentas personales, entorno, migraciones, roles, pruebas y futura configuración de R2.

## Decisiones y límites

Se mantienen el retiro dentro del sistema, el documento digital y el acceso público de potenciales clientes. OptiClick permanece fuera del alcance. Falta confirmar con la empresa las condiciones oficiales de garantía, el mecanismo definitivo de firma simple y la diferencia entre 365 días y un año calendario de vigencia de recetas.

Publicar el código en GitHub no despliega la aplicación en Internet. No se contrató ni configuró hosting de producción. La configuración actual está orientada al desarrollo académico local. La integración completa con R2 no se declara finalizada.
